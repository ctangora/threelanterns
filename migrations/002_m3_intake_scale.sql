ALTER TABLE source_material_records
  ADD COLUMN IF NOT EXISTS source_sha256 VARCHAR(64),
  ADD COLUMN IF NOT EXISTS normalized_text_sha256 VARCHAR(64),
  ADD COLUMN IF NOT EXISTS witness_group_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS is_duplicate_of_source_id VARCHAR(32);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_source_duplicate_source'
  ) THEN
    ALTER TABLE source_material_records
      ADD CONSTRAINT fk_source_duplicate_source
      FOREIGN KEY (is_duplicate_of_source_id) REFERENCES source_material_records(source_id);
  END IF;
END
$$;

UPDATE source_material_records
SET witness_group_id = source_id
WHERE witness_group_id IS NULL;

ALTER TABLE ingestion_jobs
  ADD COLUMN IF NOT EXISTS error_code VARCHAR(80),
  ADD COLUMN IF NOT EXISTS error_context_json JSON DEFAULT '{}'::json,
  ADD COLUMN IF NOT EXISTS parser_name VARCHAR(120),
  ADD COLUMN IF NOT EXISTS parser_version VARCHAR(40);

UPDATE ingestion_jobs
SET error_context_json = '{}'::json
WHERE error_context_json IS NULL;

ALTER TABLE ingestion_jobs
  ALTER COLUMN error_context_json SET DEFAULT '{}'::json,
  ALTER COLUMN error_context_json SET NOT NULL;

ALTER TABLE proposal_traces
  ADD COLUMN IF NOT EXISTS raw_response_hash VARCHAR(64),
  ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS failure_reason TEXT;

UPDATE proposal_traces
SET retry_count = 0
WHERE retry_count IS NULL;

ALTER TABLE proposal_traces
  ALTER COLUMN retry_count SET DEFAULT 0,
  ALTER COLUMN retry_count SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_source_sha256 ON source_material_records(source_sha256);
CREATE INDEX IF NOT EXISTS ix_source_normalized_sha256 ON source_material_records(normalized_text_sha256);
CREATE INDEX IF NOT EXISTS ix_source_witness_group ON source_material_records(witness_group_id);

CREATE INDEX IF NOT EXISTS ix_passage_reviewer_state ON passage_evidence(reviewer_state);
CREATE INDEX IF NOT EXISTS ix_passage_extraction_confidence ON passage_evidence(extraction_confidence);
CREATE INDEX IF NOT EXISTS ix_passage_created_at ON passage_evidence(created_at);

CREATE INDEX IF NOT EXISTS ix_tag_confidence ON ritual_pattern_tags(confidence);
CREATE INDEX IF NOT EXISTS ix_tag_created_at ON ritual_pattern_tags(created_at);

CREATE INDEX IF NOT EXISTS ix_link_weighted_similarity_score ON commonality_links(weighted_similarity_score);
CREATE INDEX IF NOT EXISTS ix_link_created_at ON commonality_links(created_at);

CREATE INDEX IF NOT EXISTS ix_flag_created_at ON flag_records(created_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_created_at ON ingestion_jobs(created_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_source_id ON ingestion_jobs(source_id);
