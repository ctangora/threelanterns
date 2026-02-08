from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.enums import ReprocessTriggerMode
from app.schemas import PassageQualityResponse, PassageReprocessRequest, PassageReprocessResponse
from app.services.validation import ValidationError
from app.services.workflows.reprocess import enqueue_reprocess_job, get_passage_quality

router = APIRouter(prefix="/api/v1/passages", tags=["passages"])


@router.post("/{passage_id}/reprocess", response_model=PassageReprocessResponse)
def reprocess_passage(
    passage_id: str,
    request: PassageReprocessRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PassageReprocessResponse:
    trigger_mode = ReprocessTriggerMode.manual if request.mode == "manual" else ReprocessTriggerMode.auto_threshold
    try:
        job = enqueue_reprocess_job(
            db,
            passage_id=passage_id,
            actor=settings.operator_id,
            trigger_mode=trigger_mode,
            reason=request.reason,
            reason_code=request.reason_code,
            reason_note=request.reason_note,
            correlation_id=f"api-reprocess:{passage_id}:{trigger_mode.value}",
        )
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return PassageReprocessResponse(
        reprocess_job_id=job.reprocess_job_id,
        passage_id=job.passage_id,
        status=job.status.value,
        trigger_mode=job.trigger_mode.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
    )


@router.get("/{passage_id}/quality", response_model=PassageQualityResponse)
def passage_quality(
    passage_id: str,
    db: Session = Depends(get_db),
) -> PassageQualityResponse:
    try:
        payload = get_passage_quality(db, passage_id=passage_id)
    except ValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PassageQualityResponse(**payload)
