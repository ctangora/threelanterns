from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import JobStatus
from app.models.core import AuditEvent, IngestionJob, PassageReprocessJob
from app.schemas import HealthDetailsResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(UTC))


@router.get("/health/details", response_model=HealthDetailsResponse)
def health_details(db: Session = Depends(get_db)) -> HealthDetailsResponse:
    db.execute(select(1))
    queue_depth = {
        status.value: int(db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == status)) or 0)
        for status in JobStatus
    }
    reprocess_depth = {
        f"reprocess_{status.value}": int(
            db.scalar(select(func.count()).select_from(PassageReprocessJob).where(PassageReprocessJob.status == status)) or 0
        )
        for status in JobStatus
    }
    queue_depth.update(reprocess_depth)
    last_activity = db.scalar(
        select(func.max(AuditEvent.timestamp)).where(
            AuditEvent.object_type == "job",
            AuditEvent.action.in_(["job_claimed", "job_completed", "job_failed"]),
        )
    )
    dead_letter_jobs = queue_depth.get(JobStatus.dead_letter.value, 0) + queue_depth.get("reprocess_dead_letter", 0)
    return HealthDetailsResponse(
        status="ok",
        timestamp=datetime.now(UTC),
        database_ok=True,
        queue_depth=queue_depth,
        dead_letter_jobs=dead_letter_jobs,
        worker_last_activity_at=last_activity,
    )
