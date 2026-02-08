-- Witness groups and consolidation tables.

CREATE TABLE IF NOT EXISTS witness_groups (
  group_id VARCHAR(32) PRIMARY KEY,
  canonical_text_id VARCHAR(32) REFERENCES text_records(text_id),
  group_status VARCHAR(20) NOT NULL DEFAULT 'active',
  match_method VARCHAR(20) NOT NULL DEFAULT 'exact_hash',
  match_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_witness_groups_status ON witness_groups(group_status);
CREATE INDEX IF NOT EXISTS ix_witness_groups_text ON witness_groups(canonical_text_id);

CREATE TABLE IF NOT EXISTS witness_group_members (
  group_id VARCHAR(32) NOT NULL REFERENCES witness_groups(group_id),
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  member_role VARCHAR(20) NOT NULL DEFAULT 'secondary',
  parser_strategy VARCHAR(80),
  membership_reason TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL,
  PRIMARY KEY (group_id, source_id)
);

CREATE INDEX IF NOT EXISTS ix_witness_group_members_source ON witness_group_members(source_id);

CREATE TABLE IF NOT EXISTS consolidated_passages (
  consolidated_id VARCHAR(32) PRIMARY KEY,
  group_id VARCHAR(32) NOT NULL REFERENCES witness_groups(group_id),
  excerpt_merged TEXT NOT NULL,
  passage_hash VARCHAR(64) NOT NULL,
  usability_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  relevance_state VARCHAR(30) NOT NULL DEFAULT 'accepted',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_consolidated_passages_group ON consolidated_passages(group_id);
CREATE INDEX IF NOT EXISTS ix_consolidated_passages_hash ON consolidated_passages(passage_hash);

CREATE TABLE IF NOT EXISTS consolidated_passage_sources (
  consolidated_id VARCHAR(32) NOT NULL REFERENCES consolidated_passages(consolidated_id),
  passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
  source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
  similarity_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(120) NOT NULL,
  updated_by VARCHAR(120) NOT NULL,
  PRIMARY KEY (consolidated_id, passage_id)
);

CREATE INDEX IF NOT EXISTS ix_consolidated_sources_source ON consolidated_passage_sources(source_id);
