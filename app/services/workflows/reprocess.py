from __future__ import annotations

import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.constants import PASSAGE_REPROCESS_MAX_ATTEMPTS, TRANSLATION_UNTRANSLATED_RATIO_THRESHOLD
from app.enums import JobStatus, ReprocessTriggerMode, ReviewerState, SourceObjectType, TranslationStatus
from app.models.core import (
    FlagRecord,
    PassageEvidence,
    PassageReprocessJob,
    PassageTranslationRevision,
    SourceMaterialRecord,
    TextRecord,
)
from app.services.audit import emit_audit_event
from app.services.connectors.free_refs import search_free_references
from app.services.parsers.pdf import parse_pdf
from app.services.translation import translate_passage_excerpt
from app.services.utils import now_utc
from app.services.validation import ValidationError, require


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {key: _to_json_safe(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(nested) for nested in value]
    return value


def _tokenize(text: str) -> set[str]:
    return {token.strip(".,:;!?()[]{}<>\"'").lower() for token in text.split() if token.strip()}


def _jaccard(left: str, right: str) -> float:
    left_tokens = {token for token in _tokenize(left) if len(token) > 2}
    right_tokens = {token for token in _tokenize(right) if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens.intersection(right_tokens)
    union = left_tokens.union(right_tokens)
    return len(overlap) / len(union)


def _find_best_pdf_variant(db: Session, *, passage: PassageEvidence) -> dict[str, Any] | None:
    sibling_stmt = select(SourceMaterialRecord).where(
        SourceMaterialRecord.text_id == passage.text_id,
        SourceMaterialRecord.source_id != passage.source_id,
    )
    siblings = list(db.scalars(sibling_stmt))
    pdf_sources = [source for source in siblings if Path(source.source_path).suffix.lower() == ".pdf"]
    if not pdf_sources:
        return None

    best: dict[str, Any] | None = None
    for source in pdf_sources:
        source_path = Path(source.source_path)
        if not source_path.exists():
            continue
        try:
            content = parse_pdf(source_path)
        except Exception:
            continue
        chunks = [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
        if not chunks:
            continue
        for chunk in chunks[:120]:
            score = _jaccard(passage.excerpt_original, chunk)
            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "excerpt": chunk,
                    "source_id": source.source_id,
                    "source_path": str(source_path),
                }
    if best is None:
        return None
    if best["score"] < 0.12:
        return None
    return {
        "source_variant": "pdf_crossref",
        "excerpt": best["excerpt"],
        "reference_context": f"Sibling PDF witness {best['source_id']} ({best['source_path']})",
        "provenance": {
            "provider": "local_pdf_crossref",
            "source_id": best["source_id"],
            "source_path": best["source_path"],
            "similarity": round(best["score"], 4),
        },
    }


def _find_best_external_variant(db: Session, *, passage: PassageEvidence) -> dict[str, Any] | None:
    text = db.get(TextRecord, passage.text_id)
    if text is None:
        return None
    title = text.canonical_title
    snippet = passage.excerpt_original[:360]
    candidates = search_free_references(title, snippet, limit=5, timeout=8)
    if not candidates:
        return None
    candidate = candidates[0]
    variant_excerpt = candidate.snippet.strip() or passage.excerpt_original
    reference_context = (
        f"Reference candidate provider={candidate.provider} title={candidate.title} "
        f"locator={candidate.locator} snippet={candidate.snippet[:300]}"
    )
    return {
        "source_variant": "external_reference",
        "excerpt": variant_excerpt,
        "reference_context": reference_context,
        "provenance": {
            "provider": candidate.provider,
            "title": candidate.title,
            "locator": candidate.locator,
            "score": candidate.score,
            "metadata": candidate.metadata,
        },
    }


def enqueue_reprocess_job(
    db: Session,
    *,
    passage_id: str,
    actor: str,
    trigger_mode: ReprocessTriggerMode,
    reason: str,
    correlation_id: str,
) -> PassageReprocessJob:
    compact_reason = reason.strip()
    require(bool(compact_reason), "Reprocess reason is required")
    passage = db.get(PassageEvidence, passage_id)
    require(passage is not None, f"Passage not found: {passage_id}")

    existing_stmt = (
        select(PassageReprocessJob)
        .where(
            PassageReprocessJob.passage_id == passage_id,
            PassageReprocessJob.status.in_([JobStatus.pending, JobStatus.running]),
        )
        .order_by(PassageReprocessJob.created_at.desc())
        .limit(1)
    )
    existing = db.scalar(existing_stmt)
    if existing is not None:
        return existing

    stamp = now_utc().isoformat()
    job = PassageReprocessJob(
        passage_id=passage_id,
        idempotency_key=f"reprocess:{passage_id}:{trigger_mode.value}:{stamp}",
        status=JobStatus.pending,
        trigger_mode=trigger_mode,
        trigger_reason=compact_reason,
        attempt_count=0,
        max_attempts=PASSAGE_REPROCESS_MAX_ATTEMPTS,
        used_pdf_crossref=False,
        used_external_reference=False,
        error_context_json={},
        created_by=actor,
        updated_by=actor,
    )
    db.add(job)
    passage.needs_reprocess = True
    passage.translation_status = TranslationStatus.needs_reprocess
    passage.updated_by = actor
    db.flush()

    emit_audit_event(
        db,
        actor=actor,
        action="passage_reprocess_enqueued",
        object_type="passage",
        object_id=passage_id,
        correlation_id=correlation_id,
        previous_state=None,
        new_state=job.status.value,
        metadata_blob={
            "reprocess_job_id": job.reprocess_job_id,
            "trigger_mode": trigger_mode.value,
            "reason": compact_reason,
        },
    )
    return job


def claim_next_pending_reprocess_job(db: Session, *, actor: str, correlation_id: str) -> PassageReprocessJob | None:
    stmt = (
        select(PassageReprocessJob)
        .where(PassageReprocessJob.status == JobStatus.pending)
        .order_by(PassageReprocessJob.created_at.asc())
        .limit(1)
    )
    job = db.scalar(stmt)
    if job is None:
        return None
    previous = job.status.value
    job.status = JobStatus.running
    job.updated_by = actor
    db.flush()
    emit_audit_event(
        db,
        actor=actor,
        action="passage_reprocess_claimed",
        object_type="passage",
        object_id=job.passage_id,
        correlation_id=correlation_id,
        previous_state=previous,
        new_state=job.status.value,
        metadata_blob={"reprocess_job_id": job.reprocess_job_id},
    )
    return job


def _ensure_uncertain_translation_flag(
    db: Session,
    *,
    passage: PassageEvidence,
    actor: str,
    rationale: str,
) -> None:
    existing_stmt = (
        select(FlagRecord)
        .where(
            FlagRecord.object_type == SourceObjectType.passage,
            FlagRecord.object_id == passage.passage_id,
            FlagRecord.flag_type == "uncertain_translation",
        )
        .order_by(FlagRecord.created_at.desc())
        .limit(1)
    )
    existing = db.scalar(existing_stmt)
    if existing is not None:
        existing.rationale = rationale
        existing.reviewer_state = ReviewerState.proposed
        existing.updated_by = actor
        return
    flag = FlagRecord(
        object_type=SourceObjectType.passage,
        object_id=passage.passage_id,
        flag_type="uncertain_translation",
        severity="high",
        rationale=rationale,
        evidence_ids=[passage.passage_id],
        reviewer_state=ReviewerState.proposed,
        created_by=actor,
        updated_by=actor,
    )
    db.add(flag)


def _classify_reprocess_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "passage not found" in message:
        return "passage_not_found"
    if "translation failed" in message:
        return "translation_failure"
    if "reference" in message:
        return "reference_lookup_failure"
    return "reprocess_failure"


def process_reprocess_job(db: Session, *, job: PassageReprocessJob, actor: str, correlation_id: str) -> None:
    passage = db.get(PassageEvidence, job.passage_id)
    require(passage is not None, f"Passage not found for reprocess: {job.passage_id}")

    try:
        job.attempt_count += 1
        variants: list[dict[str, Any]] = [
            {
                "source_variant": "original_parse",
                "excerpt": passage.excerpt_original,
                "reference_context": None,
                "provenance": {"provider": "local_original", "source_id": passage.source_id},
            }
        ]

        pdf_variant = _find_best_pdf_variant(db, passage=passage)
        if pdf_variant is not None:
            variants.append(pdf_variant)
        external_variant = _find_best_external_variant(db, passage=passage)
        if external_variant is not None:
            variants.append(external_variant)

        accepted_translation = None
        accepted_variant: str | None = None
        last_translation = None
        last_variant: str | None = None

        for variant_index, variant in enumerate(variants, start=1):
            source_variant = variant["source_variant"]
            result = translate_passage_excerpt(
                db,
                passage_id=passage.passage_id,
                excerpt=variant["excerpt"],
                actor=actor,
                idempotency_key=f"{job.idempotency_key}:{job.attempt_count}:{variant_index}",
                source_variant=source_variant,
                reference_context=variant.get("reference_context"),
            )

            quality_decision = "accepted" if result.untranslated_ratio <= TRANSLATION_UNTRANSLATED_RATIO_THRESHOLD else "needs_reprocess"
            revision = PassageTranslationRevision(
                passage_id=passage.passage_id,
                attempt_no=job.attempt_count,
                source_variant=source_variant,
                input_excerpt=variant["excerpt"],
                translated_excerpt=result.modern_english_text,
                detected_language_code=result.detected_language_code,
                detected_language_label=result.detected_language_label,
                untranslated_ratio=result.untranslated_ratio,
                quality_decision=quality_decision,
                provenance_json=variant["provenance"],
                translation_trace_id=result.trace_id,
                created_by=actor,
                updated_by=actor,
            )
            db.add(revision)

            last_translation = result
            last_variant = source_variant
            if source_variant == "pdf_crossref":
                job.used_pdf_crossref = True
            if source_variant == "external_reference":
                job.used_external_reference = True

            if quality_decision == "accepted":
                accepted_translation = result
                accepted_variant = source_variant
                break

        now = now_utc()
        passage.reprocess_count += 1
        passage.last_reprocess_at = now
        passage.updated_by = actor

        if accepted_translation is not None:
            passage.excerpt_normalized = accepted_translation.modern_english_text
            passage.detected_language_code = accepted_translation.detected_language_code
            passage.detected_language_label = accepted_translation.detected_language_label
            passage.language_detection_confidence = accepted_translation.language_detection_confidence
            passage.untranslated_ratio = accepted_translation.untranslated_ratio
            passage.translation_status = TranslationStatus.translated
            passage.needs_reprocess = False
            passage.translation_provider = accepted_translation.translation_provider
            passage.translation_trace_id = accepted_translation.trace_id

            previous = job.status.value
            job.status = JobStatus.completed
            job.last_error = None
            job.error_code = None
            job.error_context_json = {}
            job.updated_by = actor
            emit_audit_event(
                db,
                actor=actor,
                action="passage_reprocess_completed",
                object_type="passage",
                object_id=passage.passage_id,
                correlation_id=correlation_id,
                previous_state=previous,
                new_state=job.status.value,
                metadata_blob={
                    "reprocess_job_id": job.reprocess_job_id,
                    "accepted_variant": accepted_variant,
                    "untranslated_ratio": accepted_translation.untranslated_ratio,
                },
            )
            return

        if last_translation is not None:
            passage.detected_language_code = last_translation.detected_language_code
            passage.detected_language_label = last_translation.detected_language_label
            passage.language_detection_confidence = last_translation.language_detection_confidence
            passage.untranslated_ratio = last_translation.untranslated_ratio
            passage.translation_provider = last_translation.translation_provider
            passage.translation_trace_id = last_translation.trace_id

        unresolved_rationale = (
            "Passage remained above untranslated ratio threshold after reprocessing. "
            f"latest_ratio={passage.untranslated_ratio} threshold={TRANSLATION_UNTRANSLATED_RATIO_THRESHOLD}"
        )
        if job.attempt_count >= job.max_attempts:
            passage.translation_status = TranslationStatus.unresolved
            passage.needs_reprocess = False
            _ensure_uncertain_translation_flag(db, passage=passage, actor=actor, rationale=unresolved_rationale)
            previous = job.status.value
            job.status = JobStatus.dead_letter
            job.last_error = unresolved_rationale
            job.error_code = "translation_unresolved"
            job.error_context_json = {
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "last_variant": last_variant,
                "untranslated_ratio": passage.untranslated_ratio,
            }
            emit_audit_event(
                db,
                actor=actor,
                action="passage_reprocess_unresolved",
                object_type="passage",
                object_id=passage.passage_id,
                correlation_id=correlation_id,
                previous_state=previous,
                new_state=job.status.value,
                metadata_blob={"reprocess_job_id": job.reprocess_job_id, "reason": unresolved_rationale},
            )
        else:
            passage.translation_status = TranslationStatus.needs_reprocess
            passage.needs_reprocess = True
            previous = job.status.value
            job.status = JobStatus.pending
            job.last_error = unresolved_rationale
            job.error_code = "translation_below_quality_threshold"
            job.error_context_json = {
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "last_variant": last_variant,
                "untranslated_ratio": passage.untranslated_ratio,
            }
            emit_audit_event(
                db,
                actor=actor,
                action="passage_reprocess_retry_scheduled",
                object_type="passage",
                object_id=passage.passage_id,
                correlation_id=correlation_id,
                previous_state=previous,
                new_state=job.status.value,
                metadata_blob={"reprocess_job_id": job.reprocess_job_id, "reason": unresolved_rationale},
            )
        job.updated_by = actor
    except Exception as exc:
        previous = job.status.value
        error_message = f"{exc.__class__.__name__}: {exc}"
        job.last_error = f"{error_message}\n{traceback.format_exc()}"
        job.error_code = _classify_reprocess_error(exc)
        job.error_context_json = {
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
            "passage_id": job.passage_id,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
        }
        if job.attempt_count >= job.max_attempts:
            job.status = JobStatus.dead_letter
            if passage is not None:
                passage.translation_status = TranslationStatus.unresolved
                passage.needs_reprocess = False
                passage.updated_by = actor
        else:
            job.status = JobStatus.pending
        job.updated_by = actor
        emit_audit_event(
            db,
            actor=actor,
            action="passage_reprocess_failed",
            object_type="passage",
            object_id=job.passage_id,
            correlation_id=correlation_id,
            previous_state=previous,
            new_state=job.status.value,
            metadata_blob={"error": error_message, "error_code": job.error_code},
        )


def list_reprocess_jobs(
    db: Session,
    *,
    status: str | None = None,
    trigger_mode: str | None = None,
    passage_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    max_page_size: int = 200,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))
    offset = (page - 1) * page_size

    where_clauses = []
    if status:
        try:
            parsed_status = JobStatus(status)
        except ValueError as exc:
            raise ValidationError(f"Unsupported reprocess job status: {status}") from exc
        where_clauses.append(PassageReprocessJob.status == parsed_status)
    if trigger_mode:
        try:
            parsed_trigger = ReprocessTriggerMode(trigger_mode)
        except ValueError as exc:
            raise ValidationError(f"Unsupported trigger_mode: {trigger_mode}") from exc
        where_clauses.append(PassageReprocessJob.trigger_mode == parsed_trigger)
    if passage_id:
        where_clauses.append(PassageReprocessJob.passage_id == passage_id)

    total_stmt = select(func.count()).select_from(PassageReprocessJob).where(*where_clauses)
    total = int(db.scalar(total_stmt) or 0)
    stmt = (
        select(PassageReprocessJob)
        .where(*where_clauses)
        .order_by(PassageReprocessJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list(db.scalars(stmt))
    items = []
    for row in rows:
        payload = {column.name: _to_json_safe(getattr(row, column.name)) for column in row.__table__.columns}
        payload["object_id"] = payload["reprocess_job_id"]
        items.append(payload)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def get_passage_quality(db: Session, *, passage_id: str) -> dict[str, Any]:
    passage = db.get(PassageEvidence, passage_id)
    require(passage is not None, f"Passage not found: {passage_id}")
    return {
        "passage_id": passage.passage_id,
        "translation_status": passage.translation_status.value,
        "needs_reprocess": passage.needs_reprocess,
        "untranslated_ratio": passage.untranslated_ratio,
        "detected_language_code": passage.detected_language_code,
        "detected_language_label": passage.detected_language_label,
        "language_detection_confidence": passage.language_detection_confidence,
        "reprocess_count": passage.reprocess_count,
        "last_reprocess_at": passage.last_reprocess_at,
        "translation_provider": passage.translation_provider,
        "translation_trace_id": passage.translation_trace_id,
        "unresolved": passage.translation_status == TranslationStatus.unresolved,
    }


def run_reprocess_cycle(db: Session, *, actor: str) -> PassageReprocessJob | None:
    correlation_id = f"rpj-{now_utc().isoformat()}"
    job = claim_next_pending_reprocess_job(db, actor=actor, correlation_id=correlation_id)
    if not job:
        return None
    process_reprocess_job(db, job=job, actor=actor, correlation_id=correlation_id)
    return job
