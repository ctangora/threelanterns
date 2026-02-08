import argparse

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.enums import JobStatus
from app.models.core import IngestionJob
from app.services.audit import emit_audit_event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Requeue dead-letter ingestion jobs")
    parser.add_argument("--job-id", help="Specific job_id to requeue")
    parser.add_argument("--all", action="store_true", help="Requeue all dead-letter jobs")
    parser.add_argument("--reason", required=True, help="Required rationale for requeue audit trail")
    return parser.parse_args()


def _select_jobs(db, *, job_id: str | None, all_jobs: bool) -> list[IngestionJob]:
    if all_jobs:
        return list(db.scalars(select(IngestionJob).where(IngestionJob.status == JobStatus.dead_letter)))
    if not job_id:
        raise SystemExit("Either --job-id or --all is required")
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise SystemExit(f"Job not found: {job_id}")
    if job.status != JobStatus.dead_letter:
        raise SystemExit(f"Job is not dead_letter: {job_id} status={job.status.value}")
    return [job]


def main() -> int:
    args = parse_args()
    settings = get_settings()

    with SessionLocal() as db:
        jobs = _select_jobs(db, job_id=args.job_id, all_jobs=args.all)
        if not jobs:
            print("No dead-letter jobs found")
            return 0

        for job in jobs:
            previous_state = job.status.value
            job.status = JobStatus.pending
            job.attempt_count = 0
            job.last_error = None
            job.error_code = None
            job.error_context_json = {"requeue_reason": args.reason}
            job.updated_by = settings.operator_id

            emit_audit_event(
                db,
                actor=settings.operator_id,
                action="job_requeued",
                object_type="job",
                object_id=job.job_id,
                correlation_id=f"requeue:{job.job_id}",
                previous_state=previous_state,
                new_state=job.status.value,
                metadata_blob={"reason": args.reason},
            )
        db.commit()

    print(f"Requeued {len(jobs)} dead-letter job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
