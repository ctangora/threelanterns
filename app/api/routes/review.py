from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import (
    BulkReviewRequest,
    BulkReviewResponse,
    ReviewMetricsResponse,
    ReviewQueueResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.services.review import apply_bulk_review, apply_review_decision, review_metrics, review_queue
from app.services.validation import ValidationError

router = APIRouter(prefix="/api/v1/review", tags=["review"])


@router.get("/queue", response_model=ReviewQueueResponse)
def get_queue(
    object_type: str = Query(..., pattern="^(passage|tag|link|flag)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    state: str = Query(default="proposed", pattern="^(proposed|approved|rejected|needs_revision)$"),
    source_id: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    needs_reprocess: bool | None = Query(default=None),
    max_untranslated_ratio: float | None = Query(default=None, ge=0.0, le=1.0),
    detected_language: str | None = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(created_at|confidence)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    try:
        queue = review_queue(
            db,
            object_type,
            page=page,
            page_size=page_size,
            max_page_size=200,
            state=state,
            source_id=source_id,
            min_confidence=min_confidence,
            needs_reprocess=needs_reprocess,
            max_untranslated_ratio=max_untranslated_ratio,
            detected_language=detected_language,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReviewQueueResponse(
        object_type=object_type,
        total=queue["total"],
        page=queue["page"],
        page_size=queue["page_size"],
        items=queue["items"],
    )


@router.post("/bulk", response_model=BulkReviewResponse)
def review_bulk(
    request: BulkReviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkReviewResponse:
    try:
        reviews = apply_bulk_review(
            db,
            object_type=request.object_type,
            object_ids=request.object_ids,
            decision=request.decision,
            notes=request.notes,
            actor=settings.operator_id,
            correlation_id=f"review-bulk:{request.object_type}",
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return BulkReviewResponse(
        object_type=request.object_type,
        decision=request.decision.value,
        requested=len(request.object_ids),
        processed=len(reviews),
        review_ids=[item.review_id for item in reviews],
    )


@router.get("/metrics", response_model=ReviewMetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> ReviewMetricsResponse:
    metrics = review_metrics(db)
    return ReviewMetricsResponse(
        generated_at=metrics["generated_at"],
        backlog=metrics["backlog"],
        decisions_24h=metrics["decisions_24h"],
        average_proposed_age_hours=metrics["average_proposed_age_hours"],
    )


@router.post("/{object_type}/{object_id}", response_model=ReviewResponse)
def review_object(
    object_type: str,
    object_id: str,
    request: ReviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    try:
        review = apply_review_decision(
            db,
            object_type=object_type,
            object_id=object_id,
            decision=request.decision,
            notes=request.notes,
            actor=settings.operator_id,
            correlation_id=f"review:{object_type}:{object_id}",
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return ReviewResponse(
        review_id=review.review_id,
        object_type=object_type,
        object_id=object_id,
        decision=review.decision.value,
        new_state=review.new_state or "",
    )
