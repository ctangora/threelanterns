ALTER TABLE passage_evidence
  ADD COLUMN IF NOT EXISTS translation_status VARCHAR(30) DEFAULT 'translated',
  ADD COLUMN IF NOT EXISTS detected_language_code VARCHAR(30),
  ADD COLUMN IF NOT EXISTS detected_language_label VARCHAR(120),
  ADD COLUMN IF NOT EXISTS language_detection_confidence DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS untranslated_ratio DOUBLE PRECISION DEFAULT 0,
  ADD COLUMN IF NOT EXISTS needs_reprocess BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS reprocess_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_reprocess_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS translation_provider VARCHAR(80),
  ADD COLUMN IF NOT EXISTS translation_trace_id VARCHAR(32);

UPDATE passage_evidence
SET translation_status = COALESCE(translation_status, 'translated');

UPDATE passage_evidence
SET untranslated_ratio = COALESCE(untranslated_ratio, 0);

UPDATE passage_evidence
SET needs_reprocess = COALESCE(needs_reprocess, FALSE);

UPDATE passage_evidence
SET reprocess_count = COALESCE(reprocess_count, 0);

ALTER TABLE passage_evidence
  ALTER COLUMN translation_status SET DEFAULT 'translated',
  ALTER COLUMN translation_status SET NOT NULL,
  ALTER COLUMN untranslated_ratio SET DEFAULT 0,
  ALTER COLUMN untranslated_ratio SET NOT NULL,
  ALTER COLUMN needs_reprocess SET DEFAULT FALSE,
  ALTER COLUMN needs_reprocess SET NOT NULL,
  ALTER COLUMN reprocess_count SET DEFAULT 0,
  ALTER COLUMN reprocess_count SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_passage_untranslated_ratio ON passage_evidence(untranslated_ratio);
CREATE INDEX IF NOT EXISTS ix_passage_needs_reprocess ON passage_evidence(needs_reprocess);

CREATE TABLE IF NOT EXISTS passage_reprocess_jobs (
  reprocess_job_id VARCHAR(32) PRIMARY KEY,
  passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
  idempotency_key VARCHAR(255) NOT NULL UNIQUE,
  status VARCHAR(30) NOT NULL,
  trigger_mode VARCHAR(40) NOT NULL,
  trigger_reason TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 2,
  used_pdf_crossref BOOLEAN NOT NULL DEFAULT FALSE,
  used_external_reference BOOLEAN NOT NULL DEFAULT FALSE,
  last_error TEXT,
  error_code VARCHAR(80),
  error_context_json JSON NOT NULL DEFAULT '{}'::json,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_passage_reprocess_status ON passage_reprocess_jobs(status);
CREATE INDEX IF NOT EXISTS ix_passage_reprocess_pdg ON passage_reprocess_jobs(passage_id);
CREATE INDEX IF NOT EXISTS ix_passage_reprocess_created_at ON passage_reprocess_jobs(created_at);

CREATE TABLE IF NOT EXISTS passage_translation_revisions (
  revision_id VARCHAR(32) PRIMARY KEY,
  passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
  attempt_no INTEGER NOT NULL,
  source_variant VARCHAR(64) NOT NULL,
  input_excerpt TEXT NOT NULL,
  translated_excerpt TEXT NOT NULL,
  detected_language_code VARCHAR(30),
  detected_language_label VARCHAR(120),
  untranslated_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
  quality_decision VARCHAR(40) NOT NULL,
  provenance_json JSON NOT NULL DEFAULT '{}'::json,
  translation_trace_id VARCHAR(32),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_translation_revision_passage ON passage_translation_revisions(passage_id);
CREATE INDEX IF NOT EXISTS ix_translation_revision_created_at ON passage_translation_revisions(created_at);
