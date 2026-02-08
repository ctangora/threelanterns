from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import ReviewQueueResponse, ReviewRequest, ReviewResponse
from app.services.review import apply_review_decision, review_queue
from app.services.validation import ValidationError

router = APIRouter(prefix="/api/v1/review", tags=["review"])


@router.get("/queue", response_model=ReviewQueueResponse)
def get_queue(
    object_type: str = Query(..., pattern="^(passage|tag|link|flag)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    try:
        queue = review_queue(db, object_type, page=page, page_size=page_size, max_page_size=200)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReviewQueueResponse(
        object_type=object_type,
        total=queue["total"],
        page=queue["page"],
        page_size=queue["page_size"],
        items=queue["items"],
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
