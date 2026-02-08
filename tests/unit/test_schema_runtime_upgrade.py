from sqlalchemy import create_engine, inspect, text

from app.services.schema import ensure_runtime_schema


def test_runtime_schema_upgrade_adds_missing_r3_columns(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE source_material_records (
                  source_id VARCHAR(32) PRIMARY KEY,
                  text_id VARCHAR(32) NOT NULL,
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
                  created_at TIMESTAMP,
                  updated_at TIMESTAMP,
                  created_by VARCHAR(120) NOT NULL,
                  updated_by VARCHAR(120) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE ingestion_jobs (
                  job_id VARCHAR(32) PRIMARY KEY,
                  source_id VARCHAR(32) NOT NULL,
                  status VARCHAR(30) NOT NULL,
                  idempotency_key VARCHAR(255) NOT NULL,
                  attempt_count INTEGER NOT NULL DEFAULT 0,
                  max_attempts INTEGER NOT NULL DEFAULT 3,
                  last_error TEXT,
                  created_at TIMESTAMP,
                  updated_at TIMESTAMP,
                  created_by VARCHAR(120) NOT NULL,
                  updated_by VARCHAR(120) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE proposal_traces (
                  trace_id VARCHAR(32) PRIMARY KEY,
                  object_type VARCHAR(30) NOT NULL,
                  object_id VARCHAR(32) NOT NULL,
                  proposal_type VARCHAR(30) NOT NULL,
                  idempotency_key VARCHAR(255) NOT NULL,
                  model_name VARCHAR(80) NOT NULL,
                  prompt_version VARCHAR(40) NOT NULL,
                  prompt_hash VARCHAR(64) NOT NULL,
                  response_hash VARCHAR(64) NOT NULL,
                  usage_blob TEXT,
                  created_at TIMESTAMP,
                  updated_at TIMESTAMP,
                  created_by VARCHAR(120) NOT NULL,
                  updated_by VARCHAR(120) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE passage_evidence (
                  passage_id VARCHAR(32) PRIMARY KEY,
                  text_id VARCHAR(32) NOT NULL,
                  source_id VARCHAR(32) NOT NULL,
                  source_span_locator VARCHAR(255) NOT NULL,
                  excerpt_original TEXT NOT NULL,
                  excerpt_normalized TEXT NOT NULL,
                  original_language VARCHAR(30) NOT NULL,
                  normalized_language VARCHAR(30) NOT NULL,
                  extraction_confidence REAL NOT NULL,
                  reviewer_state VARCHAR(30) NOT NULL,
                  publish_state VARCHAR(30) NOT NULL,
                  created_at TIMESTAMP,
                  updated_at TIMESTAMP,
                  created_by VARCHAR(120) NOT NULL,
                  updated_by VARCHAR(120) NOT NULL
                )
                """
            )
        )

    ensure_runtime_schema(engine)

    inspector = inspect(engine)
    source_columns = {column["name"] for column in inspector.get_columns("source_material_records")}
    assert {"source_sha256", "normalized_text_sha256", "witness_group_id", "is_duplicate_of_source_id"}.issubset(
        source_columns
    )

    job_columns = {column["name"] for column in inspector.get_columns("ingestion_jobs")}
    assert {"error_code", "error_context_json", "parser_name", "parser_version"}.issubset(job_columns)

    trace_columns = {column["name"] for column in inspector.get_columns("proposal_traces")}
    assert {"raw_response_hash", "retry_count", "failure_reason"}.issubset(trace_columns)

    passage_columns = {column["name"] for column in inspector.get_columns("passage_evidence")}
    assert {
        "translation_status",
        "detected_language_code",
        "detected_language_label",
        "language_detection_confidence",
        "untranslated_ratio",
        "needs_reprocess",
        "reprocess_count",
        "last_reprocess_at",
        "translation_provider",
        "translation_trace_id",
    }.issubset(passage_columns)

    tables = set(inspector.get_table_names())
    assert {"passage_reprocess_jobs", "passage_translation_revisions"}.issubset(tables)
