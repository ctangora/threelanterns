from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import prefixed_id
from app.models.core import IngestionJob, PassageEvidence, SourceMaterialRecord, TextRecord, TuningProfile, TuningRun, TuningRunPassage
from app.services.parsers import parse_source_file_with_metadata
from app.services.quality import evaluate_passage_quality
from app.services.tuning import build_quality_config, ensure_default_profile, get_segmentation_settings, snapshot_profile
from app.services.utils import split_into_passages
from app.services.validation import ValidationError, require
from app.services.workflows.ingestion import create_ingestion_job


def _histogram(values: list[float], *, buckets: int = 10) -> list[int]:
    counts = [0 for _ in range(buckets)]
    for value in values:
        idx = int(min(max(value, 0.0), 0.9999) * buckets)
        counts[idx] += 1
    return counts


def _source_snapshot(db: Session, *, source_id: str) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id)) or 0
    accepted = db.scalar(
        select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "accepted")
    ) or 0
    borderline = db.scalar(
        select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "borderline")
    ) or 0
    filtered = db.scalar(
        select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "filtered")
    ) or 0
    avg_usability = db.scalar(select(func.avg(PassageEvidence.usability_score)).where(PassageEvidence.source_id == source_id)) or 0.0
    avg_relevance = db.scalar(select(func.avg(PassageEvidence.relevance_score)).where(PassageEvidence.source_id == source_id)) or 0.0
    avg_ratio = db.scalar(select(func.avg(PassageEvidence.untranslated_ratio)).where(PassageEvidence.source_id == source_id)) or 0.0
    needs_reprocess = db.scalar(
        select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.needs_reprocess.is_(True))
    ) or 0
    return {
        "total": int(total),
        "accepted": int(accepted),
        "borderline": int(borderline),
        "filtered": int(filtered),
        "avg_usability": round(float(avg_usability or 0.0), 4),
        "avg_relevance": round(float(avg_relevance or 0.0), 4),
        "avg_untranslated_ratio": round(float(avg_ratio or 0.0), 4),
        "needs_reprocess": int(needs_reprocess),
    }


@dataclass(frozen=True)
class PreviewResult:
    run: TuningRun
    items: list[TuningRunPassage]
    summary: dict[str, Any]


def create_tuning_preview_run(
    db: Session,
    *,
    source_id: str,
    profile_id: str | None,
    parser_strategy: str,
    actor: str,
) -> PreviewResult:
    source = db.get(SourceMaterialRecord, source_id)
    require(source is not None, f"Source not found: {source_id}")

    if profile_id:
        profile = db.get(TuningProfile, profile_id)
        require(profile is not None, f"Profile not found: {profile_id}")
    else:
        profile = ensure_default_profile(db, actor=actor)

    snapshot = snapshot_profile(profile)
    run = TuningRun(
        run_id=prefixed_id("trn"),
        source_id=source_id,
        profile_id=profile.profile_id,
        profile_snapshot_json=snapshot,
        parser_strategy=parser_strategy or "auto_by_extension",
        mode="preview",
        ai_enabled=False,
        external_refs_enabled=False,
        status="running",
        summary_json={},
        created_by=actor,
        updated_by=actor,
    )
    db.add(run)
    db.flush()

    quality_config = build_quality_config(snapshot)
    segmentation = get_segmentation_settings(snapshot)
    path = Path(source.source_path)
    parse_result = parse_source_file_with_metadata(path, parser_strategy=parser_strategy)
    raw_text = parse_result["text"]
    passages = split_into_passages(raw_text, minimum_length=segmentation["min_passage_length"])

    items: list[TuningRunPassage] = []
    usability_values: list[float] = []
    relevance_values: list[float] = []
    counts = {"accepted": 0, "borderline": 0, "filtered": 0}
    for ordinal, excerpt in enumerate(passages, start=1):
        quality = evaluate_passage_quality(excerpt, config=quality_config)
        state = quality.relevance_state.value
        counts[state] += 1
        usability_values.append(quality.usability_score)
        relevance_values.append(quality.relevance_score)
        item = TuningRunPassage(
            run_id=run.run_id,
            ordinal=ordinal,
            excerpt_original=excerpt,
            usability_score=quality.usability_score,
            relevance_score=quality.relevance_score,
            relevance_state=state,
            quality_notes_json=quality.notes,
            created_by=actor,
            updated_by=actor,
        )
        db.add(item)
        items.append(item)

    # Deltas by ordinal vs existing segments.
    existing = list(db.scalars(select(PassageEvidence).where(PassageEvidence.source_id == source_id)))
    existing_by_ordinal: dict[int, PassageEvidence] = {}
    for row in existing:
        if row.source_span_locator.startswith("segment_"):
            try:
                ordinal = int(row.source_span_locator.split("_", 1)[1])
            except ValueError:
                continue
            existing_by_ordinal[ordinal] = row

    newly_accepted: list[dict[str, Any]] = []
    newly_filtered: list[dict[str, Any]] = []
    for item in items:
        previous = existing_by_ordinal.get(item.ordinal)
        prev_state = getattr(previous.relevance_state, "value", str(previous.relevance_state)) if previous else None
        if prev_state != item.relevance_state and item.relevance_state == "accepted":
            newly_accepted.append({"ordinal": item.ordinal, "prev": prev_state, "excerpt": item.excerpt_original[:400]})
        if prev_state != item.relevance_state and item.relevance_state == "filtered":
            newly_filtered.append({"ordinal": item.ordinal, "prev": prev_state, "excerpt": item.excerpt_original[:400]})

    summary = {
        "source_snapshot": _source_snapshot(db, source_id=source_id),
        "preview_counts": counts,
        "preview_histograms": {
            "usability": _histogram(usability_values),
            "relevance": _histogram(relevance_values),
        },
        "newly_accepted": newly_accepted[:20],
        "newly_filtered": newly_filtered[:20],
        "parser": {
            "parser_name": parse_result.get("parser_name"),
            "parser_version": parse_result.get("parser_version"),
            "parser_strategy": parse_result.get("parser_strategy"),
        },
    }
    run.status = "completed"
    run.summary_json = summary
    run.updated_by = actor
    db.flush()
    return PreviewResult(run=run, items=items, summary=summary)


def create_tuning_apply_run(
    db: Session,
    *,
    source_id: str,
    profile_id: str | None,
    parser_strategy: str,
    ai_enabled: bool,
    external_refs_enabled: bool,
    actor: str,
) -> tuple[TuningRun, IngestionJob]:
    source = db.get(SourceMaterialRecord, source_id)
    require(source is not None, f"Source not found: {source_id}")

    if profile_id:
        profile = db.get(TuningProfile, profile_id)
        require(profile is not None, f"Profile not found: {profile_id}")
    else:
        profile = ensure_default_profile(db, actor=actor)

    snapshot = snapshot_profile(profile)
    run = TuningRun(
        run_id=prefixed_id("trn"),
        source_id=source_id,
        profile_id=profile.profile_id,
        profile_snapshot_json=snapshot,
        parser_strategy=parser_strategy or "auto_by_extension",
        mode="apply",
        ai_enabled=bool(ai_enabled),
        external_refs_enabled=bool(external_refs_enabled),
        status="pending",
        summary_json={},
        created_by=actor,
        updated_by=actor,
    )
    db.add(run)
    db.flush()

    job = create_ingestion_job(
        db,
        source_id=source_id,
        actor=actor,
        idempotency_key=f"tuning-apply:{run.run_id}",
        correlation_id=f"tuning-apply:{source_id}:{run.run_id}",
    )
    job.tuning_run_id = run.run_id
    job.parser_strategy = run.parser_strategy
    job.updated_by = actor
    db.flush()
    return run, job


def get_tuning_run(db: Session, *, run_id: str) -> TuningRun:
    run = db.get(TuningRun, run_id)
    if run is None:
        raise ValidationError(f"Tuning run not found: {run_id}")
    return run


def list_tuning_runs(db: Session, *, source_id: str | None = None, limit: int = 50) -> list[TuningRun]:
    stmt = select(TuningRun).order_by(TuningRun.created_at.desc()).limit(limit)
    if source_id:
        stmt = stmt.where(TuningRun.source_id == source_id)
    return list(db.scalars(stmt))


def list_profiles(db: Session) -> list[TuningProfile]:
    return list(db.scalars(select(TuningProfile).order_by(TuningProfile.created_at.asc())))


def get_profile(db: Session, *, profile_id: str) -> TuningProfile:
    profile = db.get(TuningProfile, profile_id)
    if profile is None:
        raise ValidationError(f"Profile not found: {profile_id}")
    return profile


def get_default_profile(db: Session, *, actor: str) -> TuningProfile:
    return ensure_default_profile(db, actor=actor)


def upsert_profile(
    db: Session,
    *,
    profile_id: str | None,
    name: str,
    thresholds_json: dict[str, Any],
    lexicons_json: dict[str, Any],
    segmentation_json: dict[str, Any],
    actor: str,
) -> TuningProfile:
    compact_name = (name or "").strip() or "Unnamed"
    if profile_id:
        profile = get_profile(db, profile_id=profile_id)
        profile.name = compact_name
        profile.thresholds_json = thresholds_json
        profile.lexicons_json = lexicons_json
        profile.segmentation_json = segmentation_json
        profile.updated_by = actor
        db.flush()
        return profile
    profile = TuningProfile(
        name=compact_name,
        is_default=False,
        thresholds_json=thresholds_json,
        lexicons_json=lexicons_json,
        segmentation_json=segmentation_json,
        created_by=actor,
        updated_by=actor,
    )
    db.add(profile)
    db.flush()
    return profile


def promote_profile_as_default(db: Session, *, profile_id: str, actor: str) -> None:
    profiles = list_profiles(db)
    require(bool(profiles), "No profiles exist")
    found = False
    for profile in profiles:
        if profile.profile_id == profile_id:
            found = True
            profile.is_default = True
        else:
            profile.is_default = False
        profile.updated_by = actor
    require(found, f"Profile not found: {profile_id}")
    db.flush()
