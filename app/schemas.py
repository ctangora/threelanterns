from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.enums import ReviewDecisionEnum


class DiscoverRequest(BaseModel):
    max_files: int = Field(default=25, ge=1, le=500)
    root_path: str | None = None


class DiscoveredFile(BaseModel):
    path: str
    extension: str
    size_bytes: int


class DiscoverResponse(BaseModel):
    count: int
    files: list[DiscoveredFile]


class RegisterRequest(BaseModel):
    source_path: str
    canonical_title: str | None = None
    alternate_titles: list[str] = Field(default_factory=list)
    origin_culture_region: str = "europe_mediterranean"
    tradition_tags: list[str] = Field(default_factory=lambda: ["grimoire_tradition"])
    date_range_start: int | None = None
    date_range_end: int | None = None
    date_confidence: str = "unknown"
    language_set: list[str] = Field(default_factory=lambda: ["eng"])
    rights_status: str
    rights_evidence: str
    provenance_summary: str
    holding_institution: str
    accession_or_citation: str
    edition_witness_type: str = "printed"
    acquisition_method: str = "repository_download"
    source_language: str | None = None
    source_url_or_locator: str | None = None
    source_provenance_note: str


class RegisterResponse(BaseModel):
    text_id: str
    source_id: str
    registration_status: str = "created"
    duplicate_of_source_id: str | None = None
    witness_group_id: str | None = None


class BatchRegisterRequest(BaseModel):
    items: list[RegisterRequest]
    continue_on_error: bool = True


class BatchRegisterResult(BaseModel):
    source_path: str
    status: str
    text_id: str | None = None
    source_id: str | None = None
    duplicate_of_source_id: str | None = None
    witness_group_id: str | None = None
    error: str | None = None


class BatchRegisterResponse(BaseModel):
    total: int
    created: int
    exact_duplicates: int
    alternate_witnesses: int
    failed: int
    results: list[BatchRegisterResult]


class CreateIngestJobRequest(BaseModel):
    source_id: str
    idempotency_key: str | None = None


class JobResponse(BaseModel):
    job_id: str
    source_id: str
    status: str
    attempt_count: int
    max_attempts: int
    last_error: str | None = None


class ReviewQueueResponse(BaseModel):
    object_type: str
    total: int
    page: int
    page_size: int
    items: list[dict[str, Any]]


class ReviewRequest(BaseModel):
    decision: ReviewDecisionEnum
    notes: str | None = None


class ReviewResponse(BaseModel):
    review_id: str
    object_type: str
    object_id: str
    decision: str
    new_state: str


class BulkReviewRequest(BaseModel):
    object_type: str
    object_ids: list[str] = Field(min_length=1)
    decision: ReviewDecisionEnum
    notes: str | None = None


class BulkReviewResponse(BaseModel):
    object_type: str
    decision: str
    requested: int
    processed: int
    review_ids: list[str]


class PassageReprocessRequest(BaseModel):
    reason_code: str = "manual_operator_request"
    reason_note: str | None = None
    reason: str | None = None
    mode: Literal["manual", "auto"] = "manual"


class PassageReprocessResponse(BaseModel):
    reprocess_job_id: str
    passage_id: str
    status: str
    trigger_mode: str
    attempt_count: int
    max_attempts: int


class PassageQualityResponse(BaseModel):
    passage_id: str
    translation_status: str
    needs_reprocess: bool
    untranslated_ratio: float
    detected_language_code: str | None = None
    detected_language_label: str | None = None
    language_detection_confidence: float | None = None
    reprocess_count: int
    last_reprocess_at: datetime | None = None
    translation_provider: str | None = None
    translation_trace_id: str | None = None
    usability_score: float
    relevance_score: float
    relevance_state: str
    quality_notes_json: dict[str, Any]
    quality_version: str
    unresolved: bool


class ReprocessJobQueueResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict[str, Any]]


class ReprocessReasonSummaryItem(BaseModel):
    reason_code: str
    status: str
    count: int


class ReprocessReasonSummaryResponse(BaseModel):
    items: list[ReprocessReasonSummaryItem]


class ReviewMetricsResponse(BaseModel):
    generated_at: datetime
    backlog: dict[str, dict[str, int]]
    decisions_24h: int
    average_proposed_age_hours: float


class RecordResponse(BaseModel):
    object_type: str
    object_id: str
    payload: dict[str, Any]


class AuditResponse(BaseModel):
    object_type: str
    object_id: str
    events: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    timestamp: datetime


class HealthDetailsResponse(BaseModel):
    status: Literal["ok"]
    timestamp: datetime
    database_ok: bool
    queue_depth: dict[str, int]
    dead_letter_jobs: int
    worker_last_activity_at: datetime | None = None


class SearchHit(BaseModel):
    object_type: str
    object_id: str
    score: float
    snippet: str
    review_state: str | None = None


class SearchResponse(BaseModel):
    total: int
    hits: list[SearchHit]


class TuningProfileRequest(BaseModel):
    name: str
    thresholds_json: dict[str, Any] = Field(default_factory=dict)
    lexicons_json: dict[str, Any] = Field(default_factory=dict)
    segmentation_json: dict[str, Any] = Field(default_factory=dict)


class TuningProfileResponse(BaseModel):
    profile_id: str
    name: str
    is_default: bool
    thresholds_json: dict[str, Any]
    lexicons_json: dict[str, Any]
    segmentation_json: dict[str, Any]

    @classmethod
    def from_orm(cls, profile) -> "TuningProfileResponse":  # type: ignore[override]
        return cls(
            profile_id=profile.profile_id,
            name=profile.name,
            is_default=bool(profile.is_default),
            thresholds_json=profile.thresholds_json or {},
            lexicons_json=profile.lexicons_json or {},
            segmentation_json=profile.segmentation_json or {},
        )


class TuningProfilesResponse(BaseModel):
    default_profile_id: str
    items: list[TuningProfileResponse]


class TuningPreviewRequest(BaseModel):
    source_id: str
    profile_id: str | None = None
    parser_strategy: str = "auto_by_extension"


class TuningRunResponse(BaseModel):
    run_id: str
    source_id: str
    profile_id: str
    parser_strategy: str
    mode: str
    ai_enabled: bool
    external_refs_enabled: bool
    status: str
    summary_json: dict[str, Any]

    @classmethod
    def from_orm(cls, run) -> "TuningRunResponse":  # type: ignore[override]
        return cls(
            run_id=run.run_id,
            source_id=run.source_id,
            profile_id=run.profile_id,
            parser_strategy=run.parser_strategy,
            mode=run.mode,
            ai_enabled=bool(run.ai_enabled),
            external_refs_enabled=bool(run.external_refs_enabled),
            status=run.status,
            summary_json=run.summary_json or {},
        )


class TuningPreviewResponse(BaseModel):
    run: TuningRunResponse
    summary: dict[str, Any]


class TuningApplyRequest(BaseModel):
    source_id: str
    profile_id: str | None = None
    parser_strategy: str = "auto_by_extension"
    ai_enabled: bool = False
    external_refs_enabled: bool = False


class TuningApplyResponse(BaseModel):
    run_id: str
    job_id: str
    status: str


class TuningRunsResponse(BaseModel):
    items: list[TuningRunResponse]
