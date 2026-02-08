from app.services.quality import classify_relevance_state, evaluate_passage_quality, score_relevance, score_usability


def test_usability_score_flags_garble_and_accepts_clean_text():
    garble = "###@@@ \ufffd\ufffd\ufffd 12345 !!!! ---- //// \\x00 \\x01 qqq qqq qqq qqq"
    clean = (
        "At dawn the practitioner offered water and incense, recited the invocation, "
        "and marked a protective circle before the altar."
    )

    garble_score, _ = score_usability(garble)
    clean_score, _ = score_usability(clean)

    assert garble_score < 0.60
    assert clean_score >= 0.60


def test_relevance_score_distinguishes_ritual_from_boilerplate():
    ritual_text = (
        "This ritual manual describes invocation, offering, consecration, and divination "
        "performed in a temple sanctuary with chants and protective symbols."
    )
    boilerplate = (
        "Table of contents chapter one chapter two all rights reserved "
        "project gutenberg navigation menu click download index page number"
    )

    ritual_score, _ = score_relevance(ritual_text)
    boilerplate_score, _ = score_relevance(boilerplate)

    assert ritual_score >= 0.50
    assert boilerplate_score < 0.30


def test_quality_assessment_includes_state_and_notes():
    text = "Invocation and offering at night with protective symbols and ritual recitation."
    assessment = evaluate_passage_quality(text)
    assert assessment.quality_version == "r32_v1"
    assert assessment.usability_score >= 0.0
    assert assessment.relevance_score >= 0.0
    assert assessment.relevance_state == classify_relevance_state(assessment.relevance_score)
    assert "usability" in assessment.notes
    assert "relevance" in assessment.notes
