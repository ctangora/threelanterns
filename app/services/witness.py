from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.base import prefixed_id
from app.models.core import (
    ConsolidatedPassage,
    ConsolidatedPassageSource,
    PassageEvidence,
    SourceMaterialRecord,
    TextRecord,
    WitnessGroup,
    WitnessGroupMember,
)
from app.services.parsers import parse_source_file
from app.services.utils import normalize_to_english, sha256_text
from app.services.validation import ValidationError, require

FUZZY_MATCH_THRESHOLD = 0.82
FUZZY_REVIEW_THRESHOLD = 0.70
PASSAGE_SIMILARITY_THRESHOLD = 0.92


def _token_set(text: str) -> set[str]:
    return {token for token in normalize_to_english(text).lower().split() if len(token) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = left.intersection(right)
    union = left.union(right)
    return len(overlap) / len(union)


def _title_similarity(left: str, right: str) -> float:
    return _jaccard(_token_set(left), _token_set(right))


@dataclass(frozen=True)
class FuzzyMatch:
    source: SourceMaterialRecord
    score: float
    method: str


def find_fuzzy_match(
    db: Session,
    *,
    normalized_text: str,
    canonical_title: str,
    max_candidates: int = 80,
) -> FuzzyMatch | None:
    tokens_new = _token_set(normalized_text)
    if not tokens_new:
        return None
    candidates = list(
        db.scalars(select(SourceMaterialRecord).order_by(SourceMaterialRecord.created_at.desc()).limit(max_candidates))
    )
    best: FuzzyMatch | None = None
    for candidate in candidates:
        try:
            parsed = parse_source_file(Path(candidate.source_path))
        except Exception:
            continue
        normalized = normalize_to_english(parsed)[:120000]
        score = _jaccard(tokens_new, _token_set(normalized))
        if canonical_title:
            text = db.get(TextRecord, candidate.text_id)
            title = text.canonical_title if text else ""
            title_score = _title_similarity(canonical_title, title)
            if title_score >= 0.8:
                score = min(1.0, score + 0.1)
            elif title_score >= 0.5:
                score = min(1.0, score + 0.05)
        if best is None or score > best.score:
            best = FuzzyMatch(source=candidate, score=score, method="fuzzy")
    return best


def ensure_group_for_source(
    db: Session,
    *,
    source: SourceMaterialRecord,
    canonical_text_id: str | None,
    actor: str,
    match_method: str,
    match_score: float,
    status: str,
) -> WitnessGroup:
    if source.witness_group_id:
        existing = db.get(WitnessGroup, source.witness_group_id)
        if existing is not None:
            return existing

    group = WitnessGroup(
        group_id=prefixed_id("wgr"),
        canonical_text_id=canonical_text_id,
        group_status=status,
        match_method=match_method,
        match_score=match_score,
        created_by=actor,
        updated_by=actor,
    )
    db.add(group)
    source.witness_group_id = group.group_id
    source.updated_by = actor
    db.flush()
    return group


def add_member(
    db: Session,
    *,
    group_id: str,
    source_id: str,
    role: str,
    parser_strategy: str | None,
    membership_reason: str,
    actor: str,
) -> WitnessGroupMember:
    existing = db.get(WitnessGroupMember, {"group_id": group_id, "source_id": source_id})
    if existing is not None:
        if parser_strategy and existing.parser_strategy != parser_strategy:
            existing.parser_strategy = parser_strategy
        if membership_reason and membership_reason not in (existing.membership_reason or ""):
            existing.membership_reason = membership_reason
        existing.updated_by = actor
        db.flush()
        return existing

    member = WitnessGroupMember(
        group_id=group_id,
        source_id=source_id,
        member_role=role,
        parser_strategy=parser_strategy,
        membership_reason=membership_reason,
        created_by=actor,
        updated_by=actor,
    )
    db.add(member)
    db.flush()
    return member


def update_group_status_for_parser(
    db: Session,
    *,
    group: WitnessGroup,
    parser_strategy: str | None,
    actor: str,
) -> None:
    if not parser_strategy:
        return
    existing = db.scalar(
        select(WitnessGroupMember).where(
            WitnessGroupMember.group_id == group.group_id,
            WitnessGroupMember.parser_strategy == parser_strategy,
        )
    )
    if existing is None:
        group.group_status = "needs_review"
        group.updated_by = actor


def consolidate_group(db: Session, *, group_id: str, actor: str) -> dict[str, Any]:
    group = db.get(WitnessGroup, group_id)
    require(group is not None, f"Witness group not found: {group_id}")

    db.execute(delete(ConsolidatedPassageSource).where(ConsolidatedPassageSource.consolidated_id.in_(
        select(ConsolidatedPassage.consolidated_id).where(ConsolidatedPassage.group_id == group_id)
    )))
    db.execute(delete(ConsolidatedPassage).where(ConsolidatedPassage.group_id == group_id))
    db.flush()

    members = list(db.scalars(select(WitnessGroupMember).where(WitnessGroupMember.group_id == group_id)))
    source_ids = [member.source_id for member in members]
    if not source_ids:
        return {"consolidated": 0, "sources": 0}

    passages = list(db.scalars(select(PassageEvidence).where(PassageEvidence.source_id.in_(source_ids))))
    consolidated: list[ConsolidatedPassage] = []

    def _find_similar(target: PassageEvidence) -> tuple[ConsolidatedPassage | None, float]:
        tokens_target = _token_set(target.excerpt_normalized or target.excerpt_original)
        best_match = None
        best_score = 0.0
        for item in consolidated:
            score = _jaccard(tokens_target, _token_set(item.excerpt_merged))
            if score > best_score:
                best_score = score
                best_match = item
        return best_match, best_score

    for passage in passages:
        normalized = normalize_to_english(passage.excerpt_normalized or passage.excerpt_original)
        passage_hash = sha256_text(normalized)
        existing = next((item for item in consolidated if item.passage_hash == passage_hash), None)
        similarity_score = 1.0
        if existing is None:
            match, score = _find_similar(passage)
            if match and score >= PASSAGE_SIMILARITY_THRESHOLD:
                existing = match
                similarity_score = score
        if existing is None:
            existing = ConsolidatedPassage(
                group_id=group_id,
                excerpt_merged=normalized,
                passage_hash=passage_hash,
                usability_score=passage.usability_score,
                relevance_score=passage.relevance_score,
                relevance_state=getattr(passage.relevance_state, "value", str(passage.relevance_state)),
                created_by=actor,
                updated_by=actor,
            )
            db.add(existing)
            db.flush()
            consolidated.append(existing)
        else:
            if len(normalized) > len(existing.excerpt_merged):
                existing.excerpt_merged = normalized
            existing.updated_by = actor

        link = ConsolidatedPassageSource(
            consolidated_id=existing.consolidated_id,
            passage_id=passage.passage_id,
            source_id=passage.source_id,
            similarity_score=similarity_score,
            created_by=actor,
            updated_by=actor,
        )
        db.add(link)

    group.group_status = "active" if group.group_status != "archived" else group.group_status
    group.updated_by = actor
    db.flush()
    return {"consolidated": len(consolidated), "sources": len(source_ids)}

