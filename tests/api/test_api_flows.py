from pathlib import Path

from sqlalchemy import select

from app.models.core import AuditEvent, IngestionJob, PassageEvidence
from app.services.workflows.ingestion import run_worker_cycle
from tests.helpers import create_local_source_file


def _register_payload(path: Path) -> dict:
    return {
        "source_path": str(path),
        "rights_status": "public_domain",
        "rights_evidence": "rights-note",
        "provenance_summary": "provenance-note",
        "holding_institution": "local-lib",
        "accession_or_citation": "acc-1",
        "source_provenance_note": "source-note",
    }


def test_t01_register_missing_rights_status_returns_422(client, tmp_path):
    path = create_local_source_file(tmp_path, "t01.txt")
    payload = _register_payload(path)
    payload.pop("rights_status")
    response = client.post("/api/v1/intake/register", json=payload)
    assert response.status_code == 422


def test_t02_register_missing_provenance_returns_422(client, tmp_path):
    path = create_local_source_file(tmp_path, "t02.txt")
    payload = _register_payload(path)
    payload.pop("provenance_summary")
    response = client.post("/api/v1/intake/register", json=payload)
    assert response.status_code == 422


def test_m2_discover_returns_supported_types_only(client):
    response = client.post("/api/v1/intake/discover", json={"max_files": 25})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 25
    assert all(file["extension"] in {".txt", ".md", ".html", ".epub", ".gz"} for file in body["files"])


def test_m2_job_idempotency(client, tmp_path):
    path = create_local_source_file(tmp_path, "idempotency.txt")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]

    payload = {"source_id": source_id, "idempotency_key": "same-key"}
    first = client.post("/api/v1/jobs/ingest", json=payload)
    second = client.post("/api/v1/jobs/ingest", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]


def test_m2_review_requires_notes_for_reject(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "review-need-notes.txt")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id}).json()

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    passage = db_session.scalar(select(PassageEvidence))
    assert passage is not None

    response = client.post(f"/api/v1/review/passage/{passage.passage_id}", json={"decision": "reject"})
    assert response.status_code == 400
    assert "Notes are required" in response.json()["detail"]


def test_t09_audit_events_emitted_for_create_and_review(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "audit.txt")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    passage = db_session.scalar(select(PassageEvidence))
    assert passage is not None
    approved = client.post(
        f"/api/v1/review/passage/{passage.passage_id}",
        json={"decision": "approve", "notes": "ok"},
    )
    assert approved.status_code == 200

    events = list(db_session.scalars(select(AuditEvent)))
    assert len(events) >= 3


def test_t08_publish_state_blocked_until_approve(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "blocked.txt")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    client.post("/api/v1/jobs/ingest", json={"source_id": source_id})

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()
    passage = db_session.scalar(select(PassageEvidence))
    assert passage is not None
    assert passage.publish_state.value == "blocked"

    response = client.post(
        f"/api/v1/review/passage/{passage.passage_id}",
        json={"decision": "approve", "notes": "meets criteria"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(PassageEvidence, passage.passage_id)
    assert refreshed is not None
    assert refreshed.publish_state.value == "eligible"


def test_t10_source_fk_integrity_enforced(db_session):
    job = IngestionJob(
        source_id="src_missing",
        status="pending",
        idempotency_key="missing-source",
        attempt_count=0,
        max_attempts=3,
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(job)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        assert True
    else:
        raise AssertionError("Expected foreign key failure when source does not exist")


def test_review_queue_defaults_and_metadata(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "queue-defaults.txt")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    response = client.get("/api/v1/review/queue", params={"object_type": "passage"})
    assert response.status_code == 200
    body = response.json()
    assert body["object_type"] == "passage"
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total"] >= len(body["items"])


def test_review_queue_pagination(client, db_session, tmp_path):
    long_chunk = (
        "This is a long ritual paragraph with invocation offering boundary marking and repetitive ceremonial language "
        "that exceeds the minimum extraction threshold for segmentation and review workflow verification."
    )
    content = "\n\n".join([long_chunk for _ in range(30)])
    path = create_local_source_file(tmp_path, "queue-pagination.txt", content=content)

    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    page_1 = client.get("/api/v1/review/queue", params={"object_type": "passage", "page": 1, "page_size": 5})
    page_2 = client.get("/api/v1/review/queue", params={"object_type": "passage", "page": 2, "page_size": 5})

    assert page_1.status_code == 200
    assert page_2.status_code == 200
    body_1 = page_1.json()
    body_2 = page_2.json()
    assert body_1["total"] >= 10
    assert len(body_1["items"]) == 5
    assert len(body_2["items"]) == 5
    ids_1 = {item["object_id"] for item in body_1["items"]}
    ids_2 = {item["object_id"] for item in body_2["items"]}
    assert ids_1.isdisjoint(ids_2)
