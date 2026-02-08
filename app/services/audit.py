from sqlalchemy.orm import Session

from app.models.core import AuditEvent
from app.services.utils import now_utc


def emit_audit_event(
    db: Session,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    correlation_id: str,
    previous_state: str | None = None,
    new_state: str | None = None,
    metadata_blob: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        correlation_id=correlation_id,
        previous_state=previous_state,
        new_state=new_state,
        timestamp=now_utc(),
        metadata_blob=metadata_blob or {},
    )
    db.add(event)
    db.flush()
    return event

