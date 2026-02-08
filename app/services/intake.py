from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import ALLOWED_SOURCE_EXTENSIONS
from app.enums import DateConfidence, RecordStatus, RightsStatus
from app.models.core import SourceMaterialRecord, TextRecord
from app.schemas import DiscoveredFile, RegisterRequest
from app.services.audit import emit_audit_event
from app.services.validation import require, validate_region, validate_traditions


def iter_discoverable_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_SOURCE_EXTENSIONS:
            continue
        yield path


def discover_local_sources(max_files: int = 25, root_path: str | None = None) -> list[DiscoveredFile]:
    settings = get_settings()
    root = Path(root_path) if root_path else settings.ingest_root
    root = root.resolve()
    require(root.exists(), f"Ingest root does not exist: {root}")

    files: list[DiscoveredFile] = []
    for path in sorted(iter_discoverable_files(root))[:max_files]:
        files.append(
            DiscoveredFile(
                path=str(path),
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
            )
        )
    return files


def _infer_title(source_path: str) -> str:
    return Path(source_path).stem.replace("_", " ").replace("-", " ").strip() or "Untitled Source"


def register_source(db: Session, request: RegisterRequest, *, actor: str, correlation_id: str) -> tuple[TextRecord, SourceMaterialRecord]:
    source_path = Path(request.source_path).resolve()
    require(source_path.exists(), f"Source path not found: {source_path}")
    require(source_path.suffix.lower() in ALLOWED_SOURCE_EXTENSIONS, "Unsupported file extension")

    validate_region(request.origin_culture_region)
    validate_traditions(request.tradition_tags)

    rights_status = RightsStatus(request.rights_status)
    date_confidence = DateConfidence(request.date_confidence)
    canonical_title = request.canonical_title or _infer_title(request.source_path)

    existing_stmt = select(SourceMaterialRecord).where(SourceMaterialRecord.source_path == str(source_path))
    existing = db.scalar(existing_stmt)
    if existing:
        text = db.get(TextRecord, existing.text_id)
        require(text is not None, f"Source exists with missing text record: {existing.source_id}")
        return text, existing

    text = TextRecord(
        canonical_title=canonical_title,
        alternate_titles=request.alternate_titles,
        origin_culture_region=request.origin_culture_region,
        tradition_tags=request.tradition_tags,
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
        date_confidence=date_confidence,
        language_set=request.language_set,
        rights_status=rights_status,
        provenance_summary=request.provenance_summary,
        source_count=1,
        record_status=RecordStatus.draft,
        created_by=actor,
        updated_by=actor,
    )
    db.add(text)
    db.flush()

    source = SourceMaterialRecord(
        text_id=text.text_id,
        holding_institution=request.holding_institution,
        accession_or_citation=request.accession_or_citation,
        edition_witness_type=request.edition_witness_type,
        acquisition_method=request.acquisition_method,
        digitization_status="not_started",
        source_language=request.source_language,
        source_url_or_locator=request.source_url_or_locator,
        rights_evidence=request.rights_evidence,
        source_provenance_note=request.source_provenance_note,
        source_path=str(source_path),
        created_by=actor,
        updated_by=actor,
    )
    db.add(source)
    db.flush()

    emit_audit_event(
        db,
        actor=actor,
        action="register_text",
        object_type="text",
        object_id=text.text_id,
        correlation_id=correlation_id,
        previous_state=None,
        new_state=text.record_status.value,
        metadata_blob={"source_path": str(source_path)},
    )
    emit_audit_event(
        db,
        actor=actor,
        action="register_source",
        object_type="source",
        object_id=source.source_id,
        correlation_id=correlation_id,
        previous_state=None,
        new_state=source.digitization_status,
    )
    return text, source

