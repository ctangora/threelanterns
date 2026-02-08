ALTER TABLE passage_evidence
  ADD COLUMN IF NOT EXISTS usability_score DOUBLE PRECISION DEFAULT 0,
  ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION DEFAULT 0,
  ADD COLUMN IF NOT EXISTS relevance_state VARCHAR(30) DEFAULT 'accepted',
  ADD COLUMN IF NOT EXISTS quality_notes_json JSON DEFAULT '{}'::json,
  ADD COLUMN IF NOT EXISTS quality_version VARCHAR(40) DEFAULT 'r32_v1';

UPDATE passage_evidence
SET usability_score = COALESCE(usability_score, 0);

UPDATE passage_evidence
SET relevance_score = COALESCE(relevance_score, 0);

UPDATE passage_evidence
SET relevance_state = COALESCE(relevance_state, 'accepted');

UPDATE passage_evidence
SET quality_notes_json = COALESCE(quality_notes_json, '{}'::json);

UPDATE passage_evidence
SET quality_version = COALESCE(quality_version, 'r32_v1');

ALTER TABLE passage_evidence
  ALTER COLUMN usability_score SET DEFAULT 0,
  ALTER COLUMN usability_score SET NOT NULL,
  ALTER COLUMN relevance_score SET DEFAULT 0,
  ALTER COLUMN relevance_score SET NOT NULL,
  ALTER COLUMN relevance_state SET DEFAULT 'accepted',
  ALTER COLUMN relevance_state SET NOT NULL,
  ALTER COLUMN quality_notes_json SET DEFAULT '{}'::json,
  ALTER COLUMN quality_notes_json SET NOT NULL,
  ALTER COLUMN quality_version SET DEFAULT 'r32_v1',
  ALTER COLUMN quality_version SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_passage_usability_score ON passage_evidence(usability_score);
CREATE INDEX IF NOT EXISTS ix_passage_relevance_score ON passage_evidence(relevance_score);
CREATE INDEX IF NOT EXISTS ix_passage_relevance_state ON passage_evidence(relevance_state);

ALTER TABLE passage_reprocess_jobs
  ADD COLUMN IF NOT EXISTS trigger_reason_code VARCHAR(80) DEFAULT 'manual_operator_request',
  ADD COLUMN IF NOT EXISTS trigger_reason_note TEXT;

UPDATE passage_reprocess_jobs
SET trigger_reason_code = COALESCE(trigger_reason_code, 'manual_operator_request');

ALTER TABLE passage_reprocess_jobs
  ALTER COLUMN trigger_reason_code SET DEFAULT 'manual_operator_request',
  ALTER COLUMN trigger_reason_code SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_reprocess_reason_code ON passage_reprocess_jobs(trigger_reason_code);
