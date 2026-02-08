from tests.helpers import create_local_source_file


def _register_payload(path):
    return {
        "source_path": str(path),
        "rights_status": "public_domain",
        "rights_evidence": "rights-note",
        "provenance_summary": "provenance-note",
        "holding_institution": "local-lib",
        "accession_or_citation": "acc-1",
        "source_provenance_note": "source-note",
    }


def _seed_review_data(client, db_session, tmp_path):
    long_chunk = (
        "This is a long ritual paragraph with invocation offering boundary marking and repetitive ceremonial language "
        "that exceeds the minimum extraction threshold for segmentation and review workflow verification."
    )
    content = "\n\n".join([long_chunk for _ in range(20)])
    path = create_local_source_file(tmp_path, "web-pages.txt", content=content)

    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    source_id = register.json()["source_id"]
    client.post("/api/v1/jobs/ingest", json={"source_id": source_id})

    from app.services.workflows.ingestion import run_worker_cycle

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()


def test_review_pages_render_without_500(client, db_session, tmp_path):
    _seed_review_data(client, db_session, tmp_path)

    for path in ["/review/passages", "/review/tags", "/review/links", "/review/flags"]:
        response = client.get(path)
        assert response.status_code == 200


def test_review_pages_support_pagination(client, db_session, tmp_path):
    _seed_review_data(client, db_session, tmp_path)

    response = client.get("/review/passages?page=2&page_size=5")
    assert response.status_code == 200
    text = response.text
    assert "Showing page 2" in text
    assert "page size 5" in text
