from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_column(engine: Engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _add_column_if_missing(engine: Engine, table_name: str, column_name: str, definition_sql: str) -> None:
    if _has_column(engine, table_name, column_name):
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition_sql}"))


def _create_index_if_missing(engine: Engine, index_name: str, table_name: str, columns_sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns_sql})"))


def _create_table_if_missing(engine: Engine, table_name: str, create_sql: str) -> None:
    inspector = inspect(engine)
    if table_name in set(inspector.get_table_names()):
        return
    with engine.begin() as connection:
        connection.execute(text(create_sql))


def ensure_runtime_schema(engine: Engine) -> None:
    if not engine.dialect.name.startswith("sqlite"):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {"source_material_records", "ingestion_jobs", "proposal_traces", "passage_evidence"}
    if not required_tables.issubset(existing_tables):
        return

    _add_column_if_missing(engine, "source_material_records", "source_sha256", "VARCHAR(64)")
    _add_column_if_missing(engine, "source_material_records", "normalized_text_sha256", "VARCHAR(64)")
    _add_column_if_missing(engine, "source_material_records", "witness_group_id", "VARCHAR(64)")
    _add_column_if_missing(engine, "source_material_records", "is_duplicate_of_source_id", "VARCHAR(32)")

    _add_column_if_missing(engine, "ingestion_jobs", "error_code", "VARCHAR(80)")
    _add_column_if_missing(engine, "ingestion_jobs", "error_context_json", "TEXT")
    _add_column_if_missing(engine, "ingestion_jobs", "parser_name", "VARCHAR(120)")
    _add_column_if_missing(engine, "ingestion_jobs", "parser_version", "VARCHAR(40)")
    _add_column_if_missing(engine, "ingestion_jobs", "tuning_run_id", "VARCHAR(32)")
    _add_column_if_missing(engine, "ingestion_jobs", "parser_strategy", "VARCHAR(80)")
    with engine.begin() as connection:
        connection.execute(text("UPDATE ingestion_jobs SET error_context_json = '{}' WHERE error_context_json IS NULL"))

    _add_column_if_missing(engine, "proposal_traces", "raw_response_hash", "VARCHAR(64)")
    _add_column_if_missing(engine, "proposal_traces", "retry_count", "INTEGER DEFAULT 0")
    _add_column_if_missing(engine, "proposal_traces", "failure_reason", "TEXT")
    with engine.begin() as connection:
        connection.execute(text("UPDATE proposal_traces SET retry_count = 0 WHERE retry_count IS NULL"))

    _add_column_if_missing(engine, "passage_evidence", "translation_status", "VARCHAR(30) DEFAULT 'translated'")
    _add_column_if_missing(engine, "passage_evidence", "detected_language_code", "VARCHAR(30)")
    _add_column_if_missing(engine, "passage_evidence", "detected_language_label", "VARCHAR(120)")
    _add_column_if_missing(engine, "passage_evidence", "language_detection_confidence", "REAL")
    _add_column_if_missing(engine, "passage_evidence", "untranslated_ratio", "REAL DEFAULT 0")
    _add_column_if_missing(engine, "passage_evidence", "needs_reprocess", "INTEGER DEFAULT 0")
    _add_column_if_missing(engine, "passage_evidence", "reprocess_count", "INTEGER DEFAULT 0")
    _add_column_if_missing(engine, "passage_evidence", "last_reprocess_at", "TIMESTAMP")
    _add_column_if_missing(engine, "passage_evidence", "translation_provider", "VARCHAR(80)")
    _add_column_if_missing(engine, "passage_evidence", "translation_trace_id", "VARCHAR(32)")
    _add_column_if_missing(engine, "passage_evidence", "usability_score", "REAL DEFAULT 0")
    _add_column_if_missing(engine, "passage_evidence", "relevance_score", "REAL DEFAULT 0")
    _add_column_if_missing(engine, "passage_evidence", "relevance_state", "VARCHAR(30) DEFAULT 'accepted'")
    _add_column_if_missing(engine, "passage_evidence", "quality_notes_json", "TEXT DEFAULT '{}'")
    _add_column_if_missing(engine, "passage_evidence", "quality_version", "VARCHAR(40) DEFAULT 'r32_v1'")
    _add_column_if_missing(engine, "passage_evidence", "produced_by_run_id", "VARCHAR(32)")
    _add_column_if_missing(engine, "passage_evidence", "superseded_by_run_id", "VARCHAR(32)")
    with engine.begin() as connection:
        connection.execute(text("UPDATE passage_evidence SET translation_status = 'translated' WHERE translation_status IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET untranslated_ratio = 0 WHERE untranslated_ratio IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET needs_reprocess = 0 WHERE needs_reprocess IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET reprocess_count = 0 WHERE reprocess_count IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET usability_score = 0 WHERE usability_score IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET relevance_score = 0 WHERE relevance_score IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET relevance_state = 'accepted' WHERE relevance_state IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET quality_notes_json = '{}' WHERE quality_notes_json IS NULL"))
        connection.execute(text("UPDATE passage_evidence SET quality_version = 'r32_v1' WHERE quality_version IS NULL"))

    _create_table_if_missing(
        engine,
        "tuning_profiles",
        """
        CREATE TABLE tuning_profiles (
          profile_id VARCHAR(32) PRIMARY KEY,
          name VARCHAR(120) NOT NULL,
          is_default INTEGER NOT NULL DEFAULT 0,
          thresholds_json TEXT NOT NULL DEFAULT '{}',
          lexicons_json TEXT NOT NULL DEFAULT '{}',
          segmentation_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )
    _create_table_if_missing(
        engine,
        "tuning_runs",
        """
        CREATE TABLE tuning_runs (
          run_id VARCHAR(32) PRIMARY KEY,
          source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
          profile_id VARCHAR(32) NOT NULL REFERENCES tuning_profiles(profile_id),
          profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
          parser_strategy VARCHAR(80) NOT NULL DEFAULT 'auto_by_extension',
          mode VARCHAR(20) NOT NULL,
          ai_enabled INTEGER NOT NULL DEFAULT 0,
          external_refs_enabled INTEGER NOT NULL DEFAULT 0,
          status VARCHAR(20) NOT NULL DEFAULT 'pending',
          summary_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )
    _create_table_if_missing(
        engine,
        "tuning_run_passages",
        """
        CREATE TABLE tuning_run_passages (
          run_passage_id VARCHAR(32) PRIMARY KEY,
          run_id VARCHAR(32) NOT NULL REFERENCES tuning_runs(run_id),
          ordinal INTEGER NOT NULL,
          excerpt_original TEXT NOT NULL,
          usability_score REAL NOT NULL DEFAULT 0,
          relevance_score REAL NOT NULL DEFAULT 0,
          relevance_state VARCHAR(30) NOT NULL DEFAULT 'accepted',
          quality_notes_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )

    _create_table_if_missing(
        engine,
        "witness_groups",
        """
        CREATE TABLE witness_groups (
          group_id VARCHAR(32) PRIMARY KEY,
          canonical_text_id VARCHAR(32) REFERENCES text_records(text_id),
          group_status VARCHAR(20) NOT NULL DEFAULT 'active',
          match_method VARCHAR(20) NOT NULL DEFAULT 'exact_hash',
          match_score REAL NOT NULL DEFAULT 1.0,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )
    _create_table_if_missing(
        engine,
        "witness_group_members",
        """
        CREATE TABLE witness_group_members (
          group_id VARCHAR(32) NOT NULL REFERENCES witness_groups(group_id),
          source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
          member_role VARCHAR(20) NOT NULL DEFAULT 'secondary',
          parser_strategy VARCHAR(80),
          membership_reason TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL,
          PRIMARY KEY (group_id, source_id)
        )
        """,
    )
    _create_table_if_missing(
        engine,
        "consolidated_passages",
        """
        CREATE TABLE consolidated_passages (
          consolidated_id VARCHAR(32) PRIMARY KEY,
          group_id VARCHAR(32) NOT NULL REFERENCES witness_groups(group_id),
          excerpt_merged TEXT NOT NULL,
          passage_hash VARCHAR(64) NOT NULL,
          usability_score REAL NOT NULL DEFAULT 0,
          relevance_score REAL NOT NULL DEFAULT 0,
          relevance_state VARCHAR(30) NOT NULL DEFAULT 'accepted',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )
    _create_table_if_missing(
        engine,
        "consolidated_passage_sources",
        """
        CREATE TABLE consolidated_passage_sources (
          consolidated_id VARCHAR(32) NOT NULL REFERENCES consolidated_passages(consolidated_id),
          passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
          source_id VARCHAR(32) NOT NULL REFERENCES source_material_records(source_id),
          similarity_score REAL NOT NULL DEFAULT 1.0,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL,
          PRIMARY KEY (consolidated_id, passage_id)
        )
        """,
    )

    _create_table_if_missing(
        engine,
        "passage_reprocess_jobs",
        """
        CREATE TABLE passage_reprocess_jobs (
          reprocess_job_id VARCHAR(32) PRIMARY KEY,
          passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
          idempotency_key VARCHAR(255) NOT NULL UNIQUE,
          status VARCHAR(30) NOT NULL,
          trigger_mode VARCHAR(40) NOT NULL,
          trigger_reason TEXT NOT NULL,
          trigger_reason_code VARCHAR(80) NOT NULL DEFAULT 'manual_operator_request',
          trigger_reason_note TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 2,
          used_pdf_crossref INTEGER NOT NULL DEFAULT 0,
          used_external_reference INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          error_code VARCHAR(80),
          error_context_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )
    _add_column_if_missing(
        engine,
        "passage_reprocess_jobs",
        "trigger_reason_code",
        "VARCHAR(80) DEFAULT 'manual_operator_request'",
    )
    _add_column_if_missing(engine, "passage_reprocess_jobs", "trigger_reason_note", "TEXT")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE passage_reprocess_jobs SET trigger_reason_code = 'manual_operator_request' WHERE trigger_reason_code IS NULL"
            )
        )
    _create_table_if_missing(
        engine,
        "passage_translation_revisions",
        """
        CREATE TABLE passage_translation_revisions (
          revision_id VARCHAR(32) PRIMARY KEY,
          passage_id VARCHAR(32) NOT NULL REFERENCES passage_evidence(passage_id),
          attempt_no INTEGER NOT NULL,
          source_variant VARCHAR(64) NOT NULL,
          input_excerpt TEXT NOT NULL,
          translated_excerpt TEXT NOT NULL,
          detected_language_code VARCHAR(30),
          detected_language_label VARCHAR(120),
          untranslated_ratio REAL NOT NULL DEFAULT 0,
          quality_decision VARCHAR(40) NOT NULL,
          provenance_json TEXT NOT NULL DEFAULT '{}',
          translation_trace_id VARCHAR(32),
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          created_by VARCHAR(120) NOT NULL,
          updated_by VARCHAR(120) NOT NULL
        )
        """,
    )

    _create_index_if_missing(engine, "ix_source_sha256", "source_material_records", "source_sha256")
    _create_index_if_missing(engine, "ix_source_normalized_sha256", "source_material_records", "normalized_text_sha256")
    _create_index_if_missing(engine, "ix_source_witness_group", "source_material_records", "witness_group_id")
    _create_index_if_missing(engine, "ix_passage_untranslated_ratio", "passage_evidence", "untranslated_ratio")
    _create_index_if_missing(engine, "ix_passage_needs_reprocess", "passage_evidence", "needs_reprocess")
    _create_index_if_missing(engine, "ix_passage_usability_score", "passage_evidence", "usability_score")
    _create_index_if_missing(engine, "ix_passage_relevance_score", "passage_evidence", "relevance_score")
    _create_index_if_missing(engine, "ix_passage_relevance_state", "passage_evidence", "relevance_state")
    _create_index_if_missing(engine, "ix_passage_produced_by_run", "passage_evidence", "produced_by_run_id")
    _create_index_if_missing(engine, "ix_passage_superseded_by_run", "passage_evidence", "superseded_by_run_id")
    _create_index_if_missing(engine, "ix_passage_reprocess_status", "passage_reprocess_jobs", "status")
    _create_index_if_missing(engine, "ix_passage_reprocess_pdg", "passage_reprocess_jobs", "passage_id")
    _create_index_if_missing(engine, "ix_reprocess_reason_code", "passage_reprocess_jobs", "trigger_reason_code")
    _create_index_if_missing(engine, "ix_passage_reprocess_created_at", "passage_reprocess_jobs", "created_at")
    _create_index_if_missing(engine, "ix_translation_revision_passage", "passage_translation_revisions", "passage_id")
    _create_index_if_missing(engine, "ix_translation_revision_created_at", "passage_translation_revisions", "created_at")
    _create_index_if_missing(engine, "ix_tuning_profiles_default", "tuning_profiles", "is_default")
    _create_index_if_missing(engine, "ix_tuning_profiles_name", "tuning_profiles", "name")
    _create_index_if_missing(engine, "ix_tuning_runs_source", "tuning_runs", "source_id")
    _create_index_if_missing(engine, "ix_tuning_runs_profile", "tuning_runs", "profile_id")
    _create_index_if_missing(engine, "ix_tuning_runs_created_at", "tuning_runs", "created_at")
    _create_index_if_missing(engine, "ix_tuning_runs_status", "tuning_runs", "status")
    _create_index_if_missing(engine, "ix_tuning_run_passages_run", "tuning_run_passages", "run_id")
    _create_index_if_missing(engine, "ix_tuning_run_passages_ordinal", "tuning_run_passages", "run_id, ordinal")
    _create_index_if_missing(engine, "ix_witness_groups_status", "witness_groups", "group_status")
    _create_index_if_missing(engine, "ix_witness_groups_text", "witness_groups", "canonical_text_id")
    _create_index_if_missing(engine, "ix_witness_group_members_source", "witness_group_members", "source_id")
    _create_index_if_missing(engine, "ix_consolidated_passages_group", "consolidated_passages", "group_id")
    _create_index_if_missing(engine, "ix_consolidated_passages_hash", "consolidated_passages", "passage_hash")
    _create_index_if_missing(engine, "ix_consolidated_sources_source", "consolidated_passage_sources", "source_id")
