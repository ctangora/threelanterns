from pathlib import Path

from sqlalchemy import select

from app.enums import RelationType, ReviewerState, SourceObjectType
from app.models.core import AuditEvent, CommonalityLink, FlagRecord, IngestionJob, PassageEvidence
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


def _seed_ingested_source(client, db_session, tmp_path, *, name: str, content: str, **register_overrides):
    path = create_local_source_file(tmp_path, name, content=content)
    register = client.post("/api/v1/intake/register", json=_register_payload(path, **register_overrides))
    assert register.status_code == 200
    source_id = register.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    assert job.status_code == 200
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()
    return source_id


def test_m3_batch_register_handles_dedupe_and_witness(client, db_session, tmp_path):
    path_1 = create_local_source_file(tmp_path, "dedupe-base.txt", content="ritual same text")
    path_2 = tmp_path / "dedupe-witness.rtf"
    path_2.write_text(r"{\rtf1\ansi ritual same text}", encoding="utf-8")

    request = {
        "items": [
            _register_payload(path_1, accession_or_citation="acc-1"),
            _register_payload(path_2, accession_or_citation="acc-2"),
        ]
    }
    response = client.post("/api/v1/intake/register/batch", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["created"] == 1
    assert body["alternate_witnesses"] == 1
    statuses = [item["status"] for item in body["results"]]
    assert "created" in statuses
    assert "alternate_witness" in statuses


def test_m3_exact_duplicate_returns_existing_source(client, tmp_path):
    path = create_local_source_file(tmp_path, "exact-dup.txt", content="same ritual")
    first = client.post("/api/v1/intake/register", json=_register_payload(path))
    second = client.post("/api/v1/intake/register", json=_register_payload(path))
    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["source_id"] == second_body["source_id"]
    assert second_body["registration_status"] == "exact_duplicate"
    assert second_body["duplicate_of_source_id"] == first_body["source_id"]


def test_m3_job_failure_populates_error_diagnostics(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "missing-source.txt", content="ritual")
    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id}).json()
    path.unlink()

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    refreshed = db_session.get(IngestionJob, job["job_id"])
    assert refreshed is not None
    assert refreshed.error_code == "source_missing"
    assert refreshed.error_context_json["source_id"] == source_id
    assert "Source file missing" in refreshed.error_context_json["message"]


def test_m3_review_queue_filters_sort_and_states(client, db_session, tmp_path):
    long_chunk = (
        "This is a ritual passage describing invocation and offering with repeated ceremonial words for passage splitting."
    )
    content = "\n\n".join([long_chunk for _ in range(10)])
    source_id = _seed_ingested_source(client, db_session, tmp_path, name="queue-filters.txt", content=content)

    queue = client.get("/api/v1/review/queue", params={"object_type": "passage", "source_id": source_id, "state": "proposed"})
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert items
    first_passage_id = items[0]["object_id"]

    approve = client.post(
        f"/api/v1/review/passage/{first_passage_id}",
        json={"decision": "approve", "notes": "approved for filters test"},
    )
    assert approve.status_code == 200

    approved = client.get("/api/v1/review/queue", params={"object_type": "passage", "state": "approved"})
    assert approved.status_code == 200
    assert any(item["object_id"] == first_passage_id for item in approved.json()["items"])

    filtered = client.get(
        "/api/v1/review/queue",
        params={
            "object_type": "passage",
            "state": "proposed",
            "source_id": source_id,
            "min_confidence": 0.0,
            "sort_by": "confidence",
            "sort_dir": "desc",
            "page_size": 5,
        },
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["page_size"] == 5
    assert all(item["source_id"] == source_id for item in body["items"])


def test_m3_bulk_review_all_object_types_and_audit(client, db_session, tmp_path):
    source_id = _seed_ingested_source(
        client,
        db_session,
        tmp_path,
        name="bulk-review.txt",
        content="invocation offering circle dawn ritual text\n\ninvocation offering circle dawn ritual text",
    )
    passage_queue = client.get("/api/v1/review/queue", params={"object_type": "passage", "source_id": source_id})
    tag_queue = client.get("/api/v1/review/queue", params={"object_type": "tag"})
    assert passage_queue.status_code == 200
    assert tag_queue.status_code == 200
    passage_id = passage_queue.json()["items"][0]["object_id"]
    tag_id = tag_queue.json()["items"][0]["object_id"]

    link = CommonalityLink(
        source_entity_type="passage",
        source_entity_id=passage_id,
        target_entity_type="passage",
        target_entity_id=passage_id,
        relation_type=RelationType.shares_pattern_with,
        weighted_similarity_score=0.75,
        evidence_ids=[passage_id],
        reviewer_decision=ReviewerState.proposed,
        decision_note=None,
        created_by="test-operator",
        updated_by="test-operator",
    )
    flag = FlagRecord(
        object_type=SourceObjectType.passage,
        object_id=passage_id,
        flag_type="provenance_gap",
        severity="low",
        rationale="test rationale",
        evidence_ids=[passage_id],
        reviewer_state=ReviewerState.proposed,
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(link)
    db_session.add(flag)
    db_session.commit()

    link_id = link.link_id
    flag_id = flag.flag_id
    assert link_id is not None
    assert flag_id is not None

    for object_type, object_id in [
        ("passage", passage_id),
        ("tag", tag_id),
        ("link", link_id),
        ("flag", flag_id),
    ]:
        response = client.post(
            "/api/v1/review/bulk",
            json={"object_type": object_type, "object_ids": [object_id], "decision": "approve"},
        )
        assert response.status_code == 200
        assert response.json()["processed"] == 1

    db_session.expire_all()
    assert db_session.get(CommonalityLink, link_id).reviewer_decision == ReviewerState.approved
    assert db_session.get(FlagRecord, flag_id).reviewer_state == ReviewerState.approved

    review_events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "review_decision",
                AuditEvent.object_id.in_([passage_id, tag_id, link_id, flag_id]),
            )
        )
    )
    assert len(review_events) >= 4


def test_m3_bulk_review_reject_requires_notes(client, db_session, tmp_path):
    _seed_ingested_source(client, db_session, tmp_path, name="bulk-notes.txt", content="ritual text")
    passage_queue = client.get("/api/v1/review/queue", params={"object_type": "passage"})
    passage_id = passage_queue.json()["items"][0]["object_id"]
    response = client.post(
        "/api/v1/review/bulk",
        json={"object_type": "passage", "object_ids": [passage_id], "decision": "reject"},
    )
    assert response.status_code == 400
    assert "Notes are required" in response.json()["detail"]


def test_m3_review_metrics_and_health_details(client, db_session, tmp_path):
    _seed_ingested_source(client, db_session, tmp_path, name="metrics.txt", content="invocation ritual text")

    metrics = client.get("/api/v1/review/metrics")
    assert metrics.status_code == 200
    metrics_body = metrics.json()
    assert set(metrics_body["backlog"].keys()) == {"passage", "tag", "link", "flag"}
    assert isinstance(metrics_body["decisions_24h"], int)

    health = client.get("/health/details")
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["database_ok"] is True
    assert "pending" in health_body["queue_depth"]
    assert "dead_letter" in health_body["queue_depth"]


def test_m3_search_api_and_exports(client, db_session, tmp_path):
    source_id = _seed_ingested_source(
        client,
        db_session,
        tmp_path,
        name="search-export.txt",
        content="invocation offering circle dawn ritual",
        origin_culture_region="south_asia",
    )
    passage_queue = client.get("/api/v1/review/queue", params={"object_type": "passage", "source_id": source_id})
    tag_queue = client.get("/api/v1/review/queue", params={"object_type": "tag"})
    passage_id = passage_queue.json()["items"][0]["object_id"]
    tag_id = tag_queue.json()["items"][0]["object_id"]

    client.post(f"/api/v1/review/passage/{passage_id}", json={"decision": "approve", "notes": "publish passage"})
    client.post(f"/api/v1/review/tag/{tag_id}", json={"decision": "approve", "notes": "approve tag"})

    search = client.get(
        "/api/v1/search",
        params={"q": "invocation", "object_type": "passage", "review_state": "approved", "limit": 25},
    )
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits
    assert all(hit["review_state"] == "approved" for hit in hits)
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)

    passages_export = client.get("/api/v1/exports/passages.csv", params={"state": "eligible"})
    assert passages_export.status_code == 200
    assert "passage_id" in passages_export.text
    assert passage_id in passages_export.text

    tags_export = client.get("/api/v1/exports/tags.csv", params={"state": "approved"})
    assert tags_export.status_code == 200
    assert "tag_id" in tags_export.text
    assert tag_id in tags_export.text


def test_m3_web_review_invalid_filter_and_search_pages(client, db_session, tmp_path):
    _seed_ingested_source(client, db_session, tmp_path, name="web-pages-r3.txt", content="invocation ritual")

    invalid_filter = client.get("/review/tags?source_id=src_invalid")
    assert invalid_filter.status_code == 200
    assert "Error:" in invalid_filter.text

    search_page = client.get("/search?q=invocation&object_type=passage")
    assert search_page.status_code == 200
    metrics_page = client.get("/review/metrics")
    assert metrics_page.status_code == 200
