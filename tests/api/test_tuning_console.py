from pathlib import Path

from sqlalchemy import select

from app.models.core import IngestionJob, TuningRun, TuningRunPassage
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


def test_tuning_preview_run_creates_run_and_passages(client, db_session, tmp_path):
    content = ("invocation offering ritual text " * 30).strip()
    path = create_local_source_file(tmp_path, "tuning-preview.txt", content=content)

    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    assert register.status_code == 200
    source_id = register.json()["source_id"]

    preview = client.post(
        "/api/v1/tuning/runs/preview",
        json={"source_id": source_id, "parser_strategy": "auto_by_extension"},
    )
    assert preview.status_code == 200
    run_id = preview.json()["run"]["run_id"]

    run = db_session.get(TuningRun, run_id)
    assert run is not None
    assert run.mode == "preview"
    assert run.status == "completed"

    items = list(db_session.scalars(select(TuningRunPassage).where(TuningRunPassage.run_id == run_id)))
    assert items


def test_tuning_apply_run_creates_job_and_links_run(client, db_session, tmp_path):
    content = ("invocation offering ritual text " * 30).strip()
    path = create_local_source_file(tmp_path, "tuning-apply.txt", content=content)

    register = client.post("/api/v1/intake/register", json=_register_payload(path))
    assert register.status_code == 200
    source_id = register.json()["source_id"]

    apply_resp = client.post(
        "/api/v1/tuning/runs/apply",
        json={
            "source_id": source_id,
            "parser_strategy": "txt:clean_v1",
            "ai_enabled": False,
            "external_refs_enabled": False,
        },
    )
    assert apply_resp.status_code == 200
    job_id = apply_resp.json()["job_id"]
    run_id = apply_resp.json()["run_id"]

    run = db_session.get(TuningRun, run_id)
    assert run is not None
    assert run.mode == "apply"
    assert run.parser_strategy == "txt:clean_v1"

    job = db_session.get(IngestionJob, job_id)
    assert job is not None
    assert job.tuning_run_id == run_id
    assert job.parser_strategy == "txt:clean_v1"
    assert job_id
