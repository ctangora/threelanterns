from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.enums import PublishState, RelevanceState, ReviewDecisionEnum, ReviewerState, ReviewableObjectType
from app.models.core import CommonalityLink, FlagRecord, PassageEvidence, ReviewDecision, RitualPatternTag
from app.services.audit import emit_audit_event
from app.services.validation import ValidationError, validate_review_input


def get_review_model(object_type: str):
    if object_type == "passage":
        return PassageEvidence, "passage_id", "reviewer_state"
    if object_type == "tag":
        return RitualPatternTag, "tag_id", "reviewer_state"
    if object_type == "link":
        return CommonalityLink, "link_id", "reviewer_decision"
    if object_type == "flag":
        return FlagRecord, "flag_id", "reviewer_state"
    raise ValidationError(f"Unsupported review object type: {object_type}")


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_json_safe(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(nested) for nested in value]
    return value


def _confidence_column_for_model(model):
    if model is PassageEvidence:
        return model.extraction_confidence
    if model is RitualPatternTag:
        return model.confidence
    if model is CommonalityLink:
        return model.weighted_similarity_score
    return None


def _source_column_for_model(model):
    if model is PassageEvidence:
        return model.source_id
    return None


def review_queue(
    db: Session,
    object_type: str,
    *,
    page: int = 1,
    page_size: int = 50,
    max_page_size: int = 200,
    state: str = ReviewerState.proposed.value,
    source_id: str | None = None,
    min_confidence: float | None = None,
    needs_reprocess: bool | None = None,
    max_untranslated_ratio: float | None = None,
    detected_language: str | None = None,
    min_usability: float | None = None,
    min_relevance: float | None = None,
    relevance_state: str | None = None,
    include_filtered: bool = False,
    sort_by: str = "created_at",
    sort_dir: str = "asc",
) -> dict[str, Any]:
    model, id_field, state_field = get_review_model(object_type)
    state_column = getattr(model, state_field)
    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))
    offset = (page - 1) * page_size
    try:
        requested_state = ReviewerState(state)
    except ValueError as exc:
        raise ValidationError(f"Invalid review state filter: {state}") from exc

    confidence_column = _confidence_column_for_model(model)
    source_column = _source_column_for_model(model)
    if min_confidence is not None:
        if confidence_column is None:
            raise ValidationError(f"min_confidence is not supported for object_type={object_type}")
        if not (0.0 <= min_confidence <= 1.0):
            raise ValidationError("min_confidence must be within [0.0, 1.0]")
    if source_id and source_column is None:
        raise ValidationError(f"source_id filter is not supported for object_type={object_type}")
    if needs_reprocess is not None and model is not PassageEvidence:
        raise ValidationError(f"needs_reprocess filter is not supported for object_type={object_type}")
    if max_untranslated_ratio is not None and model is not PassageEvidence:
        raise ValidationError(f"max_untranslated_ratio is not supported for object_type={object_type}")
    if detected_language and model is not PassageEvidence:
        raise ValidationError(f"detected_language filter is not supported for object_type={object_type}")
    if min_usability is not None and model is not PassageEvidence:
        raise ValidationError(f"min_usability is not supported for object_type={object_type}")
    if min_relevance is not None and model is not PassageEvidence:
        raise ValidationError(f"min_relevance is not supported for object_type={object_type}")
    if relevance_state is not None and model is not PassageEvidence:
        raise ValidationError(f"relevance_state is not supported for object_type={object_type}")
    if max_untranslated_ratio is not None and not (0.0 <= max_untranslated_ratio <= 1.0):
        raise ValidationError("max_untranslated_ratio must be within [0.0, 1.0]")
    if min_usability is not None and not (0.0 <= min_usability <= 1.0):
        raise ValidationError("min_usability must be within [0.0, 1.0]")
    if min_relevance is not None and not (0.0 <= min_relevance <= 1.0):
        raise ValidationError("min_relevance must be within [0.0, 1.0]")
    parsed_relevance_state = None
    if relevance_state is not None:
        try:
            parsed_relevance_state = RelevanceState(relevance_state)
        except ValueError as exc:
            raise ValidationError(f"Unsupported relevance_state: {relevance_state}") from exc

    if sort_by not in {"created_at", "confidence"}:
        raise ValidationError(f"Unsupported sort_by: {sort_by}")
    if sort_dir not in {"asc", "desc"}:
        raise ValidationError(f"Unsupported sort_dir: {sort_dir}")
    if sort_by == "confidence" and confidence_column is None:
        raise ValidationError(f"sort_by=confidence is not supported for object_type={object_type}")

    where_clauses = [state_column == requested_state]
    if source_id and source_column is not None:
        where_clauses.append(source_column == source_id)
    if min_confidence is not None and confidence_column is not None:
        where_clauses.append(confidence_column >= min_confidence)
    if needs_reprocess is not None and model is PassageEvidence:
        where_clauses.append(model.needs_reprocess == needs_reprocess)
    if max_untranslated_ratio is not None and model is PassageEvidence:
        where_clauses.append(model.untranslated_ratio <= max_untranslated_ratio)
    if detected_language and model is PassageEvidence:
        compact = detected_language.strip()
        where_clauses.append(
            or_(
                model.detected_language_code == compact,
                model.detected_language_label == compact,
            )
        )
    if min_usability is not None and model is PassageEvidence:
        where_clauses.append(model.usability_score >= min_usability)
    if min_relevance is not None and model is PassageEvidence:
        where_clauses.append(model.relevance_score >= min_relevance)
    if parsed_relevance_state is not None and model is PassageEvidence:
        where_clauses.append(model.relevance_state == parsed_relevance_state)
    if not include_filtered and model is PassageEvidence:
        where_clauses.append(model.relevance_state != RelevanceState.filtered)

    total_stmt = select(func.count()).select_from(model).where(*where_clauses)
    total = db.scalar(total_stmt) or 0

    if sort_by == "created_at":
        order_column = model.created_at
    else:
        order_column = confidence_column
    if order_column is None:
        raise ValidationError(f"Unable to resolve sort column for object_type={object_type}")
    sort_expression = order_column.asc() if sort_dir == "asc" else order_column.desc()

    stmt = (
        select(model)
        .where(*where_clauses)
        .order_by(sort_expression, model.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list(db.scalars(stmt))
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = {column.name: _to_json_safe(getattr(row, column.name)) for column in row.__table__.columns}
        payload["object_id"] = payload[id_field]
        items.append(payload)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": requested_state.value,
        "source_id": source_id,
        "min_confidence": min_confidence,
        "needs_reprocess": needs_reprocess,
        "max_untranslated_ratio": max_untranslated_ratio,
        "detected_language": detected_language,
        "min_usability": min_usability,
        "min_relevance": min_relevance,
        "relevance_state": parsed_relevance_state.value if parsed_relevance_state else None,
        "include_filtered": include_filtered,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


def apply_review_decision(
    db: Session,
    *,
    object_type: str,
    object_id: str,
    decision: ReviewDecisionEnum,
    notes: str | None,
    actor: str,
    correlation_id: str,
) -> ReviewDecision:
    validate_review_input(decision, notes)
    model, id_field, state_field = get_review_model(object_type)

    record = db.scalar(select(model).where(getattr(model, id_field) == object_id))
    if record is None:
        raise ValidationError(f"Object not found: {object_type}:{object_id}")

    previous_state = getattr(record, state_field).value
    if decision == ReviewDecisionEnum.approve:
        new_state_enum = ReviewerState.approved
    elif decision == ReviewDecisionEnum.reject:
        new_state_enum = ReviewerState.rejected
    else:
        new_state_enum = ReviewerState.needs_revision

    setattr(record, state_field, new_state_enum)
    if isinstance(record, PassageEvidence):
        record.publish_state = PublishState.eligible if new_state_enum == ReviewerState.approved else PublishState.blocked
    if isinstance(record, CommonalityLink):
        record.decision_note = notes
    if isinstance(record, RitualPatternTag):
        record.rationale_note = notes or record.rationale_note

    record.updated_by = actor
    review = ReviewDecision(
        object_type=ReviewableObjectType(object_type),
        object_id=object_id,
        reviewer_id=actor,
        decision=decision,
        decision_timestamp=datetime.now(UTC),
        notes=notes,
        previous_state=previous_state,
        new_state=new_state_enum.value,
        created_by=actor,
        updated_by=actor,
    )
    db.add(review)
    db.flush()

    emit_audit_event(
        db,
        actor=actor,
        action="review_decision",
        object_type=object_type,
        object_id=object_id,
        correlation_id=correlation_id,
        previous_state=previous_state,
        new_state=new_state_enum.value,
        metadata_blob={"decision": decision.value, "notes": notes},
    )
    return review


def apply_bulk_review(
    db: Session,
    *,
    object_type: str,
    object_ids: list[str],
    decision: ReviewDecisionEnum,
    notes: str | None,
    actor: str,
    correlation_id: str,
) -> list[ReviewDecision]:
    validate_review_input(decision, notes)
    deduped_ids: list[str] = []
    seen: set[str] = set()
    for object_id in object_ids:
        compact = object_id.strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        deduped_ids.append(compact)
    if not deduped_ids:
        raise ValidationError("At least one object_id is required for bulk review")

    reviews: list[ReviewDecision] = []
    for object_id in deduped_ids:
        review = apply_review_decision(
            db,
            object_type=object_type,
            object_id=object_id,
            decision=decision,
            notes=notes,
            actor=actor,
            correlation_id=f"{correlation_id}:{object_id}",
        )
        reviews.append(review)
    return reviews


def review_metrics(db: Session) -> dict[str, Any]:
    object_types = ["passage", "tag", "link", "flag"]
    backlog: dict[str, dict[str, int]] = {}
    now = datetime.now(UTC)
    proposed_ages_hours: list[float] = []

    for object_type in object_types:
        model, _, state_field = get_review_model(object_type)
        state_column = getattr(model, state_field)

        counts_stmt = select(state_column, func.count()).group_by(state_column)
        rows = db.execute(counts_stmt).all()
        state_counts = {
            ReviewerState.proposed.value: 0,
            ReviewerState.approved.value: 0,
            ReviewerState.rejected.value: 0,
            ReviewerState.needs_revision.value: 0,
        }
        for state, count in rows:
            state_value = state.value if isinstance(state, ReviewerState) else str(state)
            state_counts[state_value] = int(count)
        backlog[object_type] = state_counts

        proposed_rows = db.scalars(select(model.created_at).where(state_column == ReviewerState.proposed)).all()
        for created_at in proposed_rows:
            if created_at is None:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            age_hours = (now - created_at).total_seconds() / 3600.0
            proposed_ages_hours.append(max(age_hours, 0.0))

    decisions_24h_stmt = select(func.count()).select_from(ReviewDecision).where(
        ReviewDecision.decision_timestamp >= now - timedelta(hours=24)
    )
    decisions_24h = int(db.scalar(decisions_24h_stmt) or 0)

    average_proposed_age_hours = (
        round(sum(proposed_ages_hours) / len(proposed_ages_hours), 4) if proposed_ages_hours else 0.0
    )
    return {
        "generated_at": now,
        "backlog": backlog,
        "decisions_24h": decisions_24h,
        "average_proposed_age_hours": average_proposed_age_hours,
    }
