from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ReviewerState
from app.models.core import CommonalityLink, FlagRecord, PassageEvidence, RitualPatternTag, TextRecord
from app.services.validation import ValidationError


def _score_and_snippet(text: str, *, query: str, tokens: list[str]) -> tuple[float, str]:
    compact = " ".join(text.split())
    lowered = compact.lower()
    if not query:
        return 0.5, compact[:280]

    score = 0.0
    if query in lowered:
        score += 1.0
    token_hits = sum(1 for token in tokens if token in lowered)
    if tokens:
        score += token_hits / len(tokens)

    index = lowered.find(query)
    if index >= 0:
        start = max(0, index - 80)
        end = min(len(compact), index + len(query) + 120)
        snippet = compact[start:end]
    else:
        snippet = compact[:220]
    return round(score, 4), snippet


def _parse_object_types(object_type: str | None) -> list[str]:
    allowed = {"passage", "tag", "link", "flag"}
    if object_type is None:
        return ["passage", "tag", "link", "flag"]
    if object_type not in allowed:
        raise ValidationError(f"Unsupported object_type filter: {object_type}")
    return [object_type]


def search_records(
    db: Session,
    *,
    query: str,
    object_type: str | None = None,
    tag: str | None = None,
    culture_region: str | None = None,
    review_state: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    normalized_query = query.strip().lower()
    query_tokens = [token for token in normalized_query.split() if token]
    if not any([normalized_query, tag, culture_region, review_state]):
        raise ValidationError("At least one search filter is required")

    if review_state is not None:
        try:
            requested_state = ReviewerState(review_state)
        except ValueError as exc:
            raise ValidationError(f"Unsupported review_state: {review_state}") from exc
    else:
        requested_state = None

    allowed_types = _parse_object_types(object_type)
    text_region_map = {row.text_id: row.origin_culture_region for row in db.scalars(select(TextRecord)).all()}

    tag_passage_ids: set[str] | None = None
    if tag:
        tag_rows = db.scalars(select(RitualPatternTag).where(RitualPatternTag.controlled_term == tag)).all()
        passage_ids: set[str] = set()
        for row in tag_rows:
            passage_ids.update(evidence_id for evidence_id in row.evidence_ids if evidence_id.startswith("psg_"))
        tag_passage_ids = passage_ids

    hits: list[dict[str, Any]] = []

    if "passage" in allowed_types:
        for row in db.scalars(select(PassageEvidence)).all():
            if requested_state and row.reviewer_state != requested_state:
                continue
            if culture_region and text_region_map.get(row.text_id) != culture_region:
                continue
            if tag_passage_ids is not None and row.passage_id not in tag_passage_ids:
                continue
            score, snippet = _score_and_snippet(
                f"{row.excerpt_normalized}\n{row.excerpt_original}",
                query=normalized_query,
                tokens=query_tokens,
            )
            if normalized_query and score <= 0:
                continue
            hits.append(
                {
                    "object_type": "passage",
                    "object_id": row.passage_id,
                    "score": score,
                    "snippet": snippet,
                    "review_state": row.reviewer_state.value,
                }
            )

    if "tag" in allowed_types:
        for row in db.scalars(select(RitualPatternTag)).all():
            if requested_state and row.reviewer_state != requested_state:
                continue
            if tag and row.controlled_term != tag:
                continue
            score, snippet = _score_and_snippet(
                f"{row.ontology_dimension} {row.controlled_term} {row.rationale_note or ''}",
                query=normalized_query,
                tokens=query_tokens,
            )
            if normalized_query and score <= 0:
                continue
            hits.append(
                {
                    "object_type": "tag",
                    "object_id": row.tag_id,
                    "score": score,
                    "snippet": snippet,
                    "review_state": row.reviewer_state.value,
                }
            )

    if "link" in allowed_types:
        for row in db.scalars(select(CommonalityLink)).all():
            if requested_state and row.reviewer_decision != requested_state:
                continue
            text = (
                f"{row.source_entity_id} {row.target_entity_id} "
                f"{row.relation_type.value if hasattr(row.relation_type, 'value') else row.relation_type} "
                f"{row.decision_note or ''}"
            )
            score, snippet = _score_and_snippet(text, query=normalized_query, tokens=query_tokens)
            if normalized_query and score <= 0:
                continue
            hits.append(
                {
                    "object_type": "link",
                    "object_id": row.link_id,
                    "score": score,
                    "snippet": snippet,
                    "review_state": row.reviewer_decision.value,
                }
            )

    if "flag" in allowed_types:
        for row in db.scalars(select(FlagRecord)).all():
            if requested_state and row.reviewer_state != requested_state:
                continue
            score, snippet = _score_and_snippet(
                f"{row.flag_type} {row.severity} {row.rationale}",
                query=normalized_query,
                tokens=query_tokens,
            )
            if normalized_query and score <= 0:
                continue
            hits.append(
                {
                    "object_type": "flag",
                    "object_id": row.flag_id,
                    "score": score,
                    "snippet": snippet,
                    "review_state": row.reviewer_state.value,
                }
            )

    sorted_hits = sorted(hits, key=lambda item: (-item["score"], item["object_id"]))
    return sorted_hits[: max(1, min(limit, 500))]
