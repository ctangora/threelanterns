from pathlib import Path

from app.schemas import RegisterRequest
from app.services.intake import register_source


def create_local_source_file(tmp_path: Path, name: str = "sample.txt", content: str = "ritual dawn offering circle") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def build_register_request(path: Path) -> RegisterRequest:
    return RegisterRequest(
        source_path=str(path),
        rights_status="public_domain",
        rights_evidence="test-rights",
        provenance_summary="test-provenance",
        holding_institution="test-institution",
        accession_or_citation="test-citation",
        source_provenance_note="test-source-provenance",
    )


def register_one_source(db, *, path: Path, actor: str = "test-operator"):
    request = build_register_request(path)
    text, source = register_source(db, request, actor=actor, correlation_id="test-register")
    db.commit()
    return text, source

