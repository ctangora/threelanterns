import traceback
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import PASSAGE_USABILITY_REPROCESS_THRESHOLD
from app.enums import JobStatus, RelevanceState, ReprocessTriggerMode
from app.models.core import IngestionJob, JobAttempt, PassageEvidence, PassageReprocessJob, SourceMaterialRecord, TuningRun
from app.services.ai.proposals import propose_for_passage
from app.services.artifacts import artifact_exists, store_text_artifact
from app.services.audit import emit_audit_event
from app.services.extraction import build_passage_evidence
from app.services.parsers import parse_source_file_with_metadata
from app.services.tuning import build_quality_config, get_segmentation_settings
from app.services.utils import normalize_to_english, now_utc, sha256_file, sha256_text
from app.services.witness import add_member, consolidate_group, ensure_group_for_source, update_group_status_for_parser
from app.services.validation import ValidationError, require
from app.services.workflows.reprocess import enqueue_reprocess_job, run_reprocess_cycle


def create_ingestion_job(
    db: Session,
    *,
    source_id: str,
    actor: str,
    idempotency_key: str | None,
    correlation_id: str,
) -> IngestionJob:
    settings = get_settings()
    source = db.get(SourceMaterialRecord, source_id)
    require(source is not None, f"Source not found: {source_id}")
    key = idempotency_key or f"ingest:{source_id}"

    existing_stmt = select(IngestionJob).where(IngestionJob.idempotency_key == key)
    existing = db.scalar(existing_stmt)
    if existing:
        return existing

    job = IngestionJob(
        source_id=source_id,
        status=JobStatus.pending,
        idempotency_key=key,
        attempt_count=0,
        max_attempts=settings.max_job_attempts,
        created_by=actor,
        updated_by=actor,
    )
    db.add(job)
    db.flush()

    emit_audit_event(
        db,
        actor=actor,
        action="job_created",
        object_type="job",
        object_id=job.job_id,
        correlation_id=correlation_id,
        previous_state=None,
        new_state=JobStatus.pending.value,
        metadata_blob={"source_id": source_id},
    )
    return job


def claim_next_pending_job(db: Session, *, actor: str, correlation_id: str) -> IngestionJob | None:
    stmt = select(IngestionJob).where(IngestionJob.status == JobStatus.pending).order_by(IngestionJob.created_at.asc()).limit(1)
    job = db.scalar(stmt)
    if not job:
        return None
    previous = job.status.value
    job.status = JobStatus.running
    job.updated_by = actor
    db.flush()
    emit_audit_event(
        db,
        actor=actor,
        action="job_claimed",
        object_type="job",
        object_id=job.job_id,
        correlation_id=correlation_id,
        previous_state=previous,
        new_state=job.status.value,
    )
    return job


def _record_attempt(db: Session, *, job: IngestionJob, status: JobStatus, actor: str, error_detail: str | None = None) -> JobAttempt:
    attempt = JobAttempt(
        job_id=job.job_id,
        attempt_no=job.attempt_count,
        status=status,
        error_detail=error_detail,
        created_by=actor,
        updated_by=actor,
    )
    db.add(attempt)
    db.flush()
    return attempt


def _classify_job_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "source file missing" in message:
        return "source_missing"
    if "unsupported extension" in message:
        return "unsupported_extension"
    if "no extractable" in message:
        return "parse_no_text"
    if "openai" in message or "proposal" in message:
        return "proposal_failure"
    return "job_processing_error"


def process_job(db: Session, *, job: IngestionJob, actor: str, correlation_id: str) -> None:
    source = db.get(SourceMaterialRecord, job.source_id)
    if source is None:
        raise ValidationError(f"Source missing for job {job.job_id}")

    try:
        settings = get_settings()
        job.attempt_count += 1
        source_path = Path(source.source_path)
        require(source_path.exists(), f"Source file missing: {source_path}")
        if not source.source_sha256:
            source.source_sha256 = sha256_file(source_path)

        tuning_run: TuningRun | None = None
        if job.tuning_run_id:
            tuning_run = db.get(TuningRun, job.tuning_run_id)
        parser_strategy = job.parser_strategy or (tuning_run.parser_strategy if tuning_run else None)
        parse_result = parse_source_file_with_metadata(source_path, parser_strategy=parser_strategy)
        raw_text = parse_result["text"]
        if len(raw_text) > settings.max_source_chars:
            raw_text = raw_text[: settings.max_source_chars]
        source.normalized_text_sha256 = sha256_text(
            normalize_to_english(raw_text)[: settings.max_register_fingerprint_chars]
        )
        if not source.witness_group_id:
            group = ensure_group_for_source(
                db,
                source=source,
                canonical_text_id=source.text_id,
                actor=actor,
                match_method="exact_hash",
                match_score=1.0,
                status="active",
            )
            source.witness_group_id = group.group_id
        else:
            group = ensure_group_for_source(
                db,
                source=source,
                canonical_text_id=source.text_id,
                actor=actor,
                match_method="exact_hash",
                match_score=1.0,
                status="active",
            )
        job.parser_name = parse_result["parser_name"]
        job.parser_version = parse_result["parser_version"]
        job.parser_strategy = parse_result.get("parser_strategy") or parser_strategy
        if not artifact_exists(db, source_id=source.source_id, artifact_type="raw_text"):
            store_text_artifact(db, source_id=source.source_id, artifact_type="raw_text", text=raw_text, actor=actor)
        add_member(
            db,
            group_id=group.group_id,
            source_id=source.source_id,
            role="primary",
            parser_strategy=job.parser_strategy,
            membership_reason="ingested",
            actor=actor,
        )
        update_group_status_for_parser(db, group=group, parser_strategy=job.parser_strategy, actor=actor)

        quality_config = None
        min_passage_length = 180
        max_passages_override: int | None = None
        ai_allowed = settings.use_mock_ai or settings.ai_enabled
        if tuning_run is not None:
            quality_config = build_quality_config(tuning_run.profile_snapshot_json)
            segmentation = get_segmentation_settings(tuning_run.profile_snapshot_json)
            min_passage_length = segmentation["min_passage_length"]
            max_passages_override = segmentation["max_passages_per_source_override"]
            # Tuning apply runs are opt-in for translation/proposals, even when mocking.
            ai_allowed = bool(tuning_run.ai_enabled)

        passages = build_passage_evidence(
            db,
            text_id=source.text_id,
            source_id=source.source_id,
            content=raw_text,
            actor=actor,
            max_passages=max_passages_override or settings.max_passages_per_source,
            min_passage_length=min_passage_length,
            quality_config=quality_config or build_quality_config({}),
            produced_by_run_id=tuning_run.run_id if tuning_run else None,
            ai_enabled=ai_allowed,
            translation_idempotency_root=f"{job.job_id}:{job.attempt_count}:translation",
        )
        source.digitization_status = "complete"
        source.updated_by = actor

        if tuning_run is not None:
            superseded_stmt = (
                select(PassageEvidence)
                .where(PassageEvidence.source_id == source.source_id, PassageEvidence.superseded_by_run_id.is_(None))
                .order_by(PassageEvidence.created_at.asc())
            )
            existing = list(db.scalars(superseded_stmt))
            new_ids = {passage.passage_id for passage in passages}
            superseded_count = 0
            for record in existing:
                if record.passage_id in new_ids:
                    continue
                record.superseded_by_run_id = tuning_run.run_id
                record.updated_by = actor
                superseded_count += 1
            tuning_run.summary_json = {
                **(tuning_run.summary_json or {}),
                "superseded_passages": superseded_count,
            }

        created = {"tags": 0, "links": 0, "flags": 0}
        auto_reprocess_queued = 0
        skipped_filtered_passages = 0
        for passage in passages:
            auto_reason_code: str | None = None
            auto_reason_note: str | None = None
            if passage.needs_reprocess:
                auto_reason_code = "translation_incomplete"
                auto_reason_note = (
                    "Auto reprocess queued after translation quality gate: "
                    f"untranslated_ratio={passage.untranslated_ratio}"
                )
            elif passage.usability_score < PASSAGE_USABILITY_REPROCESS_THRESHOLD:
                auto_reason_code = "low_usability_score"
                auto_reason_note = (
                    "Auto reprocess queued after usability quality gate: "
                    f"usability_score={passage.usability_score}"
                )

            if auto_reason_code and passage.relevance_state != RelevanceState.filtered:
                enqueue_reprocess_job(
                    db,
                    passage_id=passage.passage_id,
                    actor=actor,
                    trigger_mode=ReprocessTriggerMode.auto_threshold,
                    reason=auto_reason_note or auto_reason_code,
                    reason_code=auto_reason_code,
                    reason_note=auto_reason_note,
                    correlation_id=f"{correlation_id}:{passage.passage_id}:auto",
                )
                auto_reprocess_queued += 1

            if passage.relevance_state == RelevanceState.filtered:
                skipped_filtered_passages += 1
                continue

            if ai_allowed:
                result = propose_for_passage(
                    db,
                    passage=passage,
                    actor=actor,
                    idempotency_root=f"{job.job_id}:{job.attempt_count}",
                )
                created["tags"] += result.tags_created
                created["links"] += result.links_created
                created["flags"] += result.flags_created

        previous = job.status.value
        job.status = JobStatus.completed
        job.last_error = None
        job.error_code = None
        job.error_context_json = {}
        job.updated_by = actor
        _record_attempt(db, job=job, status=JobStatus.completed, actor=actor)

        if tuning_run is not None:
            tuning_run.status = "completed"
            tuning_run.updated_by = actor
            tuning_run.summary_json = {
                **(tuning_run.summary_json or {}),
                "passages_created": len(passages),
                "tags_created": created["tags"],
                "links_created": created["links"],
                "flags_created": created["flags"],
                "skipped_filtered_passages": skipped_filtered_passages,
                "ai_enabled": tuning_run.ai_enabled,
            }

        emit_audit_event(
            db,
            actor=actor,
            action="job_completed",
            object_type="job",
            object_id=job.job_id,
            correlation_id=correlation_id,
            previous_state=previous,
            new_state=job.status.value,
            metadata_blob={
                "passages_created": len(passages),
                "tags_created": created["tags"],
                "links_created": created["links"],
                "flags_created": created["flags"],
                "auto_reprocess_queued": auto_reprocess_queued,
                "skipped_filtered_passages": skipped_filtered_passages,
            },
        )
        consolidate_group(db, group_id=group.group_id, actor=actor)
    except Exception as exc:
        previous = job.status.value
        error_message = f"{exc.__class__.__name__}: {exc}"
        stack = traceback.format_exc()
        job.last_error = f"{error_message}\n{stack}"
        job.error_code = _classify_job_error(exc)
        job.error_context_json = {
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
            "source_id": source.source_id,
            "source_path": source.source_path,
            "attempt_count": job.attempt_count,
        }
        job.updated_by = actor

        if job.attempt_count >= job.max_attempts:
            job.status = JobStatus.dead_letter
        else:
            job.status = JobStatus.pending

        _record_attempt(db, job=job, status=JobStatus.failed, actor=actor, error_detail=error_message)
        emit_audit_event(
            db,
            actor=actor,
            action="job_failed",
            object_type="job",
            object_id=job.job_id,
            correlation_id=correlation_id,
            previous_state=previous,
            new_state=job.status.value,
            metadata_blob={"error": error_message, "error_code": job.error_code},
        )


def run_worker_cycle(db: Session, *, actor: str) -> IngestionJob | PassageReprocessJob | None:
    reprocess_job = run_reprocess_cycle(db, actor=actor)
    if reprocess_job is not None:
        return reprocess_job

    correlation_id = f"wrk-{now_utc().isoformat()}"
    job = claim_next_pending_job(db, actor=actor, correlation_id=correlation_id)
    if not job:
        return None
    process_job(db, job=job, actor=actor, correlation_id=correlation_id)
    return job
