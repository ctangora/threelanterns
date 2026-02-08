from pathlib import Path

from sqlalchemy import func, select

from app.enums import JobStatus, TranslationStatus
from app.models.core import AuditEvent, PassageEvidence, PassageReprocessJob
from app.services.workflows.ingestion import run_worker_cycle
from tests.helpers import create_local_source_file


def _register_payload(path: Path, **overrides) -> dict:
    payload = {
        "source_path": str(path),
        "rights_status": "public_domain",
        "rights_evidence": "rights-note",
        "provenance_summary": "provenance-note",
        "holding_institution": "local-lib",
        "accession_or_citation": "acc-1",
        "source_provenance_note": "source-note",
    }
    payload.update(overrides)
    return payload


def _seed_ingested_passage(client, db_session, tmp_path, *, name: str, content: str) -> PassageEvidence:
    path = create_local_source_file(tmp_path, name, content=content)
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    assert register.status_code == 200
    source_id = register.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    assert job.status_code == 200
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()
    passage = db_session.scalar(select(PassageEvidence).where(PassageEvidence.source_id == source_id))
    assert passage is not None
    return passage


def test_r31_translation_contract_fields_present(client, db_session, tmp_path):
    content = (
        "This ritual passage describes invocation, offering, and boundary marking in repeated ceremonial language. "
        * 8
    )
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-translation-contract.txt", content=content)
    assert bool(passage.excerpt_normalized.strip())
    assert bool((passage.detected_language_code or "").strip())
    assert bool((passage.detected_language_label or "").strip())
    assert passage.language_detection_confidence is not None
    assert passage.translation_trace_id is not None


def test_r31_auto_reprocess_threshold_enqueues_job(client, db_session, tmp_path):
    foreignish = ("bonjour mystere ancien rituel nocturne invocatione sacrum oracle " * 20).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-auto-threshold.txt", content=foreignish)

    db_session.expire_all()
    refreshed = db_session.get(PassageEvidence, passage.passage_id)
    assert refreshed is not None
    assert refreshed.translation_status == TranslationStatus.needs_reprocess
    assert refreshed.needs_reprocess is True
    assert refreshed.untranslated_ratio > 0.20

    queued = db_session.scalar(
        select(func.count())
        .select_from(PassageReprocessJob)
        .where(PassageReprocessJob.passage_id == passage.passage_id, PassageReprocessJob.status == JobStatus.pending)
    )
    assert int(queued or 0) >= 1


def test_r31_manual_reprocess_endpoint_creates_job_and_audit(client, db_session, tmp_path):
    content = ("invocation offering dawn boundary ritual language " * 20).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-manual-endpoint.txt", content=content)

    response = client.post(
        f"/api/v1/passages/{passage.passage_id}/reprocess",
        json={"reason": "manual quality retry", "mode": "manual"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passage_id"] == passage.passage_id
    assert body["trigger_mode"] == "manual"

    jobs = client.get("/api/v1/reprocess/jobs", params={"passage_id": passage.passage_id})
    assert jobs.status_code == 200
    assert jobs.json()["total"] >= 1

    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.object_type == "passage",
                AuditEvent.object_id == passage.passage_id,
                AuditEvent.action == "passage_reprocess_enqueued",
            )
        )
    )
    assert events


def test_r31_reprocess_retry_cap_marks_unresolved(client, db_session, tmp_path):
    foreignish = ("rituale obscurum vetus lingua arcana cantus nocturnus " * 30).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-unresolved.txt", content=foreignish)

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    db_session.expire_all()
    refreshed = db_session.get(PassageEvidence, passage.passage_id)
    assert refreshed is not None
    assert refreshed.translation_status == TranslationStatus.unresolved
    assert refreshed.needs_reprocess is False
    assert bool((refreshed.detected_language_code or "").strip())
    assert bool((refreshed.detected_language_label or "").strip())
    dead_letter_jobs = list(
        db_session.scalars(
            select(PassageReprocessJob).where(
                PassageReprocessJob.passage_id == passage.passage_id,
                PassageReprocessJob.status == JobStatus.dead_letter,
            )
        )
    )
    assert dead_letter_jobs


def test_r31_review_queue_filters_quality_and_export_columns(client, db_session, tmp_path):
    clean = ("invocation offering dawn ritual passage with clear modern language " * 20).strip()
    noisy = ("bonjour mystere ancien rituel nocturne invocatione sacrum oracle " * 20).strip()
    clean_passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-clean.txt", content=clean)
    noisy_passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-noisy.txt", content=noisy)

    queue = client.get(
        "/api/v1/review/queue",
        params={"object_type": "passage", "needs_reprocess": "true", "max_untranslated_ratio": 1.0},
    )
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert any(item["object_id"] == noisy_passage.passage_id for item in items)
    assert all(item["needs_reprocess"] for item in items)

    quality = client.get(f"/api/v1/passages/{clean_passage.passage_id}/quality")
    assert quality.status_code == 200
    quality_body = quality.json()
    assert "translation_status" in quality_body
    assert "untranslated_ratio" in quality_body

    export = client.get("/api/v1/exports/passages.csv", params={"state": "blocked"})
    assert export.status_code == 200
    assert "detected_language_code" in export.text
    assert "detected_language_label" in export.text
    assert "untranslated_ratio" in export.text
    assert "translation_status" in export.text
    assert "needs_reprocess" in export.text
