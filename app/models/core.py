from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import (
    DateConfidence,
    JobStatus,
    PublishState,
    RecordStatus,
    RelationType,
    ReviewDecisionEnum,
    ReviewerState,
    ReviewableObjectType,
    RightsStatus,
    SourceObjectType,
)
from app.models.base import Base, OperatorMixin, TimestampedMixin, prefixed_id


class TextRecord(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "text_records"

    text_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("txt"))
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    alternate_titles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    origin_culture_region: Mapped[str] = mapped_column(String(120), nullable=False)
    tradition_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    date_range_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_range_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_confidence: Mapped[DateConfidence] = mapped_column(Enum(DateConfidence), default=DateConfidence.unknown, nullable=False)
    language_set: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rights_status: Mapped[RightsStatus] = mapped_column(Enum(RightsStatus), nullable=False)
    provenance_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_status: Mapped[RecordStatus] = mapped_column(Enum(RecordStatus), default=RecordStatus.draft, nullable=False)
    metadata_blob: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    sources: Mapped[list["SourceMaterialRecord"]] = relationship(back_populates="text")
    passages: Mapped[list["PassageEvidence"]] = relationship(back_populates="text")


class SourceMaterialRecord(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "source_material_records"
    __table_args__ = (
        Index("ix_source_text_id", "text_id"),
        Index("ix_source_sha256", "source_sha256"),
        Index("ix_source_normalized_sha256", "normalized_text_sha256"),
        Index("ix_source_witness_group", "witness_group_id"),
    )

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("src"))
    text_id: Mapped[str] = mapped_column(ForeignKey("text_records.text_id"), nullable=False)
    holding_institution: Mapped[str] = mapped_column(String(255), nullable=False)
    accession_or_citation: Mapped[str] = mapped_column(String(512), nullable=False)
    edition_witness_type: Mapped[str] = mapped_column(String(80), nullable=False)
    acquisition_method: Mapped[str] = mapped_column(String(80), nullable=False)
    digitization_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_started")
    source_language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_url_or_locator: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rights_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance_note: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_text_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    witness_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_duplicate_of_source_id: Mapped[str | None] = mapped_column(ForeignKey("source_material_records.source_id"), nullable=True)

    text: Mapped["TextRecord"] = relationship(back_populates="sources")
    passages: Mapped[list["PassageEvidence"]] = relationship(back_populates="source")
    jobs: Mapped[list["IngestionJob"]] = relationship(back_populates="source")


class PassageEvidence(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "passage_evidence"
    __table_args__ = (
        Index("ix_passage_text_id", "text_id"),
        Index("ix_passage_source_id", "source_id"),
        Index("ix_passage_reviewer_state", "reviewer_state"),
        Index("ix_passage_extraction_confidence", "extraction_confidence"),
        Index("ix_passage_created_at", "created_at"),
    )

    passage_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("psg"))
    text_id: Mapped[str] = mapped_column(ForeignKey("text_records.text_id"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_material_records.source_id"), nullable=False)
    source_span_locator: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt_original: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    original_language: Mapped[str] = mapped_column(String(30), nullable=False)
    normalized_language: Mapped[str] = mapped_column(String(30), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reviewer_state: Mapped[ReviewerState] = mapped_column(Enum(ReviewerState), default=ReviewerState.proposed, nullable=False)
    publish_state: Mapped[PublishState] = mapped_column(Enum(PublishState), default=PublishState.blocked, nullable=False)

    text: Mapped["TextRecord"] = relationship(back_populates="passages")
    source: Mapped["SourceMaterialRecord"] = relationship(back_populates="passages")


class RitualPatternTag(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "ritual_pattern_tags"
    __table_args__ = (
        Index("ix_tag_reviewer_state", "reviewer_state"),
        Index("ix_tag_confidence", "confidence"),
        Index("ix_tag_created_at", "created_at"),
    )

    tag_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("tag"))
    ontology_dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    controlled_term: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    proposer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_state: Mapped[ReviewerState] = mapped_column(Enum(ReviewerState), default=ReviewerState.proposed, nullable=False)
    rationale_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommonalityLink(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "commonality_links"
    __table_args__ = (
        Index("ix_link_reviewer_decision", "reviewer_decision"),
        Index("ix_link_weighted_similarity_score", "weighted_similarity_score"),
        Index("ix_link_created_at", "created_at"),
    )

    link_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("lnk"))
    source_entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(Enum(RelationType), nullable=False)
    weighted_similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reviewer_decision: Mapped[ReviewerState] = mapped_column(
        Enum(ReviewerState), default=ReviewerState.proposed, nullable=False
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlagRecord(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "flag_records"
    __table_args__ = (
        Index("ix_flag_reviewer_state", "reviewer_state"),
        Index("ix_flag_created_at", "created_at"),
    )

    flag_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("flg"))
    object_type: Mapped[SourceObjectType] = mapped_column(Enum(SourceObjectType), nullable=False)
    object_id: Mapped[str] = mapped_column(String(32), nullable=False)
    flag_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reviewer_state: Mapped[ReviewerState] = mapped_column(Enum(ReviewerState), default=ReviewerState.proposed, nullable=False)


class ReviewDecision(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "review_decisions"
    __table_args__ = (Index("ix_review_object", "object_type", "object_id"),)

    review_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("rev"))
    object_type: Mapped[ReviewableObjectType] = mapped_column(Enum(ReviewableObjectType), nullable=False)
    object_id: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[ReviewDecisionEnum] = mapped_column(Enum(ReviewDecisionEnum), nullable=False)
    decision_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(80), nullable=True)


class IngestionJob(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ingestion_jobs_idempotency_key"),
        Index("ix_ingestion_jobs_status", "status"),
        Index("ix_ingestion_jobs_created_at", "created_at"),
        Index("ix_ingestion_jobs_source_id", "source_id"),
    )

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("job"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_material_records.source_id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_context_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    parser_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    source: Mapped["SourceMaterialRecord"] = relationship(back_populates="jobs")
    attempts: Mapped[list["JobAttempt"]] = relationship(back_populates="job")


class JobAttempt(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "job_attempts"
    __table_args__ = (Index("ix_job_attempt_job_id", "job_id"),)

    attempt_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("att"))
    job_id: Mapped[str] = mapped_column(ForeignKey("ingestion_jobs.job_id"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["IngestionJob"] = relationship(back_populates="attempts")


class FileArtifact(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "file_artifacts"
    __table_args__ = (Index("ix_artifact_source_id", "source_id"),)

    artifact_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("art"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_material_records.source_id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_blob: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ProposalTrace(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "proposal_traces"
    __table_args__ = (
        Index("ix_proposal_trace_object", "object_type", "object_id"),
        UniqueConstraint("idempotency_key", name="uq_proposal_traces_idempotency_key"),
    )

    trace_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("trc"))
    object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    object_id: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_blob: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class VocabularyPendingTerm(Base, TimestampedMixin, OperatorMixin):
    __tablename__ = "vocabulary_pending_terms"

    pending_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("vpt"))
    ontology_dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    proposed_term: Mapped[str] = mapped_column(String(120), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_object", "object_type", "object_id"),)

    audit_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: prefixed_id("aud"))
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    object_id: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_blob: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
