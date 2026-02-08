import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.database import SessionLocal
from app.enums import JobStatus, TranslationStatus
from app.models.core import IngestionJob, PassageEvidence, SourceMaterialRecord
from app.services.review import review_metrics


def main() -> int:
    with SessionLocal() as db:
        source_total = int(db.scalar(select(func.count()).select_from(SourceMaterialRecord)) or 0)
        passage_total = int(db.scalar(select(func.count()).select_from(PassageEvidence)) or 0)
        translation_quality = {
            status.value: int(
                db.scalar(select(func.count()).select_from(PassageEvidence).where(PassageEvidence.translation_status == status))
                or 0
            )
            for status in TranslationStatus
        }
        job_status_counts = {
            status.value: int(
                db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == status)) or 0
            )
            for status in JobStatus
        }
        metrics = review_metrics(db)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources_total": source_total,
        "passages_total": passage_total,
        "translation_quality": translation_quality,
        "jobs_by_status": job_status_counts,
        "review_metrics": {
            "generated_at": metrics["generated_at"].isoformat(),
            "backlog": metrics["backlog"],
            "decisions_24h": metrics["decisions_24h"],
            "average_proposed_age_hours": metrics["average_proposed_age_hours"],
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
