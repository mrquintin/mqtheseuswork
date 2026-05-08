"""Tests for the open-questions extractor and the priority scorer.

Two surfaces under test:

  - ``extract_open_questions`` on synthetic transcripts: confirm the
    extractor catches planted unanswered questions and rejects
    rhetorical questions the speaker immediately answers.

  - ``question_priority`` scoring: confirm the score is bounded, that
    centrality cannot dominate the final number on its own, and that a
    cheap-to-resolve question in a thin-calibration domain can outscore
    a maximally-central question whose answer is expensive.
"""

from __future__ import annotations

from datetime import datetime, timezone

from noosphere.methods.extract_open_questions import (
    ExistingQuestion,
    ExtractOpenQuestionsInput,
    TranscriptTurn,
    extract_open_questions,
)
from noosphere.evaluation.question_priority import (
    DomainCalibrationFootprint,
    OpenQuestionRow,
    centrality,
    score_question,
    score_questions,
)


# ── Extractor tests ─────────────────────────────────────────────────────────


def _turn(idx: int, speaker: str, text: str) -> TranscriptTurn:
    return TranscriptTurn(speaker=speaker, text=text, turn_index=idx)


def test_extractor_catches_planted_unanswered_question():
    turns = [
        _turn(0, "A", "We've been talking about the Q3 numbers all morning."),
        _turn(
            1,
            "B",
            "Right. Is the calibration drift after Q3 actually a regression "
            "or is it a sampling artifact?",
        ),
        _turn(2, "A", "Hmm. Let's come back to that. Anyway, on to the next item."),
        _turn(3, "B", "Sure, let's talk about hiring."),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    texts = [q.text for q in out.questions]
    assert any("calibration drift" in t.lower() for t in texts), texts
    assert all(q.detection_rule in ("interrogative", "dont_know") for q in out.questions)


def test_extractor_catches_dont_know_hedge():
    turns = [
        _turn(
            0,
            "A",
            "I don't know whether the new prompt template is causing the "
            "drop in calibration or whether it's a coincidence.",
        ),
        _turn(1, "B", "Worth pulling apart later."),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 1
    assert out.questions[0].detection_rule == "dont_know"


def test_extractor_rejects_rhetorical_self_answered_in_turn():
    """A rhetorical question whose speaker answers it in the same turn."""
    turns = [
        _turn(
            0,
            "A",
            "Is the prediction market actually efficient at scoring "
            "long-horizon forecasts? Of course the prediction market is "
            "efficient at long-horizon forecasts — that's the whole "
            "premise we operate under.",
        ),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 0
    assert out.rejected_rhetorical >= 1


def test_extractor_rejects_rhetorical_self_answered_within_k_turns():
    """Speaker answers their own question two turns later."""
    turns = [
        _turn(0, "A", "Is the calibration drift a regression in our prompt template?"),
        _turn(1, "B", "Hard to say without more data."),
        _turn(
            2,
            "A",
            "Well, the answer is yes — the calibration drift is a regression "
            "in our prompt template, I dug into it last night.",
        ),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(
            turns=turns, existing_questions=[], k_turns=2
        )
    )
    assert len(out.questions) == 0
    assert out.rejected_rhetorical >= 1


def test_extractor_dedupes_against_registry():
    existing = [
        ExistingQuestion(
            id="q1",
            summary="Is the calibration drift after Q3 a regression in the prompt template?",
        )
    ]
    turns = [
        _turn(
            0,
            "A",
            "Is the calibration drift after Q3 actually a regression in the prompt template?",
        ),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=existing)
    )
    assert len(out.questions) == 0
    assert out.rejected_redundant >= 1


def test_extractor_dedupes_within_session():
    """Two near-paraphrase questions in the same transcript collapse to one."""
    turns = [
        _turn(0, "A", "Is the calibration drift after Q3 a prompt-template regression?"),
        _turn(1, "B", "Worth checking."),
        _turn(2, "A", "Right. Is the Q3 calibration drift caused by a prompt-template regression?"),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 1
    assert out.rejected_redundant >= 1


def test_extractor_distinguishes_interrogative_from_declarative():
    turns = [
        _turn(0, "A", "The calibration drift after Q3 is a prompt-template regression."),
        _turn(1, "B", "Agreed."),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 0


def test_extractor_filters_too_short_questions():
    """A question with too few content tokens shouldn't enter the queue."""
    turns = [_turn(0, "A", "Why?")]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 0
    assert out.rejected_too_short >= 1


def test_extractor_mixed_transcript():
    """Multiple plants + multiple rejections in one transcript."""
    turns = [
        _turn(0, "A", "Welcome everyone."),
        _turn(
            1,
            "B",
            "Is our reviewer panel calibrated against the GJP open dataset?",
        ),  # planted, unanswered
        _turn(
            2,
            "A",
            "Is the contradiction probe ever right about cross-domain "
            "pairs? Of course the contradiction probe is right about "
            "cross-domain pairs — we settled that last quarter.",
        ),  # rhetorical, self-answered
        _turn(
            3,
            "B",
            "I don't know whether the new contradiction probe is "
            "actually catching anti-aligned pairs or whether it's "
            "just picking up frequency drift.",
        ),  # planted, dont_know
        _turn(4, "A", "Good question, parking it."),
    ]
    out = extract_open_questions(
        ExtractOpenQuestionsInput(turns=turns, existing_questions=[])
    )
    assert len(out.questions) == 2
    assert out.rejected_rhetorical >= 1
    rules = sorted(q.detection_rule for q in out.questions)
    assert rules == ["dont_know", "interrogative"]


# ── Priority scorer tests ───────────────────────────────────────────────────


def test_priority_score_is_bounded_to_unit_interval():
    row = OpenQuestionRow(
        id="q1",
        summary="x",
        domain="forecasting",
        linked_conclusion_ids=tuple(f"c{i}" for i in range(50)),
        estimated_resolution_cost_usd=0.01,
    )
    footprint = DomainCalibrationFootprint(
        domain="forecasting",
        resolved_forecast_count=0,
        calibration_error=1.0,
    )
    score = score_question(row, domain_footprint=footprint)
    assert 0.0 <= score.score <= 1.0


def test_centrality_alone_cannot_dominate():
    """A maximally-central but expensive question in a thick-calibration
    domain must not approach a perfect score."""
    row = OpenQuestionRow(
        id="q_central",
        summary="central but expensive",
        domain="thick",
        linked_conclusion_ids=tuple(f"c{i}" for i in range(50)),
        estimated_resolution_cost_usd=10_000.0,  # max cost → replay=0
    )
    footprint = DomainCalibrationFootprint(
        domain="thick",
        resolved_forecast_count=200,  # well calibrated
        calibration_error=0.0,
    )
    score = score_question(row, domain_footprint=footprint)
    # With default weights, centrality is 0.40, so the score must not
    # exceed that by more than its component contribution.
    assert score.score <= 0.45, score


def test_cheap_thin_domain_question_can_outscore_expensive_central():
    """A niche but answerable question can rank above a maximally-
    central one."""
    central_expensive = OpenQuestionRow(
        id="q_central",
        summary="central but expensive",
        domain="thick",
        linked_conclusion_ids=tuple(f"c{i}" for i in range(50)),
        estimated_resolution_cost_usd=10_000.0,
    )
    niche_cheap = OpenQuestionRow(
        id="q_niche",
        summary="niche but cheap and high EVI",
        domain="thin",
        linked_conclusion_ids=("c1",),
        estimated_resolution_cost_usd=2.0,  # near-free
    )
    footprints = {
        "thick": DomainCalibrationFootprint(
            domain="thick", resolved_forecast_count=200
        ),
        "thin": DomainCalibrationFootprint(
            domain="thin", resolved_forecast_count=0, calibration_error=0.5
        ),
    }
    ranked = score_questions(
        [central_expensive, niche_cheap], domain_footprints=footprints
    )
    assert ranked[0].question_id == "q_niche", ranked


def test_resolved_questions_dropped_from_batch():
    rows = [
        OpenQuestionRow(
            id="q_open", summary="open", domain="x", linked_conclusion_ids=("c1",)
        ),
        OpenQuestionRow(
            id="q_resolved",
            summary="done",
            domain="x",
            linked_conclusion_ids=("c1",),
            resolved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    ranked = score_questions(rows)
    ids = [s.question_id for s in ranked]
    assert ids == ["q_open"]


def test_resolved_question_strict_scorer_raises():
    row = OpenQuestionRow(
        id="q_resolved",
        summary="done",
        domain="x",
        linked_conclusion_ids=(),
        resolved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    raised = False
    try:
        score_question(row)
    except ValueError:
        raised = True
    assert raised, "score_question should refuse a resolved row"


def test_centrality_saturates():
    # 8 conclusions → 1.0; 50 conclusions → still 1.0.
    assert centrality(8) == centrality(50) == 1.0
    assert centrality(0) == 0.0
    assert 0.0 < centrality(1) < 1.0


def test_components_sum_to_score_within_epsilon():
    row = OpenQuestionRow(
        id="q",
        summary="s",
        domain="d",
        linked_conclusion_ids=("c1", "c2"),
        estimated_resolution_cost_usd=100.0,
    )
    footprint = DomainCalibrationFootprint(
        domain="d", resolved_forecast_count=10
    )
    score = score_question(row, domain_footprint=footprint)
    total = sum(c.contribution for c in score.components)
    assert abs(total - score.score) < 1e-9
