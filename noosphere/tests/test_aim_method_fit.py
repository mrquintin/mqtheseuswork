"""Tests for Aim-Method Fit — the third working criterion (THE_META_METHOD §2.3).

Three jobs:

1. The rubric's worked examples (`WORKED_EXAMPLES`) exercise the scorer
   deterministically — the prose rubric in
   docs/methods/Aim_Method_Fit_Rubric.md and the code must not drift.
2. Question-type inference is tested against a small labelled set.
3. The MQS scorer computes Aim-Method Fit from the deterministic rubric, a
   mismatch surfaces as a low sub-score, and that low score flows into the
   gating composite.
"""

from __future__ import annotations

import json

import pytest

from noosphere.evaluation.mqs import (
    COMPOSITE_TIERS,
    MethodologyProfileSummary,
    MqsInput,
    StubMqsJudge,
    composite_tier,
    score_aim_method_fit,
    score_conclusion,
    tier_rank,
)
from noosphere.inquiry.aim_method_fit import (
    LEVEL_SCORES,
    WORKED_EXAMPLES,
    MethodView,
    is_registered,
    match_worked_example,
)
from noosphere.inquiry.aim_method_fit import (
    score_aim_method_fit as rubric_score,
)
from noosphere.inquiry.question_typology import (
    ADJACENT,
    DECOMPOSES_INTO,
    QUESTION_TYPES,
    QuestionType,
    infer_question_type,
    question_type_for_query_class,
    question_types_for_method,
)


# ── 1. Worked examples exercise the scorer deterministically ───────────────


def test_every_level_has_at_least_two_worked_examples() -> None:
    by_level: dict[int, int] = {}
    for we in WORKED_EXAMPLES:
        by_level[we.level] = by_level.get(we.level, 0) + 1
    for level in range(5):
        assert by_level.get(level, 0) >= 2, (
            f"rubric level {level} has fewer than two worked examples"
        )


@pytest.mark.parametrize("we", WORKED_EXAMPLES, ids=lambda we: we.id)
def test_worked_example_reproduces_its_labelled_level(we) -> None:
    """Each worked example, run through the structural rubric, must reproduce
    its labelled level, question type, and worked-example match."""
    result = rubric_score(we.question_text, we.topic_hint, [we.method_view()])

    assert result.question_type == we.expected_question_type, (
        f"{we.id}: inferred {result.question_type.value}, "
        f"expected {we.expected_question_type.value}"
    )
    assert result.level == we.level, (
        f"{we.id}: structural level {result.level} != labelled {we.level} "
        f"(relation={result.relation})"
    )
    assert result.score == LEVEL_SCORES[we.level]
    assert result.worked_example_id == we.id
    assert result.worked_example_agrees is True


def test_worked_examples_have_no_internal_disagreements() -> None:
    """A worked-example disagreement is a rubric bug — the structural logic
    and the labelled ground truth must never diverge."""
    for we in WORKED_EXAMPLES:
        result = rubric_score(
            we.question_text, we.topic_hint, [we.method_view()]
        )
        assert result.worked_example_agrees is not False, (
            f"{we.id} disagrees: structural level {result.level}, "
            f"labelled {we.level}"
        )


def test_scorer_is_deterministic() -> None:
    we = WORKED_EXAMPLES[0]
    first = rubric_score(we.question_text, we.topic_hint, [we.method_view()])
    second = rubric_score(we.question_text, we.topic_hint, [we.method_view()])
    assert first == second


# ── 2. Question-type inference against a labelled set ──────────────────────


_LABELLED_QUESTIONS = [
    ("Will GDP grow in 2027?", "", QuestionType.PREDICTIVE),
    ("Will inflation exceed 3% next year?", "forecasting", QuestionType.PREDICTIVE),
    ("What is the firm's current headcount?", "", QuestionType.DESCRIPTIVE),
    (
        "What is the composition of the firm's asset base?",
        "",
        QuestionType.DESCRIPTIVE,
    ),
    ("Is this argument rigorous?", "", QuestionType.NORMATIVE),
    ("Is this asset a sound long-term holding?", "", QuestionType.NORMATIVE),
    ("Should we invest in this fund?", "", QuestionType.STRATEGIC),
    (
        "What product should the company build next?",
        "product strategy",
        QuestionType.STRATEGIC,
    ),
    ("How did you derive this estimate?", "", QuestionType.METHODOLOGICAL),
    (
        "How did the firm derive this conclusion?",
        "methodology",
        QuestionType.METHODOLOGICAL,
    ),
    ("What type of claim is this?", "", QuestionType.CLASSIFICATORY),
    (
        "What kind of reasoning pattern does this method use?",
        "method classification",
        QuestionType.CLASSIFICATORY,
    ),
]


@pytest.mark.parametrize(
    "text,topic,expected",
    _LABELLED_QUESTIONS,
    ids=[q[0][:40] for q in _LABELLED_QUESTIONS],
)
def test_question_type_inference_matches_labels(text, topic, expected) -> None:
    inference = infer_question_type(text, topic)
    assert inference.question_type == expected, (
        f"{text!r} (topic={topic!r}): inferred "
        f"{inference.question_type.value}, expected {expected.value} "
        f"(signals={inference.signals})"
    )
    assert 0.0 <= inference.confidence <= 1.0


def test_inference_falls_back_to_descriptive_with_zero_confidence() -> None:
    """Empty input is a guess, not a signal — confidence must say so."""
    inference = infer_question_type("", "")
    assert inference.question_type == QuestionType.DESCRIPTIVE
    assert inference.confidence == 0.0


def test_topic_hint_is_weighted_over_bare_body_signal() -> None:
    """The firm's own topic tag is a deliberate signal: a forecasting topic
    pulls a decision-rule-shaped conclusion toward predictive."""
    without_topic = infer_question_type(
        "we will exit if monthly active users falls below 10k", ""
    )
    with_topic = infer_question_type(
        "we will exit if monthly active users falls below 10k", "forecasting"
    )
    assert without_topic.question_type == QuestionType.STRATEGIC
    assert with_topic.question_type == QuestionType.PREDICTIVE


# ── 3. Typology relations are well-formed ──────────────────────────────────


def test_adjacency_is_symmetric() -> None:
    for qtype, neighbours in ADJACENT.items():
        for n in neighbours:
            assert qtype in ADJACENT[n], (
                f"adjacency not symmetric: {qtype.value}~{n.value}"
            )


def test_decomposition_targets_are_constituent_types_only() -> None:
    """DECOMPOSES_INTO is kept tight: only descriptive/classificatory answers
    are broad enough to be reusable constituents of other questions."""
    allowed = {QuestionType.DESCRIPTIVE, QuestionType.CLASSIFICATORY}
    for qtype, parts in DECOMPOSES_INTO.items():
        assert parts <= allowed, (
            f"{qtype.value} decomposes into a non-constituent type: {parts}"
        )
        assert qtype not in parts, f"{qtype.value} decomposes into itself"


def test_every_question_type_is_registered_and_described() -> None:
    assert len(QUESTION_TYPES) == 6
    for qtype in QUESTION_TYPES:
        assert qtype in ADJACENT
        assert qtype in DECOMPOSES_INTO


# ── 4. Mismatch detection ──────────────────────────────────────────────────


def test_valuation_misfits_a_product_strategy_question() -> None:
    """The firm's anchor example: a valuation method pointed at a product-
    strategy question has poor fit — level 1, not 0 (it answers a *related*
    question) and not higher (it does not answer the one asked)."""
    result = rubric_score(
        "What product should the company build next?",
        "product strategy",
        [MethodView(pattern_type="valuation", has_articulated_boundary=True)],
    )
    assert result.question_type == QuestionType.STRATEGIC
    assert result.level == 1
    assert result.score == 0.25
    assert result.relation == "related-different"


def test_valuation_cannot_answer_a_methodology_question() -> None:
    result = rubric_score(
        "How did the firm derive this conclusion?",
        "methodology",
        [MethodView(pattern_type="valuation", has_articulated_boundary=True)],
    )
    assert result.level == 0
    assert result.score == 0.0
    assert result.relation == "disjoint"


def test_unregistered_method_is_not_punished_to_zero() -> None:
    """§2.3: a method is not retired on this rubric alone. An unregistered
    method cannot be verified — that is level 2, not level 0."""
    result = rubric_score(
        "Will inflation exceed 3% next year?",
        "forecasting",
        [MethodView(pattern_type="some_brand_new_method")],
    )
    assert result.relation == "undeclared"
    assert result.level == 2
    assert not is_registered(MethodView(pattern_type="some_brand_new_method"))


def test_profile_declaration_overrides_the_registry() -> None:
    """A method may declare its served types directly; the rubric prefers
    that over the pattern_type registry."""
    # valuation does NOT serve strategic in the registry…
    assert QuestionType.STRATEGIC not in (
        question_types_for_method("valuation") or frozenset()
    )
    # …but a profile that explicitly declares it does is taken at its word.
    declared = MethodView(
        pattern_type="valuation",
        declared_question_types=(QuestionType.STRATEGIC,),
        has_articulated_boundary=True,
    )
    result = rubric_score(
        "What product should the company build next?",
        "product strategy",
        [declared],
    )
    assert result.relation == "serves"
    assert result.level == 4


def test_best_fitting_method_wins_when_a_conclusion_has_several() -> None:
    """A conclusion produced by several methods is answerable if ANY of them
    fits — the rubric takes the union of served types."""
    good = MethodView(
        pattern_type="empirical_calibration", has_articulated_boundary=True
    )
    bad = MethodView(pattern_type="valuation", has_articulated_boundary=True)
    result = rubric_score(
        "Will inflation exceed 3% next year?", "forecasting", [good, bad]
    )
    assert result.level == 4


# ── 5. MQS integration ─────────────────────────────────────────────────────


def _profile(**overrides) -> MethodologyProfileSummary:
    base = dict(
        pattern_type="empirical_calibration",
        title="Empirical calibration",
        summary="Asks what evidence would discipline the belief.",
        reasoning_moves=["convert posture into evidence thresholds"],
        transfer_targets=["forecasting"],
        assumptions=["a serious belief should expose what would defeat it"],
        failure_modes=["can quantify false precision when the channel is thin"],
        confidence=0.7,
    )
    base.update(overrides)
    return MethodologyProfileSummary(**base)


def test_mqs_aim_method_fit_is_the_deterministic_rubric() -> None:
    """The MQS sub-score is the rubric level / 4, computed without an LLM —
    a stub judge response for aim_method_fit is ignored."""
    judge = StubMqsJudge(
        responses={"aim_method_fit": {"score": 0.01, "rationale": "ignored"}}
    )
    sub = score_aim_method_fit(
        MqsInput(
            conclusion_id="c-fit",
            conclusion_text=(
                "Will the company's monthly active users stay above 10k "
                "through 2026?"
            ),
            topic_hint="forecasting",
            profiles=[_profile()],
        ),
        judge,
    )
    # empirical_calibration serves predictive + declares failure modes → L4.
    assert sub.score == 1.0
    assert sub.evidence["rule"] == "aim_method_fit_v2"
    assert sub.evidence["level"] == 4
    assert sub.evidence["question_type"] == "predictive"


def test_mqs_mismatch_surfaces_as_low_fit_and_drags_the_composite() -> None:
    """A valuation method on a product-strategy conclusion: low Aim-Method
    Fit, and the composite reflects it. With the gate open and the other
    three sub-scores held equal, the weighted geometric mean is monotone in
    Aim-Method Fit (MQS Specification v1.0.0 §Composite)."""
    judge = StubMqsJudge(default_score=1.0)
    # forecast_count / has_check_back_date pin progressivity equal and
    # non-zero for both, so Aim-Method Fit is the only mover.
    misfit = score_conclusion(
        MqsInput(
            conclusion_id="c-misfit",
            conclusion_text="What product should the company build next?",
            topic_hint="product strategy",
            profiles=[_profile(pattern_type="valuation")],
            forecast_count=2,
            has_check_back_date=True,
        ),
        judge=judge,
    )
    well_fit = score_conclusion(
        MqsInput(
            conclusion_id="c-wellfit",
            conclusion_text=(
                "Will the company's monthly active users stay above 10k "
                "through 2026?"
            ),
            topic_hint="forecasting",
            profiles=[_profile(pattern_type="empirical_calibration")],
            forecast_count=2,
            has_check_back_date=True,
        ),
        judge=judge,
    )
    assert misfit.aim_method_fit.score == 0.25
    assert well_fit.aim_method_fit.score == 1.0
    assert misfit.progressivity.score == well_fit.progressivity.score
    # Same judge, same other inputs — the only mover is Aim-Method Fit.
    assert misfit.composite < well_fit.composite


def test_mqs_aim_method_fit_evidence_round_trips_through_json() -> None:
    sub = score_aim_method_fit(
        MqsInput(
            conclusion_id="c-json",
            conclusion_text="Is this asset a sound long-term holding?",
            profiles=[_profile(pattern_type="representational_geometry")],
        ),
    )
    decoded = json.loads(json.dumps(sub.evidence, default=str))
    assert decoded == sub.evidence
    assert decoded["relation"] == "answers-part"
    assert decoded["level"] == 2


def test_mqs_handles_a_conclusion_with_no_profiles() -> None:
    """No producing method → fit cannot be assessed → neutral level 2,
    never a crash."""
    sub = score_aim_method_fit(
        MqsInput(conclusion_id="c-empty", conclusion_text="some claim", profiles=[])
    )
    assert sub.evidence["relation"] == "no-method"
    assert sub.score == 0.5


# ── 6. Composite tiers ─────────────────────────────────────────────────────


def test_composite_tier_boundaries() -> None:
    assert composite_tier(0.90) == "strong"
    assert composite_tier(0.66) == "strong"
    assert composite_tier(0.65) == "adequate"
    assert composite_tier(0.40) == "adequate"
    assert composite_tier(0.39) == "provisional"
    assert composite_tier(0.15) == "provisional"
    assert composite_tier(0.14) == "failing"
    assert composite_tier(0.0) == "failing"


def test_tier_rank_orders_high_to_low() -> None:
    assert tier_rank("strong") > tier_rank("adequate")
    assert tier_rank("adequate") > tier_rank("provisional")
    assert tier_rank("provisional") > tier_rank("failing")
    # A re-score that moves adequate → provisional is a tier *drop*.
    assert tier_rank("provisional") < tier_rank("adequate")


def test_composite_tiers_are_ordered_and_cover_zero() -> None:
    thresholds = [t for _, t in COMPOSITE_TIERS]
    assert thresholds == sorted(thresholds, reverse=True)
    assert COMPOSITE_TIERS[-1][1] == 0.0


# ── 7. Shared with the prompt-29 query classifier ──────────────────────────


def test_query_class_bridge_maps_every_public_query_class() -> None:
    """The typology is shared with noosphere.inference.query_classifier:
    every public-query class maps onto a QuestionType."""
    from noosphere.inference.query_classifier import QUERY_CLASSES

    for query_class in QUERY_CLASSES:
        mapped = question_type_for_query_class(query_class)
        assert isinstance(mapped, QuestionType)

    assert (
        question_type_for_query_class("prediction-request")
        == QuestionType.PREDICTIVE
    )
    assert (
        question_type_for_query_class("methodology-question")
        == QuestionType.METHODOLOGICAL
    )
    # Unknown / None degrade to the neutral type rather than crashing.
    assert question_type_for_query_class(None) == QuestionType.DESCRIPTIVE
    assert question_type_for_query_class("not-a-class") == QuestionType.DESCRIPTIVE


def test_match_worked_example_finds_documented_pairs() -> None:
    we = match_worked_example(
        QuestionType.STRATEGIC,
        [MethodView(pattern_type="valuation")],
    )
    assert we is not None
    assert we.id == "WE-1a"
    # An undocumented pair returns None.
    assert (
        match_worked_example(
            QuestionType.STRATEGIC,
            [MethodView(pattern_type="empirical_calibration")],
        )
        is None
    )
