-- Tuning Console: profiles + runs + preview passages, plus linkage fields.

CREATE TABLE IF NOT EXISTS tuning_profiles (
  profile_id VARCHAR(32) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  thresholds_json JSON NOT NULL DEFAULT '{}'::json,
  lexicons_json JSON NOT NULL DEFAULT '{}'::json,
  segmentation_json JSON NOT NULL DEFAULT '{}'::json,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tuning_profiles_default ON tuning_profiles(is_default);
CREATE INDEX IF NOT EXISTS ix_tuning_profiles_name ON tuning_profiles(name);

CREATE TABLE IF NOT EXISTS tuning_runs (
  run_id VARCHAR(32) PRIMARY KEY,
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  profile_id VARCHAR(32) NOT NULL REFERENCES tuning_profiles(profile_id),
  profile_snapshot_json JSON NOT NULL DEFAULT '{}'::json,
  parser_strategy VARCHAR(80) NOT NULL DEFAULT 'auto_by_extension',
  mode VARCHAR(20) NOT NULL,
  ai_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  external_refs_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  summary_json JSON NOT NULL DEFAULT '{}'::json,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tuning_runs_source ON tuning_runs(source_id);
CREATE INDEX IF NOT EXISTS ix_tuning_runs_profile ON tuning_runs(profile_id);
CREATE INDEX IF NOT EXISTS ix_tuning_runs_created_at ON tuning_runs(created_at);
CREATE INDEX IF NOT EXISTS ix_tuning_runs_status ON tuning_runs(status);

CREATE TABLE IF NOT EXISTS tuning_run_passages (
  run_passage_id VARCHAR(32) PRIMARY KEY,
  run_id VARCHAR(32) NOT NULL REFERENCES tuning_runs(run_id),
  ordinal INTEGER NOT NULL,
  excerpt_original TEXT NOT NULL,
  usability_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  relevance_state VARCHAR(30) NOT NULL DEFAULT 'accepted',
  quality_notes_json JSON NOT NULL DEFAULT '{}'::json,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tuning_run_passages_run ON tuning_run_passages(run_id);
CREATE INDEX IF NOT EXISTS ix_tuning_run_passages_ordinal ON tuning_run_passages(run_id, ordinal);

ALTER TABLE passage_evidence
  ADD COLUMN IF NOT EXISTS produced_by_run_id VARCHAR(32),
  ADD COLUMN IF NOT EXISTS superseded_by_run_id VARCHAR(32);

CREATE INDEX IF NOT EXISTS ix_passage_produced_by_run ON passage_evidence(produced_by_run_id);
CREATE INDEX IF NOT EXISTS ix_passage_superseded_by_run ON passage_evidence(superseded_by_run_id);

ALTER TABLE ingestion_jobs
  ADD COLUMN IF NOT EXISTS tuning_run_id VARCHAR(32),
  ADD COLUMN IF NOT EXISTS parser_strategy VARCHAR(80);

CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_tuning_run ON ingestion_jobs(tuning_run_id);
