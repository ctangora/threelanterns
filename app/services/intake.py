from pathlib import Path
from typing import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import ALLOWED_SOURCE_EXTENSIONS
from app.enums import DateConfidence, RecordStatus, RightsStatus
from app.models.core import SourceMaterialRecord, TextRecord
from app.schemas import DiscoveredFile, RegisterRequest
from app.services.audit import emit_audit_event
from app.services.dedupe import build_source_fingerprint, resolve_duplicate_source
from app.services.witness import (
    FUZZY_MATCH_THRESHOLD,
    FUZZY_REVIEW_THRESHOLD,
    add_member,
    ensure_group_for_source,
    find_fuzzy_match,
    update_group_status_for_parser,
)
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


@dataclass
class RegisterOutcome:
    text: TextRecord
    source: SourceMaterialRecord
    registration_status: str
    duplicate_of_source_id: str | None
    witness_group_id: str | None


def _build_source_record(
    *,
    request: RegisterRequest,
    source_path: Path,
    text_id: str,
    source_sha256: str,
    normalized_text_sha256: str,
    witness_group_id: str | None,
    is_duplicate_of_source_id: str | None,
    actor: str,
) -> SourceMaterialRecord:
    return SourceMaterialRecord(
        text_id=text_id,
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
        source_sha256=source_sha256,
        normalized_text_sha256=normalized_text_sha256,
        witness_group_id=witness_group_id,
        is_duplicate_of_source_id=is_duplicate_of_source_id,
        created_by=actor,
        updated_by=actor,
    )


def register_source_with_outcome(
    db: Session, request: RegisterRequest, *, actor: str, correlation_id: str
) -> RegisterOutcome:
    source_path = Path(request.source_path).resolve()
    require(source_path.exists(), f"Source path not found: {source_path}")
    require(source_path.suffix.lower() in ALLOWED_SOURCE_EXTENSIONS, "Unsupported file extension")

    validate_region(request.origin_culture_region)
    validate_traditions(request.tradition_tags)

    rights_status = RightsStatus(request.rights_status)
    date_confidence = DateConfidence(request.date_confidence)
    canonical_title = request.canonical_title or _infer_title(request.source_path)
    settings = get_settings()

    existing_stmt = select(SourceMaterialRecord).where(SourceMaterialRecord.source_path == str(source_path))
    existing = db.scalar(existing_stmt)
    if existing:
        text = db.get(TextRecord, existing.text_id)
        require(text is not None, f"Source exists with missing text record: {existing.source_id}")
        group = ensure_group_for_source(
            db,
            source=existing,
            canonical_text_id=text.text_id,
            actor=actor,
            match_method="exact_hash",
            match_score=1.0,
            status="active",
        )
        add_member(
            db,
            group_id=group.group_id,
            source_id=existing.source_id,
            role="primary",
            parser_strategy="auto_by_extension",
            membership_reason="existing_source_path_match",
            actor=actor,
        )
        emit_audit_event(
            db,
            actor=actor,
            action="register_source_duplicate",
            object_type="source",
            object_id=existing.source_id,
            correlation_id=correlation_id,
            previous_state=existing.digitization_status,
            new_state=existing.digitization_status,
            metadata_blob={"source_path": str(source_path), "duplicate_status": "exact_duplicate"},
        )
        return RegisterOutcome(
            text=text,
            source=existing,
            registration_status="exact_duplicate",
            duplicate_of_source_id=existing.source_id,
            witness_group_id=group.group_id,
        )

    fingerprint = build_source_fingerprint(
        source_path,
        max_chars=settings.max_register_fingerprint_chars,
    )
    dedupe = resolve_duplicate_source(
        db,
        source_sha256=fingerprint.source_sha256,
        normalized_text_sha256=fingerprint.normalized_text_sha256,
    )

    if dedupe.status == "exact_duplicate" and dedupe.existing_source is not None:
        text = db.get(TextRecord, dedupe.existing_source.text_id)
        require(text is not None, f"Source exists with missing text record: {dedupe.existing_source.source_id}")
        group = ensure_group_for_source(
            db,
            source=dedupe.existing_source,
            canonical_text_id=text.text_id,
            actor=actor,
            match_method="exact_hash",
            match_score=1.0,
            status="active",
        )
        add_member(
            db,
            group_id=group.group_id,
            source_id=dedupe.existing_source.source_id,
            role="primary",
            parser_strategy="auto_by_extension",
            membership_reason="exact_hash_match",
            actor=actor,
        )
        emit_audit_event(
            db,
            actor=actor,
            action="register_source_duplicate",
            object_type="source",
            object_id=dedupe.existing_source.source_id,
            correlation_id=correlation_id,
            previous_state=dedupe.existing_source.digitization_status,
            new_state=dedupe.existing_source.digitization_status,
            metadata_blob={"source_path": str(source_path), "duplicate_status": "exact_duplicate"},
        )
        return RegisterOutcome(
            text=text,
            source=dedupe.existing_source,
            registration_status="exact_duplicate",
            duplicate_of_source_id=dedupe.existing_source.source_id,
            witness_group_id=group.group_id,
        )

    if dedupe.status == "alternate_witness" and dedupe.existing_source is not None:
        text = db.get(TextRecord, dedupe.existing_source.text_id)
        require(text is not None, f"Source exists with missing text record: {dedupe.existing_source.source_id}")
        group = ensure_group_for_source(
            db,
            source=dedupe.existing_source,
            canonical_text_id=text.text_id,
            actor=actor,
            match_method="normalized_hash",
            match_score=1.0,
            status="active",
        )
        source = _build_source_record(
            request=request,
            source_path=source_path,
            text_id=text.text_id,
            source_sha256=fingerprint.source_sha256,
            normalized_text_sha256=fingerprint.normalized_text_sha256,
            witness_group_id=group.group_id,
            is_duplicate_of_source_id=dedupe.existing_source.source_id,
            actor=actor,
        )
        db.add(source)
        db.flush()

        text.source_count += 1
        text.updated_by = actor
        source.updated_by = actor
        add_member(
            db,
            group_id=group.group_id,
            source_id=source.source_id,
            role="secondary",
            parser_strategy="auto_by_extension",
            membership_reason="normalized_hash_match",
            actor=actor,
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
            metadata_blob={
                "source_path": str(source_path),
                "duplicate_status": "alternate_witness",
                "duplicate_of_source_id": dedupe.existing_source.source_id,
                "witness_group_id": group.group_id,
            },
        )
        return RegisterOutcome(
            text=text,
            source=source,
            registration_status="alternate_witness",
            duplicate_of_source_id=dedupe.existing_source.source_id,
            witness_group_id=group.group_id,
        )

    fuzzy = find_fuzzy_match(
        db,
        normalized_text=fingerprint.normalized_text,
        canonical_title=canonical_title,
    )
    if fuzzy is not None and fuzzy.score >= FUZZY_MATCH_THRESHOLD:
        text = db.get(TextRecord, fuzzy.source.text_id)
        require(text is not None, f"Source exists with missing text record: {fuzzy.source.source_id}")
        group = ensure_group_for_source(
            db,
            source=fuzzy.source,
            canonical_text_id=text.text_id,
            actor=actor,
            match_method="fuzzy",
            match_score=fuzzy.score,
            status="active",
        )
        source = _build_source_record(
            request=request,
            source_path=source_path,
            text_id=text.text_id,
            source_sha256=fingerprint.source_sha256,
            normalized_text_sha256=fingerprint.normalized_text_sha256,
            witness_group_id=group.group_id,
            is_duplicate_of_source_id=fuzzy.source.source_id,
            actor=actor,
        )
        db.add(source)
        db.flush()
        text.source_count += 1
        text.updated_by = actor
        source.updated_by = actor
        add_member(
            db,
            group_id=group.group_id,
            source_id=source.source_id,
            role="secondary",
            parser_strategy="auto_by_extension",
            membership_reason=f"fuzzy_match:{fuzzy.score:.3f}",
            actor=actor,
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
            metadata_blob={
                "source_path": str(source_path),
                "duplicate_status": "fuzzy_match",
                "duplicate_of_source_id": fuzzy.source.source_id,
                "witness_group_id": group.group_id,
                "match_score": fuzzy.score,
            },
        )
        return RegisterOutcome(
            text=text,
            source=source,
            registration_status="alternate_witness",
            duplicate_of_source_id=fuzzy.source.source_id,
            witness_group_id=group.group_id,
        )

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

    source = _build_source_record(
        request=request,
        source_path=source_path,
        text_id=text.text_id,
        source_sha256=fingerprint.source_sha256,
        normalized_text_sha256=fingerprint.normalized_text_sha256,
        witness_group_id=None,
        is_duplicate_of_source_id=None,
        actor=actor,
    )
    db.add(source)
    db.flush()
    status = "active"
    match_score = 1.0
    match_method = "exact_hash"
    if fuzzy is not None and fuzzy.score >= FUZZY_REVIEW_THRESHOLD:
        status = "needs_review"
        match_score = fuzzy.score
        match_method = "fuzzy"
    group = ensure_group_for_source(
        db,
        source=source,
        canonical_text_id=text.text_id,
        actor=actor,
        match_method=match_method,
        match_score=match_score,
        status=status,
    )
    add_member(
        db,
        group_id=group.group_id,
        source_id=source.source_id,
        role="primary",
        parser_strategy="auto_by_extension",
        membership_reason=f"new_source{f' possible_fuzzy:{match_score:.3f}' if status == 'needs_review' else ''}",
        actor=actor,
    )
    update_group_status_for_parser(db, group=group, parser_strategy="auto_by_extension", actor=actor)
    source.witness_group_id = group.group_id
    source.updated_by = actor
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
        metadata_blob={
            "source_path": str(source_path),
            "duplicate_status": "created",
            "witness_group_id": source.witness_group_id,
            "match_method": match_method,
            "match_score": match_score,
        },
    )
    return RegisterOutcome(
        text=text,
        source=source,
        registration_status="created",
        duplicate_of_source_id=None,
        witness_group_id=source.witness_group_id,
    )


def register_source(db: Session, request: RegisterRequest, *, actor: str, correlation_id: str) -> tuple[TextRecord, SourceMaterialRecord]:
    outcome = register_source_with_outcome(db, request, actor=actor, correlation_id=correlation_id)
    return outcome.text, outcome.source
