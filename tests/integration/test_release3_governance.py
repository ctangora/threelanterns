from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.core import PassageEvidence, ProposalTrace
from app.services.ai import proposals
from app.services.ai.proposals import TagProposal, _store_tag_or_pending, propose_for_passage
from app.services.validation import ValidationError
from tests.helpers import create_local_source_file, register_one_source


def _create_passage(db_session, tmp_path: Path) -> PassageEvidence:
    path = create_local_source_file(tmp_path, "governance.txt", content="invocation offering ritual text")
    text, source = register_one_source(db_session, path=path)
    passage = PassageEvidence(
        text_id=text.text_id,
        source_id=source.source_id,
        source_span_locator="segment_1",
        excerpt_original="invocation offering ritual text",
        excerpt_normalized="invocation offering ritual text",
        original_language="eng",
        normalized_language="eng",
        extraction_confidence=0.9,
        reviewer_state="proposed",
        publish_state="blocked",
        created_by="test-operator",
        updated_by="test-operator",
    )
    db_session.add(passage)
    db_session.commit()
    return passage


def test_m3_ai_retry_failure_records_trace(monkeypatch, db_session, tmp_path):
    passage = _create_passage(db_session, tmp_path)
    monkeypatch.setenv("USE_MOCK_AI", "false")
    get_settings.cache_clear()

    call_count = {"count": 0}

    def _fake_openai_completion_json(*, prompt, client, model):  # noqa: ARG001
        call_count["count"] += 1
        if call_count["count"] == 1:
            return "{invalid", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        return "{also invalid", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    monkeypatch.setattr(proposals, "_openai_completion_json", _fake_openai_completion_json)

    with pytest.raises(ValidationError):
        propose_for_passage(
            db_session,
            passage=passage,
            actor="test-operator",
            idempotency_root="governance",
        )

    trace = db_session.scalar(
        select(ProposalTrace).where(
            ProposalTrace.object_id == passage.passage_id,
            ProposalTrace.proposal_type == "bundle",
        )
    )
    assert trace is not None
    assert trace.retry_count == 1
    assert trace.failure_reason is not None
    assert trace.usage_blob["mode"] == "openai_failed"


def test_m3_evidence_ids_required_for_tag_proposals(db_session, tmp_path):
    passage = _create_passage(db_session, tmp_path)
    with pytest.raises(ValidationError):
        _store_tag_or_pending(
            db_session,
            evidence=passage,
            proposal=TagProposal(
                ontology_dimension="ritual_intent",
                controlled_term="protection",
                confidence=0.7,
                evidence_ids=[],
            ),
            actor="test-operator",
        )
