from pathlib import Path

from sqlalchemy import select

from app.models.core import ConsolidatedPassage, WitnessGroup, WitnessGroupMember
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


def test_exact_hash_groups_sources(client, db_session, tmp_path):
    content = ("invocation offering ritual text " * 20).strip()
    path_a = create_local_source_file(tmp_path, "witness-a.txt", content=content)
    path_b = create_local_source_file(tmp_path, "witness-b.txt", content=content)

    res_a = client.post("/api/v1/intake/register", json=_register_payload(path_a))
    res_b = client.post("/api/v1/intake/register", json=_register_payload(path_b))
    assert res_a.status_code == 200
    assert res_b.status_code == 200

    group_id = res_a.json()["witness_group_id"]
    assert group_id
    members = list(db_session.scalars(select(WitnessGroupMember).where(WitnessGroupMember.group_id == group_id)))
    assert members


def test_fuzzy_groups_similar_sources(client, db_session, tmp_path):
    content_a = ("invocation offering ritual text with dawn rites " * 20).strip()
    content_b = ("invocation offering ritual text with dusk rites " * 20).strip()
    path_a = create_local_source_file(tmp_path, "fuzzy-a.txt", content=content_a)
    path_b = create_local_source_file(tmp_path, "fuzzy-b.txt", content=content_b)

    res_a = client.post("/api/v1/intake/register", json=_register_payload(path_a))
    res_b = client.post("/api/v1/intake/register", json=_register_payload(path_b))
    assert res_a.status_code == 200
    assert res_b.status_code == 200

    group_id = res_b.json()["witness_group_id"]
    group = db_session.get(WitnessGroup, group_id)
    assert group is not None
    assert group.match_method in {"fuzzy", "normalized_hash", "exact_hash"}


def test_consolidation_creates_passages(client, db_session, tmp_path):
    content_a = ("invocation offering ritual text " * 20).strip()
    content_b = ("invocation offering ritual text " * 20).strip()
    path_a = create_local_source_file(tmp_path, "cons-a.txt", content=content_a)
    path_b = create_local_source_file(tmp_path, "cons-b.txt", content=content_b)

    res_a = client.post("/api/v1/intake/register", json=_register_payload(path_a))
    res_b = client.post("/api/v1/intake/register", json=_register_payload(path_b))
    assert res_a.status_code == 200
    assert res_b.status_code == 200

    source_id = res_a.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    assert job.status_code == 200
    from app.services.workflows.ingestion import run_worker_cycle
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    group_id = res_a.json()["witness_group_id"]
    result = client.post(f"/api/v1/witness-groups/recompute/{group_id}")
    assert result.status_code == 200

    consolidated = list(db_session.scalars(select(ConsolidatedPassage).where(ConsolidatedPassage.group_id == group_id)))
    assert consolidated
