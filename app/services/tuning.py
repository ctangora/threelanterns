from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import TuningProfile
from app.services.quality import DEFAULT_QUALITY_CONFIG, QualityConfig


def _lines_to_set(value: str) -> set[str]:
    items: set[str] = set()
    for line in (value or "").splitlines():
        compact = line.strip().lower()
        if not compact or compact.startswith("#"):
            continue
        items.add(compact)
    return items


def _ensure_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not (0.0 <= parsed <= 1.0):
        return default
    return parsed


def _ensure_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


@dataclass(frozen=True)
class SegmentationSettings:
    min_passage_length: int = 180
    max_passages_per_source_override: int | None = None


def get_segmentation_settings(profile_snapshot_json: dict[str, Any]) -> dict[str, Any]:
    segmentation = (profile_snapshot_json or {}).get("segmentation", {}) or {}
    min_passage_length = _ensure_int(segmentation.get("min_passage_length"), default=180, minimum=1, maximum=5000)
    override_raw = segmentation.get("max_passages_per_source_override")
    override: int | None
    if override_raw in (None, "", "null"):
        override = None
    else:
        override = _ensure_int(override_raw, default=25, minimum=1, maximum=500)
    return {
        "min_passage_length": min_passage_length,
        "max_passages_per_source_override": override,
    }


def build_quality_config(profile_snapshot_json: dict[str, Any]) -> QualityConfig:
    if not profile_snapshot_json:
        return DEFAULT_QUALITY_CONFIG

    thresholds = (profile_snapshot_json.get("thresholds") or {}) if isinstance(profile_snapshot_json, dict) else {}
    lexicons = (profile_snapshot_json.get("lexicons") or {}) if isinstance(profile_snapshot_json, dict) else {}

    accept = _ensure_float(thresholds.get("relevance_accept_threshold"), default=DEFAULT_QUALITY_CONFIG.relevance_accept_threshold)
    filt = _ensure_float(thresholds.get("relevance_filter_threshold"), default=DEFAULT_QUALITY_CONFIG.relevance_filter_threshold)
    if filt > accept:
        filt = min(filt, accept)

    positive_extra = set((lexicons.get("positive_keywords") or [])) if isinstance(lexicons.get("positive_keywords"), list) else _lines_to_set(str(lexicons.get("positive_keywords") or ""))
    noise_extra = set((lexicons.get("noise_keywords") or [])) if isinstance(lexicons.get("noise_keywords"), list) else _lines_to_set(str(lexicons.get("noise_keywords") or ""))
    phrases_extra = set((lexicons.get("noise_phrases") or [])) if isinstance(lexicons.get("noise_phrases"), list) else _lines_to_set(str(lexicons.get("noise_phrases") or ""))

    positive = set(DEFAULT_QUALITY_CONFIG.positive_keywords).union({item.strip().lower() for item in positive_extra if str(item).strip()})
    noise = set(DEFAULT_QUALITY_CONFIG.noise_keywords).union({item.strip().lower() for item in noise_extra if str(item).strip()})
    phrases = set(DEFAULT_QUALITY_CONFIG.noise_phrases).union({item.strip().lower() for item in phrases_extra if str(item).strip()})

    quality_version = str(profile_snapshot_json.get("quality_version") or DEFAULT_QUALITY_CONFIG.quality_version)
    return QualityConfig(
        relevance_accept_threshold=accept,
        relevance_filter_threshold=filt,
        quality_version=quality_version,
        positive_keywords=positive,
        noise_keywords=noise,
        noise_phrases=phrases,
    )


def snapshot_profile(profile: TuningProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "quality_version": "tuning_v1",
        "thresholds": profile.thresholds_json or {},
        "lexicons": profile.lexicons_json or {},
        "segmentation": profile.segmentation_json or {},
    }


def ensure_default_profile(db: Session, *, actor: str) -> TuningProfile:
    existing_default = db.scalar(select(TuningProfile).where(TuningProfile.is_default.is_(True)))
    if existing_default is not None:
        return existing_default

    any_profile = db.scalar(select(TuningProfile).order_by(TuningProfile.created_at.asc()).limit(1))
    if any_profile is not None:
        any_profile.is_default = True
        any_profile.updated_by = actor
        db.flush()
        return any_profile

    profile = TuningProfile(
        name="Default",
        is_default=True,
        thresholds_json={
            "relevance_accept_threshold": DEFAULT_QUALITY_CONFIG.relevance_accept_threshold,
            "relevance_filter_threshold": DEFAULT_QUALITY_CONFIG.relevance_filter_threshold,
            "usability_reprocess_threshold": 0.60,
        },
        lexicons_json={
            "positive_keywords": sorted(DEFAULT_QUALITY_CONFIG.positive_keywords),
            "noise_keywords": sorted(DEFAULT_QUALITY_CONFIG.noise_keywords),
            "noise_phrases": sorted(DEFAULT_QUALITY_CONFIG.noise_phrases),
        },
        segmentation_json={
            "min_passage_length": 180,
            "max_passages_per_source_override": None,
        },
        created_by=actor,
        updated_by=actor,
    )
    db.add(profile)
    db.flush()
    return profile


def set_default_profile(db: Session, *, profile_id: str, actor: str) -> None:
    profiles = list(db.scalars(select(TuningProfile)))
    for profile in profiles:
        profile.is_default = profile.profile_id == profile_id
        profile.updated_by = actor
    db.flush()

