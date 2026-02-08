CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS text_records (
  text_id VARCHAR(32) PRIMARY KEY,
  canonical_title VARCHAR(512) NOT NULL,
  alternate_titles JSON NOT NULL DEFAULT '[]',
  origin_culture_region VARCHAR(120) NOT NULL,
  tradition_tags JSON NOT NULL DEFAULT '[]',
  date_range_start INTEGER,
  date_range_end INTEGER,
  date_confidence VARCHAR(20) NOT NULL,
  language_set JSON NOT NULL DEFAULT '[]',
  rights_status VARCHAR(20) NOT NULL,
  provenance_summary TEXT NOT NULL,
  source_count INTEGER NOT NULL DEFAULT 0,
  record_status VARCHAR(20) NOT NULL,
  metadata_blob JSON NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS source_material_records (
  source_id VARCHAR(32) PRIMARY KEY,
  text_id VARCHAR(32) NOT NULL REFERENCES text_records(text_id),
  holding_institution VARCHAR(255) NOT NULL,
  accession_or_citation VARCHAR(512) NOT NULL,
  edition_witness_type VARCHAR(80) NOT NULL,
  acquisition_method VARCHAR(80) NOT NULL,
  digitization_status VARCHAR(40) NOT NULL,
  source_language VARCHAR(30),
  source_url_or_locator VARCHAR(1024),
  rights_evidence TEXT NOT NULL,
  source_provenance_note TEXT NOT NULL,
  source_path VARCHAR(2048) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_source_text_id ON source_material_records(text_id);

CREATE TABLE IF NOT EXISTS passage_evidence (
  passage_id VARCHAR(32) PRIMARY KEY,
  text_id VARCHAR(32) NOT NULL REFERENCES text_records(text_id),
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  source_span_locator VARCHAR(255) NOT NULL,
  excerpt_original TEXT NOT NULL,
  excerpt_normalized TEXT NOT NULL,
  original_language VARCHAR(30) NOT NULL,
  normalized_language VARCHAR(30) NOT NULL,
  extraction_confidence DOUBLE PRECISION NOT NULL,
  reviewer_state VARCHAR(30) NOT NULL,
  publish_state VARCHAR(30) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_passage_text_id ON passage_evidence(text_id);
CREATE INDEX IF NOT EXISTS ix_passage_source_id ON passage_evidence(source_id);

CREATE TABLE IF NOT EXISTS ritual_pattern_tags (
  tag_id VARCHAR(32) PRIMARY KEY,
  ontology_dimension VARCHAR(80) NOT NULL,
  controlled_term VARCHAR(120) NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  evidence_ids JSON NOT NULL DEFAULT '[]',
  proposer_type VARCHAR(30) NOT NULL,
  reviewer_state VARCHAR(30) NOT NULL,
  rationale_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tag_reviewer_state ON ritual_pattern_tags(reviewer_state);

CREATE TABLE IF NOT EXISTS commonality_links (
  link_id VARCHAR(32) PRIMARY KEY,
  source_entity_type VARCHAR(20) NOT NULL,
  source_entity_id VARCHAR(32) NOT NULL,
  target_entity_type VARCHAR(20) NOT NULL,
  target_entity_id VARCHAR(32) NOT NULL,
  relation_type VARCHAR(30) NOT NULL,
  weighted_similarity_score DOUBLE PRECISION NOT NULL,
  evidence_ids JSON NOT NULL DEFAULT '[]',
  reviewer_decision VARCHAR(30) NOT NULL,
  decision_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_link_reviewer_decision ON commonality_links(reviewer_decision);

CREATE TABLE IF NOT EXISTS flag_records (
  flag_id VARCHAR(32) PRIMARY KEY,
  object_type VARCHAR(20) NOT NULL,
  object_id VARCHAR(32) NOT NULL,
  flag_type VARCHAR(80) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  rationale TEXT NOT NULL,
  evidence_ids JSON NOT NULL DEFAULT '[]',
  reviewer_state VARCHAR(30) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_flag_reviewer_state ON flag_records(reviewer_state);

CREATE TABLE IF NOT EXISTS review_decisions (
  review_id VARCHAR(32) PRIMARY KEY,
  object_type VARCHAR(20) NOT NULL,
  object_id VARCHAR(32) NOT NULL,
  reviewer_id VARCHAR(120) NOT NULL,
  decision VARCHAR(30) NOT NULL,
  decision_timestamp TIMESTAMPTZ NOT NULL,
  notes TEXT,
  previous_state VARCHAR(80),
  new_state VARCHAR(80),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_review_object ON review_decisions(object_type, object_id);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
  job_id VARCHAR(32) PRIMARY KEY,
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  status VARCHAR(30) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL UNIQUE,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status ON ingestion_jobs(status);

CREATE TABLE IF NOT EXISTS job_attempts (
  attempt_id VARCHAR(32) PRIMARY KEY,
  job_id VARCHAR(32) NOT NULL REFERENCES ingestion_jobs(job_id),
  attempt_no INTEGER NOT NULL,
  status VARCHAR(30) NOT NULL,
  error_detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_attempt_job_id ON job_attempts(job_id);

CREATE TABLE IF NOT EXISTS file_artifacts (
  artifact_id VARCHAR(32) PRIMARY KEY,
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  artifact_type VARCHAR(50) NOT NULL,
  path VARCHAR(2048) NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  metadata_blob JSON NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_artifact_source_id ON file_artifacts(source_id);

CREATE TABLE IF NOT EXISTS proposal_traces (
  trace_id VARCHAR(32) PRIMARY KEY,
  object_type VARCHAR(30) NOT NULL,
  object_id VARCHAR(32) NOT NULL,
  proposal_type VARCHAR(30) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL UNIQUE,
  model_name VARCHAR(80) NOT NULL,
  prompt_version VARCHAR(40) NOT NULL,
  prompt_hash VARCHAR(64) NOT NULL,
  response_hash VARCHAR(64) NOT NULL,
  usage_blob JSON NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_proposal_trace_object ON proposal_traces(object_type, object_id);

CREATE TABLE IF NOT EXISTS vocabulary_pending_terms (
  pending_id VARCHAR(32) PRIMARY KEY,
  ontology_dimension VARCHAR(80) NOT NULL,
  proposed_term VARCHAR(120) NOT NULL,
  rationale TEXT NOT NULL,
  evidence_ids JSON NOT NULL DEFAULT '[]',
  status VARCHAR(30) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  audit_id VARCHAR(32) PRIMARY KEY,
  actor VARCHAR(120) NOT NULL,
  action VARCHAR(80) NOT NULL,
  object_type VARCHAR(30) NOT NULL,
  object_id VARCHAR(32) NOT NULL,
  previous_state VARCHAR(80),
  new_state VARCHAR(80),
  correlation_id VARCHAR(64) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  metadata_blob JSON NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_audit_object ON audit_events(object_type, object_id);

