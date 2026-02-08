from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import PublishState, ReviewDecisionEnum, ReviewerState, ReviewableObjectType
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


def review_queue(
    db: Session,
    object_type: str,
    *,
    page: int = 1,
    page_size: int = 50,
    max_page_size: int = 200,
) -> dict[str, Any]:
    model, id_field, state_field = get_review_model(object_type)
    state_column = getattr(model, state_field)
    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))
    offset = (page - 1) * page_size

    total_stmt = select(func.count()).select_from(model).where(state_column == ReviewerState.proposed)
    total = db.scalar(total_stmt) or 0

    stmt = (
        select(model)
        .where(state_column == ReviewerState.proposed)
        .order_by(model.created_at.asc())
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
