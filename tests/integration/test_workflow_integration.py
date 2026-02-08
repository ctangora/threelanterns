from sqlalchemy import select

from app.models.core import (
    CommonalityLink,
    FlagRecord,
    PassageEvidence,
    ProposalTrace,
    SourceMaterialRecord,
    TextRecord,
    VocabularyPendingTerm,
)
from app.services.ai.proposals import FlagProposal, TagProposal, _store_flag, _store_tag_or_pending
from app.services.intake import register_source
from app.services.validation import ValidationError, validate_relation_type
from app.services.workflows.ingestion import create_ingestion_job, run_worker_cycle
from tests.helpers import build_register_request, create_local_source_file


def _register(db, tmp_path, filename="flow.txt", content="dawn ritual offering circle invoke protect"):
    path = create_local_source_file(tmp_path, filename, content)
    req = build_register_request(path)
    text, source = register_source(db, req, actor="test-operator", correlation_id="it-register")
    db.commit()
    return text, source


def test_t03_invalid_vocabulary_routes_pending_queue(db_session, tmp_path):
    text, source = _register(db_session, tmp_path, "vocab.txt")
    passage = PassageEvidence(
        text_id=text.text_id,
        source_id=source.source_id,
        source_span_locator="segment_1",
        excerpt_original="ritual text",
        excerpt_normalized="ritual text",
        original_language="eng",
        normalized_language="eng",
        extraction_confidence=0.9,
        reviewer_state="proposed",
        publish_state="blocked",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(passage)
    db_session.flush()

    ok = _store_tag_or_pending(
        db_session,
        evidence=passage,
        proposal=TagProposal(ontology_dimension="ritual_intent", controlled_term="not_allowed_term", confidence=0.7),
        actor="test-operator",
    )
    db_session.commit()
    assert ok is False
    pending = db_session.scalar(select(VocabularyPendingTerm))
    assert pending is not None


def test_t04_passage_requires_span_and_language(db_session, tmp_path):
    text, source = _register(db_session, tmp_path, "span.txt")
    invalid = PassageEvidence(
        text_id=text.text_id,
        source_id=source.source_id,
        source_span_locator=None,  # type: ignore[arg-type]
        excerpt_original="x",
        excerpt_normalized="x",
        original_language="eng",
        normalized_language="eng",
        extraction_confidence=0.8,
        reviewer_state="proposed",
        publish_state="blocked",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(invalid)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        assert True
    else:
        raise AssertionError("Expected NOT NULL validation for source_span_locator")


def test_t05_commonality_requires_valid_relation_type():
    try:
        validate_relation_type("invalid_relation")
    except ValidationError:
        assert True
    else:
        raise AssertionError("Expected ValidationError for invalid relation type")


def test_t06_flag_requires_rationale_and_evidence(db_session, tmp_path):
    text, source = _register(db_session, tmp_path, "flag.txt")
    passage = PassageEvidence(
        text_id=text.text_id,
        source_id=source.source_id,
        source_span_locator="segment_1",
        excerpt_original="ritual text",
        excerpt_normalized="ritual text",
        original_language="eng",
        normalized_language="eng",
        extraction_confidence=0.8,
        reviewer_state="proposed",
        publish_state="blocked",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(passage)
    db_session.flush()

    try:
        _store_flag(
            db_session,
            evidence=passage,
            proposal=FlagProposal(flag_type="uncertain_translation", severity="low", rationale=""),
            actor="test-operator",
        )
    except ValidationError:
        assert True
    else:
        raise AssertionError("Expected ValidationError for missing rationale")


def test_t07_multilingual_fields_present_after_ingestion(db_session, tmp_path):
    _, source = _register(db_session, tmp_path, "multi.txt", content="some ritual text with invocation and offering")
    create_ingestion_job(
        db_session,
        source_id=source.source_id,
        actor="test-operator",
        idempotency_key="multi-job",
        correlation_id="multi-job",
    )
    db_session.commit()
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    passages = list(db_session.scalars(select(PassageEvidence)))
    assert len(passages) >= 1
    assert all(bool(p.excerpt_original.strip()) for p in passages)
    assert all(bool(p.excerpt_normalized.strip()) for p in passages)
    assert all(p.normalized_language == "eng" for p in passages)


def test_m2_proposal_trace_recorded(db_session, tmp_path):
    _, source = _register(db_session, tmp_path, "trace.txt", content="dawn offering invocation protect")
    create_ingestion_job(
        db_session,
        source_id=source.source_id,
        actor="test-operator",
        idempotency_key="trace-job",
        correlation_id="trace-job",
    )
    db_session.commit()
    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()
    traces = list(db_session.scalars(select(ProposalTrace)))
    assert len(traces) >= 1


def test_m2_worker_retries_to_dead_letter(db_session):
    text = TextRecord(
        canonical_title="missing-file",
        alternate_titles=[],
        origin_culture_region="europe_mediterranean",
        tradition_tags=["grimoire_tradition"],
        date_confidence="unknown",
        language_set=["eng"],
        rights_status="public_domain",
        provenance_summary="x",
        source_count=1,
        record_status="draft",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(text)
    db_session.flush()

    source = SourceMaterialRecord(
        text_id=text.text_id,
        holding_institution="x",
        accession_or_citation="x",
        edition_witness_type="printed",
        acquisition_method="repository_download",
        digitization_status="not_started",
        rights_evidence="x",
        source_provenance_note="x",
        source_path="/tmp/does-not-exist.txt",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(source)
    db_session.flush()

    job = create_ingestion_job(
        db_session,
        source_id=source.source_id,
        actor="test-operator",
        idempotency_key="retry-job",
        correlation_id="retry-job",
    )
    db_session.commit()

    for _ in range(3):
        run_worker_cycle(db_session, actor="test-operator")
        db_session.commit()

    refreshed = db_session.get(type(job), job.job_id)
    assert refreshed is not None
    assert refreshed.status.value == "dead_letter"


def test_m2_end_to_end_ingest_and_review_cycle(client, db_session, tmp_path):
    path = create_local_source_file(tmp_path, "e2e.txt", "dawn ritual offering invoke circle")
    register_payload = {
        "source_path": str(path),
        "rights_status": "public_domain",
        "rights_evidence": "test-rights",
        "provenance_summary": "test-prov",
        "holding_institution": "test-lib",
        "accession_or_citation": "test-acc",
        "source_provenance_note": "test-note",
    }
    register = client.post("/api/v1/intake/register", json=register_payload)
    assert register.status_code == 200
    source_id = register.json()["source_id"]
    job = client.post("/api/v1/jobs/ingest", json={"source_id": source_id})
    assert job.status_code == 200

    run_worker_cycle(db_session, actor="test-operator")
    db_session.commit()

    queue = client.get("/api/v1/review/queue", params={"object_type": "passage"})
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert len(items) >= 1
    object_id = items[0]["object_id"]
    reviewed = client.post(f"/api/v1/review/passage/{object_id}", json={"decision": "approve", "notes": "ok"})
    assert reviewed.status_code == 200

    links = list(db_session.scalars(select(CommonalityLink)))
    flags = list(db_session.scalars(select(FlagRecord)))
    assert isinstance(links, list)
    assert isinstance(flags, list)

