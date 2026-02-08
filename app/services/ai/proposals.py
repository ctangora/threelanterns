import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import LANGUAGE_NORMALIZED_CANONICAL, ONTOLOGY_DIMENSIONS
from app.enums import RelationType, ReviewerState, SourceObjectType
from app.models.core import CommonalityLink, FlagRecord, PassageEvidence, ProposalTrace, RitualPatternTag, VocabularyPendingTerm
from app.services.validation import require, validate_flag_type, validate_ontology_term, validate_relation_type

logger = logging.getLogger(__name__)


class TagProposal(BaseModel):
    ontology_dimension: str
    controlled_term: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_note: str | None = None


class LinkProposal(BaseModel):
    target_passage_id: str
    relation_type: str = "sharesPatternWith"
    weighted_similarity_score: float = Field(ge=0.0, le=1.0)
    rationale_note: str | None = None


class FlagProposal(BaseModel):
    flag_type: str
    severity: str
    rationale: str


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
            tags.append(TagProposal(ontology_dimension=dimension, controlled_term=term, confidence=0.68))

    if passage.original_language != LANGUAGE_NORMALIZED_CANONICAL:
        flags.append(
            FlagProposal(
                flag_type="uncertain_translation",
                severity="medium",
                rationale="Passage normalized into canonical English representation from non-English original.",
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
            )
        )

    if not tags:
        tags.append(TagProposal(ontology_dimension="outcome_claim", controlled_term="uncertain_or_symbolic", confidence=0.51))

    return ProposalBundle(tags=tags[:3], links=links[:1], flags=flags)


def _build_prompt(passage: PassageEvidence, peers: list[PassageEvidence]) -> str:
    peer_block = "\n".join(
        [f"- {peer.passage_id}: {peer.excerpt_normalized[:320]}" for peer in peers[:10] if peer.passage_id != passage.passage_id]
    )
    allowed_terms = json.dumps({key: sorted(value) for key, value in ONTOLOGY_DIMENSIONS.items()}, ensure_ascii=True)
    return (
        "You are proposing structured ritual-analysis metadata.\n"
        "Return strictly JSON with keys tags, links, flags.\n"
        "Only use ontology terms from this map:\n"
        f"{allowed_terms}\n"
        f"Passage ID: {passage.passage_id}\n"
        f"Passage text: {passage.excerpt_normalized[:2800]}\n"
        "Candidate peer passages for cross-cultural linking:\n"
        f"{peer_block}\n"
    )


def _openai_bundle(passage: PassageEvidence, peer_passages: list[PassageEvidence]) -> tuple[ProposalBundle, dict[str, Any], str]:
    settings = get_settings()
    prompt = _build_prompt(passage, peer_passages)
    client = OpenAI(api_key=settings.openai_api_key)

    completion = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    bundle = ProposalBundle.model_validate(parsed)
    usage = {
        "prompt_tokens": getattr(completion.usage, "prompt_tokens", None),
        "completion_tokens": getattr(completion.usage, "completion_tokens", None),
        "total_tokens": getattr(completion.usage, "total_tokens", None),
    }
    return bundle, usage, prompt


def _create_trace(
    db: Session,
    *,
    object_type: str,
    object_id: str,
    proposal_type: str,
    idempotency_key: str,
    prompt: str,
    response_body: str,
    usage_blob: dict[str, Any],
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
        usage_blob=usage_blob,
        created_by=actor,
        updated_by=actor,
    )
    db.add(trace)
    db.flush()
    return trace


def _store_tag_or_pending(
    db: Session,
    *,
    evidence: PassageEvidence,
    proposal: TagProposal,
    actor: str,
) -> bool:
    if not validate_ontology_term(proposal.ontology_dimension, proposal.controlled_term):
        pending = VocabularyPendingTerm(
            ontology_dimension=proposal.ontology_dimension,
            proposed_term=proposal.controlled_term,
            rationale=proposal.rationale_note or "Generated by proposal engine",
            evidence_ids=[evidence.passage_id],
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
        evidence_ids=[evidence.passage_id],
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
        return False
    link = CommonalityLink(
        source_entity_type="passage",
        source_entity_id=evidence.passage_id,
        target_entity_type="passage",
        target_entity_id=proposal.target_passage_id,
        relation_type=RelationType(proposal.relation_type),
        weighted_similarity_score=proposal.weighted_similarity_score,
        evidence_ids=[evidence.passage_id, proposal.target_passage_id],
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
    flag = FlagRecord(
        object_type=SourceObjectType.passage,
        object_id=evidence.passage_id,
        flag_type=proposal.flag_type,
        severity=proposal.severity,
        rationale=proposal.rationale,
        evidence_ids=[evidence.passage_id],
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
    )
    if db.scalar(existing_trace_stmt):
        return ProposalResult(tags_created=0, links_created=0, flags_created=0, trace_id=None)

    peer_stmt = select(PassageEvidence).limit(200)
    peers = list(db.scalars(peer_stmt))

    bundle: ProposalBundle
    prompt: str
    usage: dict[str, Any]
    raw_response: str

    if settings.use_mock_ai:
        bundle = _heuristic_bundle(passage, peers)
        prompt = _build_prompt(passage, peers)
        usage = {"mode": "mock"}
        raw_response = bundle.model_dump_json()
    else:
        try:
            bundle, usage, prompt = _openai_bundle(passage, peers)
            raw_response = bundle.model_dump_json()
        except (ValidationError, Exception) as exc:
            logger.exception("AI proposal generation failed, fallback to heuristic: %s", exc)
            bundle = _heuristic_bundle(passage, peers)
            prompt = _build_prompt(passage, peers)
            usage = {"mode": "fallback", "error": str(exc)}
            raw_response = bundle.model_dump_json()

    trace = _create_trace(
        db,
        object_type="passage",
        object_id=passage.passage_id,
        proposal_type="bundle",
        idempotency_key=f"{idempotency_root}:{passage.passage_id}",
        prompt=prompt,
        response_body=raw_response,
        usage_blob=usage,
        actor=actor,
    )

    tags_created = 0
    links_created = 0
    flags_created = 0

    for tag_proposal in bundle.tags:
        if _store_tag_or_pending(db, evidence=passage, proposal=tag_proposal, actor=actor):
            tags_created += 1
    for link_proposal in bundle.links:
        if _store_link(db, evidence=passage, proposal=link_proposal, actor=actor):
            links_created += 1
    for flag_proposal in bundle.flags:
        if _store_flag(db, evidence=passage, proposal=flag_proposal, actor=actor):
            flags_created += 1

    return ProposalResult(
        tags_created=tags_created,
        links_created=links_created,
        flags_created=flags_created,
        trace_id=trace.trace_id,
    )
