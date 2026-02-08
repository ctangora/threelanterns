from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.enums import JobStatus
from app.models.core import IngestionJob, SourceMaterialRecord
from app.schemas import RegisterRequest
from app.services.intake import discover_local_sources, register_source_with_outcome
from app.services.workflows.ingestion import create_ingestion_job, run_worker_cycle


def main() -> int:
    settings = get_settings()
    discovered = discover_local_sources(max_files=100, root_path=str(settings.ingest_root))
    if len(discovered) < 100:
        print(f"warning: expected up to 100 discoverable files, found {len(discovered)}")

    with SessionLocal() as db:
        for item in discovered:
            register_req = RegisterRequest(
                source_path=item.path,
                rights_status="public_domain",
                rights_evidence="Local reference corpus",
                provenance_summary="Release 3 intake run",
                holding_institution="Local Reference Library",
                accession_or_citation=item.path,
                source_provenance_note="Imported from __Reference__",
            )
            outcome = register_source_with_outcome(
                db,
                register_req,
                actor=settings.operator_id,
                correlation_id=f"r3a-register:{item.path}",
            )
            create_ingestion_job(
                db,
                source_id=outcome.source.source_id,
                actor=settings.operator_id,
                idempotency_key=f"r3a-job:{outcome.source.source_id}",
                correlation_id=f"r3a-job-create:{outcome.source.source_id}",
            )
        db.commit()

    while True:
        with SessionLocal() as db:
            job = run_worker_cycle(db, actor=settings.operator_id)
            db.commit()
            if job is None:
                break

    with SessionLocal() as db:
        sources_total = int(db.scalar(select(func.count()).select_from(SourceMaterialRecord)) or 0)
        jobs_total = int(db.scalar(select(func.count()).select_from(IngestionJob)) or 0)
        completed = int(
            db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == JobStatus.completed)) or 0
        )
        failed = int(
            db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == JobStatus.dead_letter)) or 0
        )
    success_rate = round((completed / jobs_total) * 100, 2) if jobs_total else 0.0
    print(f"sources={sources_total} jobs={jobs_total} completed={completed} dead_letter={failed} success_rate={success_rate}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
