from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    AuditEvent,
    CommonalityLink,
    FileArtifact,
    FlagRecord,
    IngestionJob,
    JobAttempt,
    PassageEvidence,
    PassageReprocessJob,
    PassageTranslationRevision,
    ProposalTrace,
    ReviewDecision,
    RitualPatternTag,
    SourceMaterialRecord,
    TextRecord,
    VocabularyPendingTerm,
)
from app.services.validation import ValidationError


def _model_map() -> dict[str, tuple[type, str]]:
    return {
        "text": (TextRecord, "text_id"),
        "source": (SourceMaterialRecord, "source_id"),
        "passage": (PassageEvidence, "passage_id"),
        "tag": (RitualPatternTag, "tag_id"),
        "link": (CommonalityLink, "link_id"),
        "flag": (FlagRecord, "flag_id"),
        "review": (ReviewDecision, "review_id"),
        "job": (IngestionJob, "job_id"),
        "attempt": (JobAttempt, "attempt_id"),
        "artifact": (FileArtifact, "artifact_id"),
        "reprocess_job": (PassageReprocessJob, "reprocess_job_id"),
        "translation_revision": (PassageTranslationRevision, "revision_id"),
        "trace": (ProposalTrace, "trace_id"),
        "pending_term": (VocabularyPendingTerm, "pending_id"),
        "audit_event": (AuditEvent, "audit_id"),
    }


def get_record(db: Session, object_type: str, object_id: str) -> dict[str, Any]:
    mapping = _model_map()
    if object_type not in mapping:
        raise ValidationError(f"Unsupported object type: {object_type}")
    model, id_field = mapping[object_type]
    stmt = select(model).where(getattr(model, id_field) == object_id)
    record = db.scalar(stmt)
    if record is None:
        raise ValidationError(f"Object not found: {object_type}:{object_id}")
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def infer_object_type(object_id: str) -> str:
    prefix_map = {
        "txt_": "text",
        "src_": "source",
        "psg_": "passage",
        "tag_": "tag",
        "lnk_": "link",
        "flg_": "flag",
        "rev_": "review",
        "job_": "job",
        "att_": "attempt",
        "art_": "artifact",
        "rpj_": "reprocess_job",
        "trv_": "translation_revision",
        "trc_": "trace",
        "vpt_": "pending_term",
        "aud_": "audit_event",
    }
    for prefix, object_type in prefix_map.items():
        if object_id.startswith(prefix):
            return object_type
    raise ValidationError(f"Cannot infer object type from id: {object_id}")


def get_audit_events(db: Session, object_type: str, object_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.object_type == object_type, AuditEvent.object_id == object_id)
        .order_by(AuditEvent.timestamp.asc())
    )
    rows = list(db.scalars(stmt))
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]
