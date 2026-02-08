import traceback
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import JobStatus
from app.models.core import IngestionJob, JobAttempt, SourceMaterialRecord
from app.services.ai.proposals import propose_for_passage
from app.services.artifacts import artifact_exists, store_text_artifact
from app.services.audit import emit_audit_event
from app.services.extraction import build_passage_evidence
from app.services.parsers import parse_source_file_with_metadata
from app.services.utils import normalize_to_english, now_utc, sha256_file, sha256_text
from app.services.validation import ValidationError, require


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

        parse_result = parse_source_file_with_metadata(source_path)
        raw_text = parse_result["text"]
        if len(raw_text) > settings.max_source_chars:
            raw_text = raw_text[: settings.max_source_chars]
        source.normalized_text_sha256 = sha256_text(
            normalize_to_english(raw_text)[: settings.max_register_fingerprint_chars]
        )
        source.witness_group_id = source.witness_group_id or source.source_id
        job.parser_name = parse_result["parser_name"]
        job.parser_version = parse_result["parser_version"]
        if not artifact_exists(db, source_id=source.source_id, artifact_type="raw_text"):
            store_text_artifact(db, source_id=source.source_id, artifact_type="raw_text", text=raw_text, actor=actor)

        passages = build_passage_evidence(
            db,
            text_id=source.text_id,
            source_id=source.source_id,
            content=raw_text,
            actor=actor,
            max_passages=settings.max_passages_per_source,
        )
        source.digitization_status = "complete"
        source.updated_by = actor

        created = {"tags": 0, "links": 0, "flags": 0}
        for passage in passages:
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
            },
        )
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


def run_worker_cycle(db: Session, *, actor: str) -> IngestionJob | None:
    correlation_id = f"wrk-{now_utc().isoformat()}"
    job = claim_next_pending_job(db, actor=actor, correlation_id=correlation_id)
    if not job:
        return None
    process_job(db, job=job, actor=actor, correlation_id=correlation_id)
    return job
