from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RecordResponse
from app.services.records import get_record
from app.services.validation import ValidationError

router = APIRouter(prefix="/api/v1/records", tags=["records"])


@router.get("/{object_type}/{object_id}", response_model=RecordResponse)
def fetch_record(object_type: str, object_id: str, db: Session = Depends(get_db)) -> RecordResponse:
    try:
        payload = get_record(db, object_type, object_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RecordResponse(object_type=object_type, object_id=object_id, payload=payload)

