from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.core import IngestionJob
from app.schemas import CreateIngestJobRequest, JobResponse
from app.services.workflows.ingestion import create_ingestion_job

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("/ingest", response_model=JobResponse)
def create_job(
    request: CreateIngestJobRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    job = create_ingestion_job(
        db,
        source_id=request.source_id,
        actor=settings.operator_id,
        idempotency_key=request.idempotency_key,
        correlation_id=f"job-create:{request.source_id}",
    )
    db.commit()
    return JobResponse(
        job_id=job.job_id,
        source_id=job.source_id,
        status=job.status.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return JobResponse(
        job_id=job.job_id,
        source_id=job.source_id,
        status=job.status.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
    )

