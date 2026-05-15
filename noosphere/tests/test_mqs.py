"""Tests for the Methodology Quality Score (MQS) scorer.

Goals:
1. Domain Sensitivity gate: a low domain-fit score caps the composite even
   when every other criterion is high.
2. Deterministic stub judge produces stable scores (so backfill is auditable
   without an LLM in the loop).
3. The evidence blob serializes and deserializes through JSON without loss
   (this is the contract the Prisma `Json` column relies on).
"""

from __future__ import annotations

import json

from noosphere.evaluation.mqs import (
    COMPOSITE_FORMULA,
    MQS_SCHEMA,
    MethodologyProfileSummary,
    MqsInput,
    StubMqsJudge,
    composite_score,
    evidence_payload,
    evidence_payload_json,
    score_conclusion,
    score_progressivity,
)


def _profile(**overrides) -> MethodologyProfileSummary:
    base = dict(
        pattern_type="empirical_calibration",
        title="Empirical calibration",
        summary="Asks what evidence would discipline the belief.",
        reasoning_moves=["convert posture into evidence thresholds"],
        transfer_targets=["forecasting"],
        assumptions=["a serious belief should expose what would defeat it"],
        failure_modes=["can quantify false precision when channel is thin"],
        confidence=0.7,
    )
    base.update(overrides)
    return MethodologyProfileSummary(**base)


def test_domain_sensitivity_acts_as_gate_on_composite() -> None:
    """A near-zero domain sensitivity must cap composite to near zero, even
    when every other criterion is at the maximum."""
    judge = StubMqsJudge(
        responses={
            "severity": {"score": 1.0, "rationale": "very severe"},
            "aim_method_fit": {"score": 1.0, "rationale": "fits"},
            "compressibility": {"score": 1.0, "rationale": "single assumption"},
            "domain_sensitivity": {"score": 0.05, "rationale": "out of domain"},
        }
    )
    out = score_conclusion(
        MqsInput(
            conclusion_id="c1",
            conclusion_text="we will exit if monthly active users falls below 10k",
            rationale="if growth flattens then thesis breaks",
            topic_hint="forecasting",
            profiles=[_profile()],
            forecast_count=2,
            has_check_back_date=True,
            dissent_claim_count=1,
        ),
        judge=judge,
    )

    # All other sub-scores high.
    assert out.progressivity.score >= 0.85
    assert out.severity.score >= 0.5
    assert out.aim_method_fit.score >= 0.9
    assert out.compressibility.score == 1.0

    # Domain sensitivity gate clamps the composite.
    assert out.domain_sensitivity.score <= 0.1
    assert out.composite <= 0.1, (
        f"Domain sensitivity gate failed: composite={out.composite}, "
        f"domain={out.domain_sensitivity.score}"
    )


def test_high_domain_sensitivity_lets_composite_reflect_other_scores() -> None:
    judge = StubMqsJudge(
        responses={
            "severity": {"score": 1.0, "rationale": "severe"},
            "aim_method_fit": {"score": 1.0, "rationale": "fits"},
            "compressibility": {"score": 1.0, "rationale": "compact"},
            "domain_sensitivity": {"score": 1.0, "rationale": "in domain"},
        }
    )
    out = score_conclusion(
        MqsInput(
            conclusion_id="c2",
            conclusion_text="we will exit if MAU falls under 10k",
            rationale="if growth flattens then thesis breaks",
            topic_hint="forecasting",
            profiles=[_profile()],
            forecast_count=2,
            has_check_back_date=True,
            dissent_claim_count=1,
        ),
        judge=judge,
    )
    assert out.composite >= 0.95


def test_no_failure_modes_caps_severity_at_threshold() -> None:
    """A method that lists no way it could fail cannot score high on severity,
    even if the LLM rates it 1.0 (rubric guard from THE_META_METHOD)."""
    judge = StubMqsJudge(
        responses={
            "severity": {"score": 1.0, "rationale": "no failures listed"},
        },
        default_score=0.5,
    )
    out = score_conclusion(
        MqsInput(
            conclusion_id="c3",
            conclusion_text="some claim",
            profiles=[_profile(failure_modes=[], assumptions=[])],
            dissent_claim_count=0,
        ),
        judge=judge,
    )
    assert out.severity.score <= 0.35
    assert out.severity.evidence["no_failure_modes_cap"] is True


def test_progressivity_is_deterministic_and_independent_of_judge() -> None:
    """Progressivity is computed without LLM input — a serious belief that
    has not produced a checkable prediction must score near zero."""
    nothing = score_progressivity(
        MqsInput(
            conclusion_id="c4",
            conclusion_text="this is true.",
            rationale="",
            forecast_count=0,
            has_check_back_date=False,
        )
    )
    assert nothing.score == 0.0

    full = score_progressivity(
        MqsInput(
            conclusion_id="c5",
            conclusion_text="if MAU < 10k by 2026 then we will exit",
            rationale="we will revisit by Q2",
            forecast_count=2,
            has_check_back_date=True,
        )
    )
    assert full.score == 1.00


def test_compressibility_penalises_assumption_stacks() -> None:
    judge = StubMqsJudge(default_score=0.5)
    one = score_conclusion(
        MqsInput(
            conclusion_id="c6",
            profiles=[_profile(assumptions=["only one"])],
        ),
        judge=judge,
    )
    five = score_conclusion(
        MqsInput(
            conclusion_id="c7",
            profiles=[_profile(assumptions=["a", "b", "c", "d", "e"])],
        ),
        judge=judge,
    )
    assert one.compressibility.score > five.compressibility.score
    assert five.compressibility.score < 0.6


def test_evidence_blob_round_trips_through_json_without_loss() -> None:
    """Prisma persists `evidence` as a Json column. The blob must serialize
    to JSON and parse back to an identical Python value."""
    judge = StubMqsJudge(
        responses={
            "severity": {"score": 0.6, "rationale": "moderate failure modes recorded"},
            "aim_method_fit": {"score": 0.7, "rationale": "method shape matches"},
            "compressibility": {"score": 0.8, "rationale": "few assumptions"},
            "domain_sensitivity": {"score": 0.5, "rationale": "borderline domain"},
        }
    )
    score = score_conclusion(
        MqsInput(
            conclusion_id="c8",
            conclusion_text="we will exit if X by 2027",
            rationale="if Y then exit",
            topic_hint="forecasting",
            profiles=[_profile()],
            forecast_count=1,
            has_check_back_date=True,
            dissent_claim_count=2,
        ),
        judge=judge,
    )

    payload = evidence_payload(score)
    encoded = evidence_payload_json(score)

    decoded = json.loads(encoded)
    assert decoded == payload, "evidence JSON did not round-trip losslessly"

    assert decoded["schema"] == MQS_SCHEMA
    assert decoded["composite_formula"] == COMPOSITE_FORMULA
    for key in (
        "progressivity",
        "severity",
        "aim_method_fit",
        "compressibility",
        "domain_sensitivity",
    ):
        assert key in decoded, f"missing sub-score evidence for {key}"
        assert isinstance(decoded[key], dict)


def test_composite_is_piecewise_gate_then_weighted_geometric_mean() -> None:
    """MQS Specification v1.0.0 §Composite: the composite is piecewise — a
    hard Domain-Sensitivity gate at DS_GATE_THRESHOLD, then the weighted
    geometric mean of the other four. Verify the formal claims directly so a
    regression to the old soft multiplicative gate would fail here. The
    exhaustive property sweep lives in test_mqs_spec.py."""
    from noosphere.evaluation.mqs import DS_GATE_THRESHOLD

    # Gate open (domain_sensitivity >= threshold): the composite is the WGM of
    # the other four and domain sensitivity no longer scales it — WGM(1,1,1,1)
    # is 1.0 even though domain_sensitivity is only 0.5.
    assert composite_score(
        progressivity=1.0,
        severity=1.0,
        aim_method_fit=1.0,
        compressibility=1.0,
        domain_sensitivity=0.5,
    ) == 1.0

    # Gate closed (below threshold) -> composite = 0 regardless of the others.
    assert composite_score(
        progressivity=1.0,
        severity=1.0,
        aim_method_fit=1.0,
        compressibility=1.0,
        domain_sensitivity=DS_GATE_THRESHOLD - 1e-6,
    ) == 0.0

    # The threshold itself is on the passing side (the gate uses strict `<`).
    assert composite_score(
        progressivity=1.0,
        severity=1.0,
        aim_method_fit=1.0,
        compressibility=1.0,
        domain_sensitivity=DS_GATE_THRESHOLD,
    ) == 1.0

    # WGM of four equal sub-scores is that value (weights sum to 1).
    composite = composite_score(
        progressivity=0.5,
        severity=0.5,
        aim_method_fit=0.5,
        compressibility=0.5,
        domain_sensitivity=1.0,
    )
    assert abs(composite - 0.5) < 1e-9

    # Weakest link: a single zeroed non-gate sub-score zeroes the composite
    # even with the gate wide open — a strong axis cannot redeem a failed one.
    assert composite_score(
        progressivity=0.0,
        severity=1.0,
        aim_method_fit=1.0,
        compressibility=1.0,
        domain_sensitivity=1.0,
    ) == 0.0
