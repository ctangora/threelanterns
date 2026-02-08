from pathlib import Path


def test_m3_migration_contains_required_columns():
    path = Path(__file__).resolve().parents[2] / "migrations" / "002_m3_intake_scale.sql"
    sql = path.read_text(encoding="utf-8")

    required_tokens = [
        "source_sha256",
        "normalized_text_sha256",
        "witness_group_id",
        "is_duplicate_of_source_id",
        "error_code",
        "error_context_json",
        "parser_name",
        "parser_version",
        "retry_count",
        "failure_reason",
        "raw_response_hash",
    ]
    for token in required_tokens:
        assert token in sql


def test_r31_migration_contains_translation_quality_schema():
    path = Path(__file__).resolve().parents[2] / "migrations" / "003_r31_translation_quality.sql"
    sql = path.read_text(encoding="utf-8")

    required_tokens = [
        "translation_status",
        "detected_language_code",
        "detected_language_label",
        "language_detection_confidence",
        "untranslated_ratio",
        "needs_reprocess",
        "reprocess_count",
        "passage_reprocess_jobs",
        "passage_translation_revisions",
        "trigger_mode",
        "source_variant",
        "quality_decision",
    ]
    for token in required_tokens:
        assert token in sql


def test_r32_migration_contains_quality_and_reason_columns():
    path = Path(__file__).resolve().parents[2] / "migrations" / "004_r32_passage_quality_and_reprocess_reasons.sql"
    sql = path.read_text(encoding="utf-8")

    required_tokens = [
        "usability_score",
        "relevance_score",
        "relevance_state",
        "quality_notes_json",
        "quality_version",
        "trigger_reason_code",
        "trigger_reason_note",
        "ix_passage_usability_score",
        "ix_passage_relevance_score",
        "ix_passage_relevance_state",
        "ix_reprocess_reason_code",
    ]
    for token in required_tokens:
        assert token in sql
