import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import LANGUAGE_NORMALIZED_CANONICAL, ONTOLOGY_DIMENSIONS
from app.enums import RelationType, ReviewerState, SourceObjectType
from app.models.core import CommonalityLink, FlagRecord, PassageEvidence, ProposalTrace, RitualPatternTag, VocabularyPendingTerm
from app.services.validation import ValidationError, require, validate_flag_type, validate_ontology_term, validate_relation_type

logger = logging.getLogger(__name__)


class TagProposal(BaseModel):
    ontology_dimension: str
    controlled_term: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale_note: str | None = None


class LinkProposal(BaseModel):
    target_passage_id: str
    relation_type: str = "sharesPatternWith"
    weighted_similarity_score: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale_note: str | None = None


class FlagProposal(BaseModel):
    flag_type: str
    severity: str
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalBundle(BaseModel):
    tags: list[TagProposal] = Field(default_factory=list)
    links: list[LinkProposal] = Field(default_factory=list)
    flags: list[FlagProposal] = Field(default_factory=list)


@dataclass
class ProposalResult:
    tags_created: int
    links_created: int
    flags_created: int
    trace_id: str | None


def _tokenize(text: str) -> set[str]:
    return {token for token in text.lower().split() if len(token) > 2}


def _jaccard(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens.intersection(right_tokens)
    union = left_tokens.union(right_tokens)
    return len(overlap) / len(union)


def _heuristic_bundle(passage: PassageEvidence, peer_passages: list[PassageEvidence]) -> ProposalBundle:
    text = passage.excerpt_normalized.lower()
    tags: list[TagProposal] = []
    flags: list[FlagProposal] = []
    links: list[LinkProposal] = []

    keyword_map = [
        ("dawn", "time_timing", "dawn_operation"),
        ("night", "time_timing", "night_operation"),
        ("offering", "exchange_offering", "food_offering"),
        ("libation", "exchange_offering", "liquid_libation"),
        ("circle", "protection_boundary", "circle_boundary"),
        ("protect", "ritual_intent", "protection"),
        ("divin", "ritual_intent", "divination"),
        ("invoke", "ritual_actions", "invocation"),
    ]
    for needle, dimension, term in keyword_map:
        if needle in text:
            tags.append(
                TagProposal(
                    ontology_dimension=dimension,
                    controlled_term=term,
                    confidence=0.68,
                    evidence_ids=[passage.passage_id],
                )
            )

    if passage.original_language != LANGUAGE_NORMALIZED_CANONICAL:
        flags.append(
            FlagProposal(
                flag_type="uncertain_translation",
                severity="medium",
                rationale="Passage normalized into canonical English representation from non-English original.",
                evidence_ids=[passage.passage_id],
            )
        )

    best_peer: PassageEvidence | None = None
    best_score = 0.0
    for peer in peer_passages:
        if peer.text_id == passage.text_id:
            continue
        score = _jaccard(passage.excerpt_normalized, peer.excerpt_normalized)
        if score > best_score:
            best_score = score
            best_peer = peer
    if best_peer and best_score >= 0.35:
        links.append(
            LinkProposal(
                target_passage_id=best_peer.passage_id,
                relation_type="sharesPatternWith",
                weighted_similarity_score=round(best_score, 4),
                evidence_ids=[passage.passage_id, best_peer.passage_id],
            )
        )

    if not tags:
        tags.append(
            TagProposal(
                ontology_dimension="outcome_claim",
                controlled_term="uncertain_or_symbolic",
                confidence=0.51,
                evidence_ids=[passage.passage_id],
            )
        )

    return ProposalBundle(tags=tags[:3], links=links[:1], flags=flags)


def _build_prompt(passage: PassageEvidence, peers: list[PassageEvidence]) -> str:
    peer_block = "\n".join(
        [f"- {peer.passage_id}: {peer.excerpt_normalized[:320]}" for peer in peers[:10] if peer.passage_id != passage.passage_id]
    )
    allowed_terms = json.dumps({key: sorted(value) for key, value in ONTOLOGY_DIMENSIONS.items()}, ensure_ascii=True)
    return (
        "You are proposing structured ritual-analysis metadata.\n"
        "Return strictly JSON with keys tags, links, flags.\n"
        "Each tag/link/flag must include evidence_ids with valid passage IDs from the provided passage IDs.\n"
        "Do not return markdown, prose, or extra keys.\n"
        "Only use ontology terms from this map:\n"
        f"{allowed_terms}\n"
        f"Passage ID: {passage.passage_id}\n"
        f"Passage text: {passage.excerpt_normalized[:2800]}\n"
        "Candidate peer passages for cross-cultural linking:\n"
        f"{peer_block}\n"
    )


def _build_repair_prompt(*, original_prompt: str, raw_response: str, error: str) -> str:
    return (
        "Repair this invalid JSON response and return strictly valid JSON only.\n"
        "Follow the original schema requirements and preserve only valid objects.\n"
        f"Original prompt:\n{original_prompt}\n"
        f"Invalid response:\n{raw_response}\n"
        f"Validation error:\n{error}\n"
    )


def _openai_completion_json(*, prompt: str, client: OpenAI, model: str) -> tuple[str, dict[str, Any]]:
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    usage = {
        "prompt_tokens": getattr(completion.usage, "prompt_tokens", None),
        "completion_tokens": getattr(completion.usage, "completion_tokens", None),
        "total_tokens": getattr(completion.usage, "total_tokens", None),
    }
    return raw, usage


def _parse_bundle(raw: str) -> ProposalBundle:
    parsed = json.loads(raw)
    return ProposalBundle.model_validate(parsed)


def _create_trace(
    db: Session,
    *,
    object_type: str,
    object_id: str,
    proposal_type: str,
    idempotency_key: str,
    prompt: str,
    response_body: str,
    raw_response_body: str | None,
    usage_blob: dict[str, Any],
    retry_count: int,
    failure_reason: str | None,
    actor: str,
) -> ProposalTrace:
    settings = get_settings()
    trace = ProposalTrace(
        object_type=object_type,
        object_id=object_id,
        proposal_type=proposal_type,
        idempotency_key=idempotency_key,
        model_name=settings.openai_model,
        prompt_version=settings.openai_prompt_version,
        prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        response_hash=sha256(response_body.encode("utf-8")).hexdigest(),
        raw_response_hash=sha256((raw_response_body or response_body).encode("utf-8")).hexdigest(),
        usage_blob=usage_blob,
        retry_count=retry_count,
        failure_reason=failure_reason,
        created_by=actor,
        updated_by=actor,
    )
    db.add(trace)
    db.flush()
    return trace


def _validate_evidence_ids(evidence_ids: list[str], *, allowed_ids: set[str], context: str) -> list[str]:
    require(bool(evidence_ids), f"{context} proposal must include evidence_ids")
    cleaned = [item.strip() for item in evidence_ids if item and item.strip()]
    require(bool(cleaned), f"{context} proposal evidence_ids cannot be blank")
    invalid = [item for item in cleaned if item not in allowed_ids]
    require(not invalid, f"{context} proposal evidence_ids contain invalid IDs: {invalid}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in cleaned:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _store_tag_or_pending(
    db: Session,
    *,
    evidence: PassageEvidence,
    proposal: TagProposal,
    actor: str,
) -> bool:
    evidence_ids = _validate_evidence_ids(
        proposal.evidence_ids,
        allowed_ids={evidence.passage_id},
        context="tag",
    )
    if not validate_ontology_term(proposal.ontology_dimension, proposal.controlled_term):
        pending = VocabularyPendingTerm(
            ontology_dimension=proposal.ontology_dimension,
            proposed_term=proposal.controlled_term,
            rationale=proposal.rationale_note or "Generated by proposal engine",
            evidence_ids=evidence_ids,
            status="pending",
            created_by=actor,
            updated_by=actor,
        )
        db.add(pending)
        return False

    tag = RitualPatternTag(
        ontology_dimension=proposal.ontology_dimension,
        controlled_term=proposal.controlled_term,
        confidence=proposal.confidence,
        evidence_ids=evidence_ids,
        proposer_type="automated",
        reviewer_state=ReviewerState.proposed,
        rationale_note=proposal.rationale_note,
        created_by=actor,
        updated_by=actor,
    )
    db.add(tag)
    return True


def _store_link(
    db: Session,
    *,
    evidence: PassageEvidence,
    proposal: LinkProposal,
    actor: str,
) -> bool:
    validate_relation_type(proposal.relation_type)
    require(0.0 <= proposal.weighted_similarity_score <= 1.0, "weighted_similarity_score must be in [0,1]")
    target = db.get(PassageEvidence, proposal.target_passage_id)
    if not target:
        raise ValidationError(f"Invalid target passage for link: {proposal.target_passage_id}")
    evidence_ids = _validate_evidence_ids(
        proposal.evidence_ids,
        allowed_ids={evidence.passage_id, proposal.target_passage_id},
        context="link",
    )
    link = CommonalityLink(
        source_entity_type="passage",
        source_entity_id=evidence.passage_id,
        target_entity_type="passage",
        target_entity_id=proposal.target_passage_id,
        relation_type=RelationType(proposal.relation_type),
        weighted_similarity_score=proposal.weighted_similarity_score,
        evidence_ids=evidence_ids,
        reviewer_decision=ReviewerState.proposed,
        decision_note=proposal.rationale_note,
        created_by=actor,
        updated_by=actor,
    )
    db.add(link)
    return True


def _store_flag(
    db: Session,
    *,
    evidence: PassageEvidence,
    proposal: FlagProposal,
    actor: str,
) -> bool:
    validate_flag_type(proposal.flag_type)
    require(bool(proposal.rationale.strip()), "Flag rationale is required")
    evidence_ids = _validate_evidence_ids(
        proposal.evidence_ids,
        allowed_ids={evidence.passage_id},
        context="flag",
    )
    flag = FlagRecord(
        object_type=SourceObjectType.passage,
        object_id=evidence.passage_id,
        flag_type=proposal.flag_type,
        severity=proposal.severity,
        rationale=proposal.rationale,
        evidence_ids=evidence_ids,
        reviewer_state=ReviewerState.proposed,
        created_by=actor,
        updated_by=actor,
    )
    db.add(flag)
    return True


def propose_for_passage(db: Session, *, passage: PassageEvidence, actor: str, idempotency_root: str) -> ProposalResult:
    settings = get_settings()
    existing_trace_stmt = select(ProposalTrace).where(
        ProposalTrace.object_type == "passage",
        ProposalTrace.object_id == passage.passage_id,
        ProposalTrace.proposal_type == "bundle",
        ProposalTrace.failure_reason.is_(None),
    )
    if db.scalar(existing_trace_stmt):
        return ProposalResult(tags_created=0, links_created=0, flags_created=0, trace_id=None)

    peer_stmt = select(PassageEvidence).limit(200)
    peers = list(db.scalars(peer_stmt))

    bundle: ProposalBundle
    prompt: str
    usage: dict[str, Any]
    raw_response: str
    retry_count = 0
    failure_reason: str | None = None

    if settings.use_mock_ai:
        bundle = _heuristic_bundle(passage, peers)
        prompt = _build_prompt(passage, peers)
        usage = {"mode": "mock"}
        raw_response = bundle.model_dump_json()
    else:
        prompt = _build_prompt(passage, peers)
        client = OpenAI(api_key=settings.openai_api_key)
        raw_attempt_1 = ""
        raw_attempt_2 = ""
        usage_attempts: list[dict[str, Any]] = []
        try:
            raw_attempt_1, usage_1 = _openai_completion_json(
                prompt=prompt,
                client=client,
                model=settings.openai_model,
            )
            usage_attempts.append({"attempt": 1, **usage_1})
            bundle = _parse_bundle(raw_attempt_1)
            raw_response = raw_attempt_1
            usage = {"mode": "openai", "attempts": usage_attempts}
        except Exception as first_exc:
            retry_count = 1
            repair_prompt = _build_repair_prompt(
                original_prompt=prompt,
                raw_response=raw_attempt_1 or "{}",
                error=f"{first_exc.__class__.__name__}: {first_exc}",
            )
            try:
                raw_attempt_2, usage_2 = _openai_completion_json(
                    prompt=repair_prompt,
                    client=client,
                    model=settings.openai_model,
                )
                usage_attempts.append({"attempt": 2, **usage_2})
                bundle = _parse_bundle(raw_attempt_2)
                raw_response = raw_attempt_2
                usage = {
                    "mode": "openai_repair",
                    "attempts": usage_attempts,
                    "initial_error": f"{first_exc.__class__.__name__}: {first_exc}",
                }
            except Exception as second_exc:
                failure_reason = (
                    "openai_bundle_validation_failed: "
                    f"attempt1={first_exc.__class__.__name__}: {first_exc}; "
                    f"attempt2={second_exc.__class__.__name__}: {second_exc}"
                )
                raw_response = raw_attempt_2 or raw_attempt_1 or "{}"
                usage = {
                    "mode": "openai_failed",
                    "attempts": usage_attempts,
                    "initial_error": f"{first_exc.__class__.__name__}: {first_exc}",
                    "repair_error": f"{second_exc.__class__.__name__}: {second_exc}",
                }
                trace = _create_trace(
                    db,
                    object_type="passage",
                    object_id=passage.passage_id,
                    proposal_type="bundle",
                    idempotency_key=f"{idempotency_root}:{passage.passage_id}",
                    prompt=prompt,
                    response_body=raw_response,
                    raw_response_body=raw_response,
                    usage_blob=usage,
                    retry_count=retry_count,
                    failure_reason=failure_reason,
                    actor=actor,
                )
                logger.warning("OpenAI proposal validation failed for %s: %s", passage.passage_id, failure_reason)
                raise ValidationError(f"AI proposal generation failed for {passage.passage_id}") from second_exc

    trace = _create_trace(
        db,
        object_type="passage",
        object_id=passage.passage_id,
        proposal_type="bundle",
        idempotency_key=f"{idempotency_root}:{passage.passage_id}",
        prompt=prompt,
        response_body=raw_response,
        raw_response_body=raw_response,
        usage_blob=usage,
        retry_count=retry_count,
        failure_reason=failure_reason,
        actor=actor,
    )

    tags_created = 0
    links_created = 0
    flags_created = 0

    for tag_proposal in bundle.tags:
        try:
            if _store_tag_or_pending(db, evidence=passage, proposal=tag_proposal, actor=actor):
                tags_created += 1
        except ValidationError as exc:
            logger.warning("Skipped invalid tag proposal for %s: %s", passage.passage_id, exc)
    for link_proposal in bundle.links:
        try:
            if _store_link(db, evidence=passage, proposal=link_proposal, actor=actor):
                links_created += 1
        except ValidationError as exc:
            logger.warning("Skipped invalid link proposal for %s: %s", passage.passage_id, exc)
    for flag_proposal in bundle.flags:
        try:
            if _store_flag(db, evidence=passage, proposal=flag_proposal, actor=actor):
                flags_created += 1
        except ValidationError as exc:
            logger.warning("Skipped invalid flag proposal for %s: %s", passage.passage_id, exc)

    return ProposalResult(
        tags_created=tags_created,
        links_created=links_created,
        flags_created=flags_created,
        trace_id=trace.trace_id,
    )
