from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SearchHit, SearchResponse
from app.services.search import search_records
from app.services.validation import ValidationError

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(default=""),
    object_type: str | None = Query(default=None, pattern="^(passage|tag|link|flag)$"),
    tag: str | None = Query(default=None),
    culture_region: str | None = Query(default=None),
    review_state: str | None = Query(default=None, pattern="^(proposed|approved|rejected|needs_revision)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> SearchResponse:
    try:
        hits = search_records(
            db,
            query=q,
            object_type=object_type,
            tag=tag,
            culture_region=culture_region,
            review_state=review_state,
            limit=limit,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SearchResponse(total=len(hits), hits=[SearchHit(**item) for item in hits])
