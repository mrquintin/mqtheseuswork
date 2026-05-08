"""Severity-rubric tests for peer-review objections.

Pins the rubric's three load-bearing properties:

1. Severity is monotonic in the structural inputs (cascade_weight,
   centrality, failure-mode severity).
2. The max-severity / blocking gate triggers at two unresolved high
   objections — not at one, not at ten lows.
3. The response-required flag fires for high; medium is encouraged;
   low is optional.
4. The LLM judge cannot self-promote past the structural ceiling.
5. Stale severities are excluded from aggregation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.evaluation.mqs import (
    MethodologyProfileSummary,
    MqsInput,
    StubMqsJudge,
    score_severity,
)
from noosphere.peer_review.severity import (
    HIGH_BLOCK_COUNT,
    LOW_MAX,
    MEDIUM_MAX,
    ObjectionSeverity,
    SeverityInputs,
    aggregate,
    cascade_weight_from_edge_confidence,
    claim_centrality_from_cascade,
    label_for,
    mark_stale,
    mqs_severity_penalty,
    score_objection,
)


# ── Bracket / label boundaries ───────────────────────────────────────


def test_label_brackets():
    assert label_for(0.0) == "low"
    assert label_for(LOW_MAX - 0.001) == "low"
    assert label_for(LOW_MAX) == "medium"
    assert label_for(MEDIUM_MAX - 0.001) == "medium"
    assert label_for(MEDIUM_MAX) == "high"
    assert label_for(1.0) == "high"


# ── Property 1: monotonic in cascade weight ──────────────────────────


def test_severity_monotonic_in_cascade_weight():
    """Holding centrality / failure-mode / source / judge fixed,
    severity must be non-decreasing in cascade_weight."""

    last = -1.0
    for cw in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
        sev = score_objection(
            SeverityInputs(
                cascade_weight=cw,
                claim_centrality=0.5,
                failure_mode_severity=0.0,
            )
        )
        assert sev.value >= last, f"non-monotone at cascade_weight={cw}"
        last = sev.value
    assert last > 0.0  # we got off the floor at the high end


def test_severity_monotonic_in_centrality():
    last = -1.0
    for c in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        sev = score_objection(
            SeverityInputs(cascade_weight=0.7, claim_centrality=c)
        )
        assert sev.value >= last
        last = sev.value


def test_severity_monotonic_in_failure_mode_severity():
    last = -1.0
    for fm in [0.0, 0.33, 0.5, 0.67, 1.0]:
        sev = score_objection(
            SeverityInputs(
                cascade_weight=0.6,
                claim_centrality=0.6,
                failure_mode_severity=fm,
            )
        )
        assert sev.value >= last
        last = sev.value


def test_source_credibility_caps_ceiling_from_above():
    """A weak source must lower the ceiling; a missing source must not
    penalise (charitable default)."""

    base = SeverityInputs(
        cascade_weight=0.9,
        claim_centrality=0.9,
        failure_mode_severity=0.5,
    )
    no_source = score_objection(base)
    weak_source = score_objection(
        SeverityInputs(
            cascade_weight=base.cascade_weight,
            claim_centrality=base.claim_centrality,
            failure_mode_severity=base.failure_mode_severity,
            source_credibility=0.2,
        )
    )
    strong_source = score_objection(
        SeverityInputs(
            cascade_weight=base.cascade_weight,
            claim_centrality=base.claim_centrality,
            failure_mode_severity=base.failure_mode_severity,
            source_credibility=0.95,
        )
    )
    assert weak_source.value < no_source.value
    assert strong_source.value <= no_source.value
    # Strong source ~ no source (just the cred multiplier near 1).
    assert abs(strong_source.value - no_source.value) < 0.1


# ── Property 4: LLM judge cannot self-promote ────────────────────────


def test_judge_cannot_promote_past_structural_ceiling():
    """A judge claiming severity 1.0 on a low-structural objection must
    be capped at the structural ceiling, not allowed to land in `high`."""

    # Tiny structural support: low cascade, low centrality, no failure
    # mode. Ceiling should be small.
    inp = SeverityInputs(
        cascade_weight=0.1,
        claim_centrality=0.1,
        failure_mode_severity=0.0,
        judge_severity=1.0,
    )
    sev = score_objection(inp)
    assert sev.judge_capped is True
    assert sev.value <= sev.bracket_ceiling
    assert sev.label != "high"


def test_judge_can_park_inside_bracket():
    """A judge that picks below the ceiling is honoured (no cap)."""

    inp = SeverityInputs(
        cascade_weight=0.9,
        claim_centrality=0.9,
        failure_mode_severity=0.5,
        judge_severity=0.4,
    )
    sev = score_objection(inp)
    assert sev.judge_capped is False
    assert sev.value == pytest.approx(0.4, abs=1e-9)


def test_judge_below_floor_promoted_up_when_failure_mode_high():
    """When the curated failure-mode prior is high and structural
    support is meaningful, the judge cannot drop the score into `low`."""

    inp = SeverityInputs(
        cascade_weight=0.7,
        claim_centrality=0.7,
        failure_mode_severity=1.0,  # curated `high`
        judge_severity=0.05,        # judge says nothing
    )
    sev = score_objection(inp)
    assert sev.bracket_floor >= LOW_MAX
    assert sev.value >= sev.bracket_floor
    assert sev.label != "low"


def test_no_judge_falls_back_to_ceiling():
    inp = SeverityInputs(
        cascade_weight=0.8,
        claim_centrality=0.8,
        failure_mode_severity=0.0,
    )
    sev = score_objection(inp)
    assert sev.value == pytest.approx(sev.bracket_ceiling, abs=1e-9)


# ── Property 2: max-severity gate ────────────────────────────────────


def _high_sev() -> ObjectionSeverity:
    return score_objection(
        SeverityInputs(
            cascade_weight=0.95,
            claim_centrality=0.95,
            failure_mode_severity=1.0,
        )
    )


def _low_sev() -> ObjectionSeverity:
    return score_objection(
        SeverityInputs(
            cascade_weight=0.1,
            claim_centrality=0.1,
            failure_mode_severity=0.0,
        )
    )


def test_two_high_severities_trip_blocking_gate():
    sevs = [_high_sev() for _ in range(HIGH_BLOCK_COUNT)]
    agg = aggregate(sevs)
    assert agg.blocking is True
    assert agg.high_count == HIGH_BLOCK_COUNT
    assert agg.response_required_high is True


def test_one_high_does_not_trip_blocking():
    agg = aggregate([_high_sev()])
    assert agg.blocking is False
    assert agg.response_required_high is True


def test_ten_low_severities_do_not_trip_blocking():
    agg = aggregate([_low_sev() for _ in range(10)])
    assert agg.blocking is False
    assert agg.high_count == 0
    assert agg.response_required_high is False


def test_resolved_high_does_not_block():
    """High severities that have a recorded reviewer/founder response
    should not count toward the publication gate."""

    sevs = [_high_sev() for _ in range(HIGH_BLOCK_COUNT)]
    # Resolve one of them.
    agg = aggregate(sevs, responses_resolved_for={0})
    # Only 1 unresolved high < HIGH_BLOCK_COUNT → no blocking.
    assert agg.blocking is False
    # But response_required_high stays true while at least one high
    # exists — the unresolved one.
    assert agg.response_required_high is True


# ── Property 3: response flags ───────────────────────────────────────


def test_response_required_for_high_only():
    high = _high_sev()
    medium = score_objection(
        SeverityInputs(
            cascade_weight=0.7,
            claim_centrality=0.5,
            failure_mode_severity=0.33,
        )
    )
    assert medium.label == "medium"
    low = _low_sev()

    agg_high = aggregate([high])
    agg_medium = aggregate([medium])
    agg_low = aggregate([low])

    assert agg_high.response_required_high is True
    assert agg_medium.response_required_high is False
    assert agg_medium.response_recommended_medium is True
    assert agg_low.response_required_high is False
    assert agg_low.response_recommended_medium is False


# ── Property 5: stale severities ─────────────────────────────────────


def test_stale_severities_excluded_from_aggregate():
    fresh = _high_sev()
    stale = mark_stale(_high_sev())
    agg = aggregate([fresh, stale])
    assert agg.high_count == 1
    assert agg.objections_total == 1


def test_mark_stale_does_not_mutate_original():
    fresh = _high_sev()
    stale = mark_stale(fresh)
    assert fresh.stale is False
    assert stale.stale is True


# ── MQS coupling ─────────────────────────────────────────────────────


def _profile_with_failure_modes() -> MethodologyProfileSummary:
    """Profile carrying at least one failure mode so the MQS
    `no_failure_modes_cap` (0.35) does not fire — we want to isolate
    the objection-severity penalty under test, not the cold-start cap.
    """

    return MethodologyProfileSummary(
        pattern_type="empirical",
        title="t",
        summary="s",
        failure_modes=["thin sample"],
        assumptions=["a"],
        confidence=0.7,
    )


def test_mqs_severity_penalty_blocking_drops_below_publish_threshold():
    """Two high-severity objections must drop the MQS Severity sub-score
    below a typical publish threshold (~0.6)."""

    base_judge = StubMqsJudge(
        responses={"severity": {"score": 0.9, "rationale": "high"}}
    )
    sevs = [_high_sev() for _ in range(HIGH_BLOCK_COUNT)]
    agg = aggregate(sevs)
    penalty = mqs_severity_penalty(agg)

    inp = MqsInput(
        conclusion_id="c-blocking",
        conclusion_text="x",
        profiles=[_profile_with_failure_modes()],
        objection_severity_penalty=penalty,
        objection_blocking=agg.blocking,
        objection_high_count=agg.high_count,
        objection_weighted_count=agg.weighted_count,
    )
    out = score_severity(inp, base_judge)
    assert agg.blocking is True
    assert out.score < 0.6, (
        f"two high objections must drop severity below publish; got {out.score}"
    )


def test_mqs_severity_penalty_low_pile_does_not_drop_below_publish():
    base_judge = StubMqsJudge(
        responses={"severity": {"score": 0.8, "rationale": "ok"}}
    )
    sevs = [_low_sev() for _ in range(10)]
    agg = aggregate(sevs)
    penalty = mqs_severity_penalty(agg)

    inp = MqsInput(
        conclusion_id="c-lowpile",
        conclusion_text="x",
        profiles=[_profile_with_failure_modes()],
        objection_severity_penalty=penalty,
        objection_blocking=agg.blocking,
        objection_low_count=agg.low_count,
        objection_weighted_count=agg.weighted_count,
    )
    out = score_severity(inp, base_judge)
    assert agg.blocking is False
    assert out.score >= 0.6


def test_mqs_severity_penalty_no_objections_is_identity():
    """No swarm objections → no penalty → sub-score unchanged."""

    base_judge = StubMqsJudge(
        responses={"severity": {"score": 0.7, "rationale": "ok"}}
    )
    agg = aggregate([])
    penalty = mqs_severity_penalty(agg)
    assert penalty == 1.0

    inp = MqsInput(
        conclusion_id="c-noobj",
        conclusion_text="x",
        profiles=[_profile_with_failure_modes()],
        objection_severity_penalty=penalty,
    )
    out = score_severity(inp, base_judge)
    assert out.score == pytest.approx(0.7, abs=1e-6)


# ── Cascade-graph integration helpers ────────────────────────────────


class _StubCascade:
    def __init__(self, fanouts: dict[str, int]):
        self._fanouts = fanouts

    def explain(self, node_id: str) -> list:
        return []

    def downstream(self, node_id: str) -> list:
        # The number of edges is what claim_centrality_from_cascade
        # cares about; the edge contents are unused.
        return [object()] * self._fanouts.get(node_id, 0)


def test_centrality_from_cascade_saturates():
    reader = _StubCascade({"a": 0, "b": 1, "c": 5, "d": 50})
    a = claim_centrality_from_cascade(reader, "a")
    b = claim_centrality_from_cascade(reader, "b")
    c = claim_centrality_from_cascade(reader, "c")
    d = claim_centrality_from_cascade(reader, "d")
    assert a == 0.0
    assert 0.3 < b < 0.5
    assert 0.7 < c < 1.0
    assert d > c
    assert d < 1.0001


def test_cascade_weight_pass_through_clamps():
    assert cascade_weight_from_edge_confidence(-1.0) == 0.0
    assert cascade_weight_from_edge_confidence(0.5) == 0.5
    assert cascade_weight_from_edge_confidence(2.0) == 1.0


# ── Severity expiry semantics ────────────────────────────────────────


def test_stale_severity_keeps_value_for_audit_but_excluded_from_gate():
    """Marking stale must preserve the historical numbers (for audit)
    but the aggregator must skip stale entries entirely."""

    fresh = _high_sev()
    stale = mark_stale(fresh)
    assert stale.value == fresh.value
    assert stale.label == fresh.label
    assert stale.scored_at == fresh.scored_at

    agg = aggregate([stale])
    assert agg.objections_total == 0
    assert agg.blocking is False


# ── Edge-case: judge None vs structural ceiling ──────────────────────


def test_zero_inputs_yield_zero_severity():
    sev = score_objection(SeverityInputs())
    assert sev.value == 0.0
    assert sev.label == "low"
    assert sev.bracket_ceiling == 0.0


def test_score_objection_serialises_to_dict_round_trip_safe():
    sev = score_objection(
        SeverityInputs(cascade_weight=0.6, claim_centrality=0.4),
        rationale="structural prior only",
    )
    d = sev.to_dict()
    assert d["label"] in {"low", "medium", "high"}
    assert 0.0 <= d["value"] <= 1.0
    assert d["bracket_floor"] <= d["bracket_ceiling"]
    assert d["inputs"]["cascade_weight"] == 0.6
    assert "scored_at" in d
