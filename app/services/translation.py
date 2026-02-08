from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import LANGUAGE_LABELS, TRANSLATION_UNTRANSLATED_RATIO_THRESHOLD
from app.enums import TranslationStatus
from app.models.core import ProposalTrace
from app.services.utils import guess_language_code, normalize_to_english
from app.services.validation import ValidationError, require

_ARCHAIC_PATTERNS = [
    (re.compile(r"\bthou\b", re.IGNORECASE), "you"),
    (re.compile(r"\bthee\b", re.IGNORECASE), "you"),
    (re.compile(r"\bthy\b", re.IGNORECASE), "your"),
    (re.compile(r"\bthine\b", re.IGNORECASE), "yours"),
    (re.compile(r"\bhath\b", re.IGNORECASE), "has"),
    (re.compile(r"\bdoth\b", re.IGNORECASE), "does"),
    (re.compile(r"\bart\b", re.IGNORECASE), "are"),
]

_ARCHAIC_MARKERS = ("þ", "ð", "æ", "hwæt", "thou", "hath", "doth", "yclept", "whan", "ye ")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9'-]+")
_PROTECTED_TOKENS = {
    "ritual",
    "psalm",
    "oracle",
    "amulet",
    "sigil",
    "incantation",
    "liturgy",
}
_STOP_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "upon",
    "unto",
    "are",
    "was",
    "were",
    "shall",
    "should",
    "would",
    "could",
}
_ENGLISH_HINT_TOKENS = _STOP_TOKENS.union(
    {
        "ritual",
        "invocation",
        "offering",
        "circle",
        "boundary",
        "dawn",
        "night",
        "ceremony",
        "chant",
        "blessing",
        "protection",
        "healing",
        "passage",
        "modern",
        "language",
        "oracle",
        "sacred",
        "altar",
        "prayer",
        "spirit",
        "water",
        "fire",
        "temple",
        "household",
        "scribe",
        "oath",
        "vow",
        "offered",
    }
)


class TranslationPayload(BaseModel):
    modern_english_text: str = Field(min_length=1)
    detected_language_code: str = Field(min_length=2, max_length=12)
    detected_language_label: str = Field(min_length=2, max_length=120)
    language_detection_confidence: float = Field(ge=0.0, le=1.0)


@dataclass
class TranslationResult:
    modern_english_text: str
    detected_language_code: str
    detected_language_label: str
    language_detection_confidence: float
    untranslated_ratio: float
    translation_status: TranslationStatus
    needs_reprocess: bool
    translation_provider: str
    trace_id: str


def _language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code.lower(), "Undetermined")


def _detect_english_variant(text: str) -> tuple[str, str, float]:
    lowered = text.lower()
    if any(marker in lowered for marker in _ARCHAIC_MARKERS):
        if any(marker in lowered for marker in ("þ", "ð", "hwæt", "iclept", "ge-")):
            return "ang", _language_label("ang"), 0.9
        return "enm", _language_label("enm"), 0.76

    guessed = guess_language_code(text)
    if guessed == "eng":
        tokens = [token for token in _tokens(text) if len(token) > 2]
        if tokens:
            english_hits = sum(1 for token in tokens if token in _ENGLISH_HINT_TOKENS)
            hit_ratio = english_hits / len(tokens)
            if hit_ratio < 0.28:
                return "und", _language_label("und"), 0.58
        return "eng", _language_label("eng"), 0.88
    return guessed, _language_label(guessed), 0.64


def _mock_translate(excerpt: str) -> TranslationPayload:
    normalized = normalize_to_english(excerpt)
    detected_code, detected_label, confidence = _detect_english_variant(normalized)
    modern = normalized
    if detected_code in {"ang", "enm"}:
        for pattern, replacement in _ARCHAIC_PATTERNS:
            modern = pattern.sub(replacement, modern)
    modern = normalize_to_english(modern)
    return TranslationPayload(
        modern_english_text=modern or normalized,
        detected_language_code=detected_code,
        detected_language_label=detected_label,
        language_detection_confidence=confidence,
    )


def _translation_prompt(excerpt: str, *, source_variant: str, reference_context: str | None) -> str:
    reference_block = reference_context.strip() if reference_context else "None"
    return (
        "Translate the source passage into clear modern English.\n"
        "Return strictly JSON with keys:\n"
        "- modern_english_text\n"
        "- detected_language_code\n"
        "- detected_language_label\n"
        "- language_detection_confidence\n"
        "Do not include markdown or extra keys.\n"
        f"Source variant: {source_variant}\n"
        f"External references: {reference_block}\n"
        "Source passage:\n"
        f"{excerpt[:6000]}\n"
    )


def _translation_repair_prompt(*, original_prompt: str, raw_response: str, error: str) -> str:
    return (
        "Repair this output into strictly valid JSON for the required translation schema.\n"
        "Return JSON only.\n"
        f"Original prompt:\n{original_prompt}\n"
        f"Invalid response:\n{raw_response}\n"
        f"Validation error:\n{error}\n"
    )


def _openai_json_completion(*, prompt: str, client: OpenAI, model: str) -> tuple[str, dict[str, Any]]:
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    usage = {
        "prompt_tokens": getattr(completion.usage, "prompt_tokens", None),
        "completion_tokens": getattr(completion.usage, "completion_tokens", None),
        "total_tokens": getattr(completion.usage, "total_tokens", None),
    }
    return raw, usage


def _parse_payload(raw: str) -> TranslationPayload:
    return TranslationPayload.model_validate(json.loads(raw))


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


def _is_ignorable_ratio_token(token: str) -> bool:
    if len(token) < 3:
        return True
    if token.isdigit():
        return True
    if token in _PROTECTED_TOKENS:
        return True
    if token in _STOP_TOKENS:
        return True
    return False


def compute_untranslated_ratio(source_text: str, translated_text: str, *, detected_language_code: str) -> float:
    normalized_translation = normalize_to_english(translated_text)
    if not normalized_translation:
        return 1.0

    language_code = (detected_language_code or "und").lower()
    if language_code == "eng":
        return 0.0

    source_tokens = [token for token in _tokens(source_text) if not _is_ignorable_ratio_token(token)]
    if not source_tokens:
        return 0.0
    translated_tokens = set(_tokens(normalized_translation))

    untranslated_count = sum(1 for token in source_tokens if token in translated_tokens)
    ratio = untranslated_count / max(len(source_tokens), 1)
    bounded = max(0.0, min(1.0, ratio))
    return round(bounded, 4)


def decision_for_ratio(untranslated_ratio: float) -> TranslationStatus:
    if untranslated_ratio > TRANSLATION_UNTRANSLATED_RATIO_THRESHOLD:
        return TranslationStatus.needs_reprocess
    return TranslationStatus.translated


def _create_translation_trace(
    db: Session,
    *,
    passage_id: str,
    idempotency_key: str,
    prompt: str,
    response_body: str,
    usage_blob: dict[str, Any],
    retry_count: int,
    failure_reason: str | None,
    actor: str,
) -> ProposalTrace:
    settings = get_settings()
    trace = ProposalTrace(
        object_type="passage",
        object_id=passage_id,
        proposal_type="translation",
        idempotency_key=idempotency_key,
        model_name=settings.openai_model if not settings.use_mock_ai else "mock_translation",
        prompt_version=f"{settings.openai_prompt_version}:translation_v1",
        prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        response_hash=sha256(response_body.encode("utf-8")).hexdigest(),
        raw_response_hash=sha256(response_body.encode("utf-8")).hexdigest(),
        usage_blob=usage_blob,
        retry_count=retry_count,
        failure_reason=failure_reason,
        created_by=actor,
        updated_by=actor,
    )
    db.add(trace)
    db.flush()
    return trace


def translate_passage_excerpt(
    db: Session,
    *,
    passage_id: str,
    excerpt: str,
    actor: str,
    idempotency_key: str,
    source_variant: str,
    reference_context: str | None = None,
) -> TranslationResult:
    settings = get_settings()
    prompt = _translation_prompt(excerpt, source_variant=source_variant, reference_context=reference_context)

    retry_count = 0
    failure_reason: str | None = None
    usage: dict[str, Any]
    payload: TranslationPayload
    raw_response: str
    provider = "openai"

    if settings.use_mock_ai:
        provider = "mock_translation"
        payload = _mock_translate(excerpt)
        raw_response = payload.model_dump_json()
        usage = {"mode": "mock_translation"}
    else:
        client = OpenAI(api_key=settings.openai_api_key)
        raw_attempt_1 = ""
        raw_attempt_2 = ""
        usage_attempts: list[dict[str, Any]] = []
        try:
            raw_attempt_1, usage_1 = _openai_json_completion(prompt=prompt, client=client, model=settings.openai_model)
            usage_attempts.append({"attempt": 1, **usage_1})
            payload = _parse_payload(raw_attempt_1)
            raw_response = raw_attempt_1
            usage = {"mode": "openai_translation", "attempts": usage_attempts}
        except Exception as first_exc:
            retry_count = 1
            repair_prompt = _translation_repair_prompt(
                original_prompt=prompt,
                raw_response=raw_attempt_1 or "{}",
                error=f"{first_exc.__class__.__name__}: {first_exc}",
            )
            try:
                raw_attempt_2, usage_2 = _openai_json_completion(
                    prompt=repair_prompt,
                    client=client,
                    model=settings.openai_model,
                )
                usage_attempts.append({"attempt": 2, **usage_2})
                payload = _parse_payload(raw_attempt_2)
                raw_response = raw_attempt_2
                usage = {"mode": "openai_translation_repair", "attempts": usage_attempts}
            except Exception as second_exc:
                failure_reason = (
                    "translation_output_validation_failed: "
                    f"attempt1={first_exc.__class__.__name__}: {first_exc}; "
                    f"attempt2={second_exc.__class__.__name__}: {second_exc}"
                )
                raw_response = raw_attempt_2 or raw_attempt_1 or "{}"
                usage = {
                    "mode": "openai_translation_failed",
                    "attempts": usage_attempts,
                    "initial_error": f"{first_exc.__class__.__name__}: {first_exc}",
                    "repair_error": f"{second_exc.__class__.__name__}: {second_exc}",
                }
                _create_translation_trace(
                    db,
                    passage_id=passage_id,
                    idempotency_key=idempotency_key,
                    prompt=prompt,
                    response_body=raw_response,
                    usage_blob=usage,
                    retry_count=retry_count,
                    failure_reason=failure_reason,
                    actor=actor,
                )
                raise ValidationError(f"Translation failed for passage {passage_id}") from second_exc

    translated = normalize_to_english(payload.modern_english_text)
    require(bool(translated), "Translated excerpt cannot be empty")
    detected_code = payload.detected_language_code.strip().lower() or "und"
    detected_label = payload.detected_language_label.strip() or _language_label(detected_code)
    untranslated_ratio = compute_untranslated_ratio(excerpt, translated, detected_language_code=detected_code)
    translation_status = decision_for_ratio(untranslated_ratio)
    needs_reprocess = translation_status == TranslationStatus.needs_reprocess

    trace = _create_translation_trace(
        db,
        passage_id=passage_id,
        idempotency_key=idempotency_key,
        prompt=prompt,
        response_body=raw_response,
        usage_blob={
            **usage,
            "source_variant": source_variant,
            "untranslated_ratio": untranslated_ratio,
        },
        retry_count=retry_count,
        failure_reason=failure_reason,
        actor=actor,
    )
    return TranslationResult(
        modern_english_text=translated,
        detected_language_code=detected_code,
        detected_language_label=detected_label,
        language_detection_confidence=payload.language_detection_confidence,
        untranslated_ratio=untranslated_ratio,
        translation_status=translation_status,
        needs_reprocess=needs_reprocess,
        translation_provider=provider,
        trace_id=trace.trace_id,
    )
