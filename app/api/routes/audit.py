from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AuditResponse
from app.services.records import get_audit_events

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/{object_type}/{object_id}", response_model=AuditResponse)
def fetch_audit(object_type: str, object_id: str, db: Session = Depends(get_db)) -> AuditResponse:
    events = get_audit_events(db, object_type, object_id)
    return AuditResponse(object_type=object_type, object_id=object_id, events=events)

