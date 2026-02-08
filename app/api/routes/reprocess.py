from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ReprocessJobQueueResponse, ReprocessReasonSummaryItem, ReprocessReasonSummaryResponse
from app.services.validation import ValidationError
from app.services.workflows.reprocess import list_reprocess_jobs, reprocess_reason_summary

router = APIRouter(prefix="/api/v1/reprocess", tags=["reprocess"])


@router.get("/jobs", response_model=ReprocessJobQueueResponse)
def reprocess_jobs(
    status: str | None = Query(default=None, pattern="^(pending|running|completed|failed|dead_letter)$"),
    trigger_mode: str | None = Query(default=None, pattern="^(manual|auto_threshold)$"),
    reason_code: str | None = Query(default=None),
    passage_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReprocessJobQueueResponse:
    try:
        payload = list_reprocess_jobs(
            db,
            status=status,
            trigger_mode=trigger_mode,
            reason_code=reason_code,
            passage_id=passage_id,
            page=page,
            page_size=page_size,
            max_page_size=200,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReprocessJobQueueResponse(
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        items=payload["items"],
    )


@router.get("/reasons/summary", response_model=ReprocessReasonSummaryResponse)
def reasons_summary(db: Session = Depends(get_db)) -> ReprocessReasonSummaryResponse:
    items = [ReprocessReasonSummaryItem(**row) for row in reprocess_reason_summary(db)]
    return ReprocessReasonSummaryResponse(items=items)
