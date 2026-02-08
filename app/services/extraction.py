from sqlalchemy.orm import Session

from app.constants import LANGUAGE_LABELS, LANGUAGE_NORMALIZED_CANONICAL, PASSAGE_QUALITY_VERSION
from app.enums import PublishState, ReviewerState, TranslationStatus
from app.models.base import prefixed_id
from app.models.core import PassageEvidence
from app.services.quality import evaluate_passage_quality
from app.services.translation import translate_passage_excerpt
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
    translation_idempotency_root: str,
) -> list[PassageEvidence]:
    passages = split_into_passages(content)
    passages = passages[:max_passages]
    created: list[PassageEvidence] = []

    for index, passage in enumerate(passages, start=1):
        passage_id = prefixed_id("psg")
        quality = evaluate_passage_quality(passage)
        if quality.relevance_state.value == "filtered":
            detected_language_code = guess_language_code(passage)
            detected_language_label = LANGUAGE_LABELS.get(detected_language_code, "Undetermined")
            normalized_excerpt = normalize_to_english(passage)
            translation_status = TranslationStatus.translated
            untranslated_ratio = 0.0
            needs_reprocess = False
            translation_provider = "skipped_low_relevance"
            translation_trace_id = None
            language_detection_confidence = 0.52
        else:
            translation = translate_passage_excerpt(
                db,
                passage_id=passage_id,
                excerpt=passage,
                actor=actor,
                idempotency_key=f"{translation_idempotency_root}:{passage_id}:{index}",
                source_variant="original_parse",
            )
            normalized_excerpt = translation.modern_english_text
            detected_language_code = translation.detected_language_code
            detected_language_label = translation.detected_language_label
            language_detection_confidence = translation.language_detection_confidence
            translation_status = translation.translation_status
            untranslated_ratio = translation.untranslated_ratio
            needs_reprocess = translation.needs_reprocess
            translation_provider = translation.translation_provider
            translation_trace_id = translation.trace_id

        confidence = 0.9 if detected_language_code == "eng" else 0.74
        validate_confidence(confidence, "extraction_confidence")
        require(bool(normalized_excerpt), "Normalized passage cannot be empty")

        evidence = PassageEvidence(
            passage_id=passage_id,
            text_id=text_id,
            source_id=source_id,
            source_span_locator=f"segment_{index}",
            excerpt_original=passage,
            excerpt_normalized=normalized_excerpt,
            original_language=detected_language_code,
            normalized_language=LANGUAGE_NORMALIZED_CANONICAL,
            extraction_confidence=confidence,
            reviewer_state=ReviewerState.proposed,
            publish_state=PublishState.blocked,
            translation_status=translation_status,
            detected_language_code=detected_language_code,
            detected_language_label=detected_language_label,
            language_detection_confidence=language_detection_confidence,
            untranslated_ratio=untranslated_ratio,
            needs_reprocess=needs_reprocess,
            reprocess_count=0,
            translation_provider=translation_provider,
            translation_trace_id=translation_trace_id,
            usability_score=quality.usability_score,
            relevance_score=quality.relevance_score,
            relevance_state=quality.relevance_state,
            quality_notes_json=quality.notes,
            quality_version=PASSAGE_QUALITY_VERSION,
            created_by=actor,
            updated_by=actor,
        )
        db.add(evidence)
        created.append(evidence)

    db.flush()
    return created
