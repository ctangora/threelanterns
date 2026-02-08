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

