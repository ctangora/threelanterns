from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import FileArtifact
from app.services.utils import sha256_file, sha256_text


def store_text_artifact(
    db: Session,
    *,
    source_id: str,
    artifact_type: str,
    text: str,
    actor: str,
) -> FileArtifact:
    settings = get_settings()
    source_dir = settings.artifact_root / source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    digest = sha256_text(text)
    path = source_dir / f"{artifact_type}_{digest[:16]}.txt"
    path.write_text(text, encoding="utf-8")

    artifact = FileArtifact(
        source_id=source_id,
        artifact_type=artifact_type,
        path=str(path),
        sha256=sha256_file(path),
        metadata_blob={"bytes": path.stat().st_size},
        created_by=actor,
        updated_by=actor,
    )
    db.add(artifact)
    db.flush()
    return artifact


def artifact_exists(db: Session, *, source_id: str, artifact_type: str) -> bool:
    from sqlalchemy import select

    stmt = select(FileArtifact.artifact_id).where(
        FileArtifact.source_id == source_id, FileArtifact.artifact_type == artifact_type
    )
    return db.scalar(stmt) is not None

