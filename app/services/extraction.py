from sqlalchemy.orm import Session

from app.constants import LANGUAGE_NORMALIZED_CANONICAL
from app.enums import PublishState, ReviewerState
from app.models.base import prefixed_id
from app.models.core import PassageEvidence
from app.services.translation import translate_passage_excerpt
from app.services.utils import split_into_passages
from app.services.validation import validate_confidence, require


def build_passage_evidence(
    db: Session,
    *,
    text_id: str,
    source_id: str,
    content: str,
    actor: str,
    max_passages: int,
    translation_idempotency_root: str,
) -> list[PassageEvidence]:
    passages = split_into_passages(content)
    passages = passages[:max_passages]
    created: list[PassageEvidence] = []

    for index, passage in enumerate(passages, start=1):
        passage_id = prefixed_id("psg")
        translation = translate_passage_excerpt(
            db,
            passage_id=passage_id,
            excerpt=passage,
            actor=actor,
            idempotency_key=f"{translation_idempotency_root}:{passage_id}:{index}",
            source_variant="original_parse",
        )
        confidence = 0.9 if translation.detected_language_code == "eng" else 0.74
        validate_confidence(confidence, "extraction_confidence")
        require(bool(translation.modern_english_text), "Normalized passage cannot be empty")

        evidence = PassageEvidence(
            passage_id=passage_id,
            text_id=text_id,
            source_id=source_id,
            source_span_locator=f"segment_{index}",
            excerpt_original=passage,
            excerpt_normalized=translation.modern_english_text,
            original_language=translation.detected_language_code,
            normalized_language=LANGUAGE_NORMALIZED_CANONICAL,
            extraction_confidence=confidence,
            reviewer_state=ReviewerState.proposed,
            publish_state=PublishState.blocked,
            translation_status=translation.translation_status,
            detected_language_code=translation.detected_language_code,
            detected_language_label=translation.detected_language_label,
            language_detection_confidence=translation.language_detection_confidence,
            untranslated_ratio=translation.untranslated_ratio,
            needs_reprocess=translation.needs_reprocess,
            reprocess_count=0,
            translation_provider=translation.translation_provider,
            translation_trace_id=translation.trace_id,
            created_by=actor,
            updated_by=actor,
        )
        db.add(evidence)
        created.append(evidence)

    db.flush()
    return created
