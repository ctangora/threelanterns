from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import SourceMaterialRecord
from app.services.parsers import parse_source_file
from app.services.utils import normalize_to_english, sha256_file, sha256_text


@dataclass
class DedupeFingerprint:
    source_sha256: str
    normalized_text_sha256: str
    normalized_text: str


@dataclass
class DedupeResolution:
    status: str
    existing_source: SourceMaterialRecord | None


def build_source_fingerprint(source_path: Path, *, max_chars: int) -> DedupeFingerprint:
    source_hash = sha256_file(source_path)
    parsed = parse_source_file(source_path)
    normalized = normalize_to_english(parsed)
    if max_chars > 0:
        normalized = normalized[:max_chars]
    normalized_hash = sha256_text(normalized)
    return DedupeFingerprint(
        source_sha256=source_hash,
        normalized_text_sha256=normalized_hash,
        normalized_text=normalized,
    )


def resolve_duplicate_source(
    db: Session,
    *,
    source_sha256: str,
    normalized_text_sha256: str,
) -> DedupeResolution:
    exact_stmt = (
        select(SourceMaterialRecord)
        .where(SourceMaterialRecord.source_sha256 == source_sha256)
        .order_by(SourceMaterialRecord.created_at.asc())
        .limit(1)
    )
    exact = db.scalar(exact_stmt)
    if exact is not None:
        return DedupeResolution(status="exact_duplicate", existing_source=exact)

    witness_stmt = (
        select(SourceMaterialRecord)
        .where(SourceMaterialRecord.normalized_text_sha256 == normalized_text_sha256)
        .order_by(SourceMaterialRecord.created_at.asc())
        .limit(1)
    )
    witness = db.scalar(witness_stmt)
    if witness is not None:
        return DedupeResolution(status="alternate_witness", existing_source=witness)

    return DedupeResolution(status="new", existing_source=None)
