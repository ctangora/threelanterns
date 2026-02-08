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
    assert passage.usability_score >= 0.0
    assert passage.relevance_score >= 0.0


def test_r31_auto_reprocess_threshold_enqueues_job(client, db_session, tmp_path):
    garbled_but_relevant = (
        "invocation offering ritual oracle @@##@@ #### ??? 12345 boundary chant altar spirit "
        * 25
    ).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-auto-threshold.txt", content=garbled_but_relevant)

    db_session.expire_all()
    refreshed = db_session.get(PassageEvidence, passage.passage_id)
    assert refreshed is not None
    assert refreshed.relevance_state.value != "filtered"
    assert refreshed.needs_reprocess is True or refreshed.usability_score < 0.60

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
        json={"reason_code": "garbled_text", "reason_note": "manual quality retry", "mode": "manual"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passage_id"] == passage.passage_id
    assert body["trigger_mode"] == "manual"

    jobs = client.get("/api/v1/reprocess/jobs", params={"passage_id": passage.passage_id})
    assert jobs.status_code == 200
    assert jobs.json()["total"] >= 1
    assert jobs.json()["items"][0]["trigger_reason_code"] in {
        "garbled_text",
        "manual_operator_request",
    }

    reason_summary = client.get("/api/v1/reprocess/reasons/summary")
    assert reason_summary.status_code == 200
    assert isinstance(reason_summary.json()["items"], list)

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
    hard_garble = ("@@@ #### ??? ### |||| ---- invocation offering ritual altar " * 35).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-unresolved.txt", content=hard_garble)

    manual_enqueue = client.post(
        f"/api/v1/passages/{passage.passage_id}/reprocess",
        json={"reason_code": "garbled_text", "reason_note": "force retry path", "mode": "manual"},
    )
    assert manual_enqueue.status_code == 200

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
    noisy = ("invocation offering ritual @@##@@ ### ??? spirit oracle altar chant " * 20).strip()
    clean_passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-clean.txt", content=clean)
    noisy_passage = _seed_ingested_passage(client, db_session, tmp_path, name="r31-noisy.txt", content=noisy)

    queue = client.get(
        "/api/v1/review/queue",
        params={
            "object_type": "passage",
            "needs_reprocess": "true",
            "max_untranslated_ratio": 1.0,
            "include_filtered": "true",
            "min_usability": 0.0,
            "min_relevance": 0.0,
        },
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
    assert "usability_score" in quality_body
    assert "relevance_score" in quality_body
    assert "relevance_state" in quality_body
    assert "quality_notes_json" in quality_body

    export = client.get("/api/v1/exports/passages.csv", params={"state": "blocked"})
    assert export.status_code == 200
    assert "detected_language_code" in export.text
    assert "detected_language_label" in export.text
    assert "untranslated_ratio" in export.text
    assert "translation_status" in export.text
    assert "needs_reprocess" in export.text
    assert "usability_score" in export.text
    assert "relevance_score" in export.text
    assert "relevance_state" in export.text
    assert "trigger_reason_code_last" in export.text


def test_r32_review_queue_supports_range_filters(client, db_session, tmp_path):
    passage_high = _seed_ingested_passage(
        client,
        db_session,
        tmp_path,
        name="r32-range-high.txt",
        content=(
            "At dawn the practitioner offered water and incense, recited the invocation, "
            "and marked a protective circle before the altar. "
            * 10
        ).strip(),
    )
    passage_low = _seed_ingested_passage(
        client,
        db_session,
        tmp_path,
        name="r32-range-low.txt",
        content=("@@@ #### ??? ### |||| ---- invocation offering ritual altar " * 35).strip(),
    )

    response = client.get(
        "/api/v1/review/queue",
        params={
            "object_type": "passage",
            "include_filtered": "true",
            "min_usability": 0.75,
            "max_usability": 0.98,
            "min_relevance": 0.40,
            "max_relevance": 1.0,
            "min_untranslated_ratio": 0.0,
            "max_untranslated_ratio": 1.0,
            "min_confidence": 0.0,
            "max_confidence": 1.0,
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["object_id"] == passage_high.passage_id for item in items)
    assert all(item["object_id"] != passage_low.passage_id for item in items)


def test_r32_review_queue_rejects_invalid_ranges(client, db_session, tmp_path):
    _seed_ingested_passage(
        client,
        db_session,
        tmp_path,
        name="r32-range-invalid.txt",
        content=("invocation offering ritual passage " * 20).strip(),
    )
    response = client.get(
        "/api/v1/review/queue",
        params={
            "object_type": "passage",
            "min_usability": 0.9,
            "max_usability": 0.1,
        },
    )
    assert response.status_code == 400
    assert "min_usability" in response.json()["detail"]


def test_r32_reprocess_endpoint_accepts_legacy_reason_field(client, db_session, tmp_path):
    content = ("invocation offering ritual phrase " * 12).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r32-legacy-reason.txt", content=content)
    response = client.post(
        f"/api/v1/passages/{passage.passage_id}/reprocess",
        json={"reason": "legacy reason field", "mode": "manual"},
    )
    assert response.status_code == 200

    jobs = client.get("/api/v1/reprocess/jobs", params={"passage_id": passage.passage_id})
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["trigger_reason_code"] == "manual_operator_request"


def test_r32_reprocess_endpoint_rejects_invalid_reason_code(client, db_session, tmp_path):
    content = ("invocation offering ritual phrase " * 12).strip()
    passage = _seed_ingested_passage(client, db_session, tmp_path, name="r32-invalid-reason.txt", content=content)
    response = client.post(
        f"/api/v1/passages/{passage.passage_id}/reprocess",
        json={"reason_code": "not_valid", "reason_note": "x", "mode": "manual"},
    )
    assert response.status_code == 400
    assert "Invalid reprocess reason_code" in response.json()["detail"]
