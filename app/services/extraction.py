from sqlalchemy.orm import Session

from app.constants import LANGUAGE_NORMALIZED_CANONICAL
from app.enums import PublishState, ReviewerState
from app.models.core import PassageEvidence
from app.services.utils import guess_language_code, normalize_to_english, split_into_passages
from app.services.validation import validate_confidence, require


def build_passage_evidence(
    db: Session,
    *,
    text_id: str,
    source_id: str,
    content: str,
    actor: str,
    max_passages: int,
) -> list[PassageEvidence]:
    passages = split_into_passages(content)
    passages = passages[:max_passages]
    created: list[PassageEvidence] = []

    for index, passage in enumerate(passages, start=1):
        original_lang = guess_language_code(passage)
        normalized = normalize_to_english(passage)
        confidence = 0.9 if original_lang == "eng" else 0.72
        validate_confidence(confidence, "extraction_confidence")
        require(bool(normalized), "Normalized passage cannot be empty")

        evidence = PassageEvidence(
            text_id=text_id,
            source_id=source_id,
            source_span_locator=f"segment_{index}",
            excerpt_original=passage,
            excerpt_normalized=normalized,
            original_language=original_lang,
            normalized_language=LANGUAGE_NORMALIZED_CANONICAL,
            extraction_confidence=confidence,
            reviewer_state=ReviewerState.proposed,
            publish_state=PublishState.blocked,
            created_by=actor,
            updated_by=actor,
        )
        db.add(evidence)
        created.append(evidence)

    db.flush()
    return created
