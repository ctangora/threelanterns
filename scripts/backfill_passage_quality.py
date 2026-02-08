from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.core import PassageEvidence
from app.services.quality import evaluate_passage_quality


def main() -> int:
    settings = get_settings()
    updated = 0
    with SessionLocal() as db:
        passages = list(db.scalars(select(PassageEvidence)))
        for passage in passages:
            quality = evaluate_passage_quality(passage.excerpt_normalized or passage.excerpt_original)
            passage.usability_score = quality.usability_score
            passage.relevance_score = quality.relevance_score
            passage.relevance_state = quality.relevance_state
            passage.quality_notes_json = quality.notes
            passage.quality_version = quality.quality_version
            passage.updated_by = settings.operator_id
            updated += 1
        db.commit()
    print(f"backfilled quality for {updated} passage(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
