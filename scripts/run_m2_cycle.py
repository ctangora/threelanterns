from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.models.core import IngestionJob, SourceMaterialRecord
from app.schemas import RegisterRequest
from app.services.intake import discover_local_sources, register_source
from app.services.workflows.ingestion import create_ingestion_job, run_worker_cycle


def main() -> int:
    settings = get_settings()
    discovered = discover_local_sources(max_files=25, root_path=str(settings.ingest_root))
    if len(discovered) != 25:
        print(f"warning: expected 25 discoverable files, found {len(discovered)}")

    with SessionLocal() as db:
        for item in discovered:
            register_req = RegisterRequest(
                source_path=item.path,
                rights_status="public_domain",
                rights_evidence="Local reference corpus",
                provenance_summary="Milestone 2 runbook registration",
                holding_institution="Local Reference Library",
                accession_or_citation=item.path,
                source_provenance_note="Imported from __Reference__",
            )
            _, source = register_source(
                db,
                register_req,
                actor=settings.operator_id,
                correlation_id=f"seed-register:{item.path}",
            )
            create_ingestion_job(
                db,
                source_id=source.source_id,
                actor=settings.operator_id,
                idempotency_key=f"seed-job:{source.source_id}",
                correlation_id=f"seed-job-create:{source.source_id}",
            )
        db.commit()

    while True:
        with SessionLocal() as db:
            job = run_worker_cycle(db, actor=settings.operator_id)
            db.commit()
            if job is None:
                break

    with SessionLocal() as db:
        sources = db.scalar(select(func.count()).select_from(SourceMaterialRecord))
        jobs = db.scalar(select(func.count()).select_from(IngestionJob))
        print(f"sources={sources}, jobs={jobs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
