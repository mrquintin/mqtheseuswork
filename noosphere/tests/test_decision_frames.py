"""Unit tests for the multi-frame decision engine.

Covers:
- frame-level verdicts on representative contexts;
- synthesis priority rules (hard-stop > exit > reduce > unstable > majority);
- the four scenarios called out in the prompt:
  1. all frames agree on watch/trade;
  2. empirical transfer SUPPORTs but incentive frame blocks;
  3. contradiction frame forces abstain;
  4. reflexivity frame downgrades a naive edge;
- integration with ``build_decision_trace`` so a HARD_STOP from a frame
  the rule graph does not already cover (caller-supplied
  ``incentive_signals``) downgrades the trace action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.decisions.frames import (
    CONTRADICTION_HARD_STOP,
    FrameContext,
    FrameResult,
    FrameVerdict,
    MetricView,
    contradiction_frame,
    coordination_equilibrium_frame,
    empirical_transfer_frame,
    incentive_alignment_frame,
    option_value_frame,
    principal_agent_frame,
    reflexivity_frame,
    run_frames,
)
from noosphere.decisions.synthesis import (
    DecisionSynthesis,
    SynthesisAction,
    synthesize,
)
from noosphere.forecasts.decision_metrics import (
    MarketDecisionAction,
    build_decision_trace,
)


NOW = datetime(2026, 5, 12, tzinfo=timezone.utc)


def _metric(name: str, value: float, *, low_confidence: bool = False) -> MetricView:
    return MetricView(name=name, value=value, low_confidence=low_confidence)


def _strong_metrics(*, edge: float = 0.12, decay: float = 0.2) -> dict[str, MetricView]:
    """Healthy metric bundle that all frames should be happy with.

    Caller can adjust ``edge`` and ``decay`` to flex one axis at a
    time without re-typing the whole bundle.
    """
    return {
        "market_mispricing_edge": _metric("market_mispricing_edge", edge),
        "calibration_adjusted_confidence": _metric("calibration_adjusted_confidence", 0.72),
        "source_domain_locality": _metric("source_domain_locality", 0.9),
        "contradiction_pressure": _metric("contradiction_pressure", 0.05),
        "liquidity_cost_feasibility": _metric("liquidity_cost_feasibility", 0.85),
        "temporal_decay_pressure": _metric("temporal_decay_pressure", decay),
    }


# ─── Frame-level tests ───────────────────────────────────────────────


def test_contradiction_frame_hard_stop_above_threshold() -> None:
    metrics = _strong_metrics()
    metrics["contradiction_pressure"] = _metric(
        "contradiction_pressure", CONTRADICTION_HARD_STOP + 0.05
    )
    ctx = FrameContext(side="YES", metrics=metrics)
    result = contradiction_frame(ctx)
    assert result.verdict == FrameVerdict.HARD_STOP
    assert result.assumptions_stable is True


def test_contradiction_frame_low_value_supports() -> None:
    ctx = FrameContext(side="YES", metrics=_strong_metrics())
    result = contradiction_frame(ctx)
    assert result.verdict == FrameVerdict.SUPPORT


def test_incentive_alignment_redlist_hard_stops() -> None:
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        incentive_signals=("issuer_conflict",),
    )
    result = incentive_alignment_frame(ctx)
    assert result.verdict == FrameVerdict.HARD_STOP
    assert any("issuer_conflict" in r for r in result.reasons)


def test_coordination_frame_tiny_edge_watches() -> None:
    metrics = _strong_metrics(edge=0.01)
    ctx = FrameContext(side="YES", metrics=metrics)
    result = coordination_equilibrium_frame(ctx)
    assert result.verdict == FrameVerdict.WATCH


def test_coordination_frame_huge_edge_watches() -> None:
    metrics = _strong_metrics(edge=0.55)
    ctx = FrameContext(side="YES", metrics=metrics)
    result = coordination_equilibrium_frame(ctx)
    assert result.verdict == FrameVerdict.WATCH


def test_principal_agent_exit_on_revoked_principle() -> None:
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        position_state={"principles_revoked": True, "open_side": "YES"},
    )
    result = principal_agent_frame(ctx)
    assert result.verdict == FrameVerdict.EXIT


def test_principal_agent_reduce_on_side_flip() -> None:
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        position_state={"open_side": "NO"},
    )
    result = principal_agent_frame(ctx)
    assert result.verdict == FrameVerdict.REDUCE


def test_reflexivity_frame_downgrades_when_decay_high() -> None:
    metrics = _strong_metrics(edge=0.20, decay=0.7)
    ctx = FrameContext(side="YES", metrics=metrics)
    result = reflexivity_frame(ctx)
    assert result.verdict == FrameVerdict.WATCH
    assert any("decay" in r.lower() or "decay" in r for r in result.reasons)


def test_reflexivity_frame_supports_when_decay_low() -> None:
    metrics = _strong_metrics(edge=0.20, decay=0.1)
    ctx = FrameContext(side="YES", metrics=metrics)
    result = reflexivity_frame(ctx)
    assert result.verdict == FrameVerdict.SUPPORT


def test_option_value_frame_waits_when_confidence_low_and_time_remains() -> None:
    metrics = _strong_metrics()
    metrics["calibration_adjusted_confidence"] = _metric(
        "calibration_adjusted_confidence", 0.30
    )
    metrics["temporal_decay_pressure"] = _metric("temporal_decay_pressure", 0.2)
    ctx = FrameContext(side="YES", metrics=metrics)
    result = option_value_frame(ctx)
    assert result.verdict == FrameVerdict.WATCH


def test_empirical_transfer_applies_supports() -> None:
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        transfer_best_stance="APPLIES",
        transfer_best_principle_id="p_1",
        transfer_recommendation_count=3,
    )
    result = empirical_transfer_frame(ctx)
    assert result.verdict == FrameVerdict.SUPPORT


def test_empirical_transfer_does_not_apply_hard_stops_when_supported() -> None:
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        transfer_best_stance="DOES_NOT_APPLY",
        transfer_recommendation_count=3,
    )
    result = empirical_transfer_frame(ctx)
    assert result.verdict == FrameVerdict.HARD_STOP


def test_empirical_transfer_missing_report_abstains() -> None:
    ctx = FrameContext(side="YES", metrics=_strong_metrics())
    result = empirical_transfer_frame(ctx)
    assert result.verdict == FrameVerdict.ABSTAIN
    assert result.assumptions_stable is False


# ─── Synthesis priority rules ────────────────────────────────────────


def _all_supporting_results(side: str = "YES") -> list[FrameResult]:
    base = dict(
        assumptions_stable=True,
        confidence=0.8,
        side_preference=side,
        metrics_consulted=(),
        reasons=(),
        failure_modes=(),
    )
    return [
        FrameResult(name=name, verdict=FrameVerdict.SUPPORT, **base)
        for name in (
            "incentive_alignment",
            "coordination_equilibrium",
            "principal_agent",
            "reflexivity",
            "option_value",
            "contradiction",
            "empirical_transfer",
        )
    ]


def test_synthesis_all_support_returns_support() -> None:
    syn = synthesize(_all_supporting_results())
    assert syn.action == SynthesisAction.SUPPORT
    assert syn.side == "YES"
    assert syn.agreement == pytest.approx(1.0)
    assert syn.hard_stop_frames == ()


def test_synthesis_hard_stop_forces_abstain_even_with_majority_support() -> None:
    results = _all_supporting_results()
    results[0] = FrameResult(
        name="incentive_alignment",
        verdict=FrameVerdict.HARD_STOP,
        assumptions_stable=True,
        confidence=1.0,
        side_preference=None,
        metrics_consulted=(),
        reasons=("red-list incentive conflict",),
        failure_modes=(),
    )
    syn = synthesize(results)
    assert syn.action == SynthesisAction.ABSTAIN
    assert "incentive_alignment" in syn.hard_stop_frames
    assert syn.side is None


def test_synthesis_exit_overrides_supports() -> None:
    results = _all_supporting_results()
    results[2] = FrameResult(
        name="principal_agent",
        verdict=FrameVerdict.EXIT,
        assumptions_stable=True,
        confidence=1.0,
        side_preference=None,
        metrics_consulted=(),
        reasons=("principle revoked",),
        failure_modes=(),
    )
    syn = synthesize(results)
    assert syn.action == SynthesisAction.EXIT


def test_synthesis_unstable_assumptions_force_abstain() -> None:
    """When fewer than MIN_ELIGIBLE_FRAMES_FOR_SUPPORT frames have
    stable assumptions, synthesis must refuse to act regardless of how
    those few voted.
    """
    results = _all_supporting_results()
    # mark five of seven frames as having unstable assumptions →
    # only two stable frames remain, below the support floor.
    for idx in (0, 1, 2, 3, 4):
        prior = results[idx]
        results[idx] = FrameResult(
            name=prior.name,
            verdict=prior.verdict,
            assumptions_stable=False,
            confidence=prior.confidence,
            side_preference=prior.side_preference,
            metrics_consulted=prior.metrics_consulted,
            reasons=prior.reasons,
            failure_modes=prior.failure_modes,
        )
    syn = synthesize(results)
    assert syn.action == SynthesisAction.ABSTAIN


def test_synthesis_split_returns_watch() -> None:
    results = _all_supporting_results()
    results[3] = FrameResult(
        name="reflexivity",
        verdict=FrameVerdict.WATCH,
        assumptions_stable=True,
        confidence=0.3,
        side_preference="YES",
        metrics_consulted=(),
        reasons=("naive edge with high decay",),
        failure_modes=(),
    )
    # add one ABSTAIN to prevent the strict-majority shortcut
    results[6] = FrameResult(
        name="empirical_transfer",
        verdict=FrameVerdict.ABSTAIN,
        assumptions_stable=False,
        confidence=0.0,
        side_preference=None,
        metrics_consulted=(),
        reasons=("no transfer report",),
        failure_modes=(),
    )
    syn = synthesize(results)
    assert syn.action == SynthesisAction.WATCH


# ─── Scenarios called out in the prompt ──────────────────────────────


def test_scenario_all_frames_agree_on_trade() -> None:
    """All seven frames vote SUPPORT → synthesis SUPPORT, side preserved."""
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        transfer_best_stance="APPLIES",
        transfer_best_principle_id="p_1",
        transfer_recommendation_count=4,
    )
    results = run_frames(ctx)
    syn = synthesize(results, default_side="YES")
    assert syn.action == SynthesisAction.SUPPORT
    assert syn.side == "YES"
    # Every frame should be on the SUPPORT side here
    for r in results:
        assert r.verdict == FrameVerdict.SUPPORT, f"{r.name} returned {r.verdict}"


def test_scenario_transfer_supports_but_incentive_frame_blocks() -> None:
    """Transfer says APPLIES but caller flagged a known conflict → ABSTAIN."""
    ctx = FrameContext(
        side="YES",
        metrics=_strong_metrics(),
        transfer_best_stance="APPLIES",
        transfer_best_principle_id="p_1",
        transfer_recommendation_count=4,
        incentive_signals=("issuer_conflict",),
    )
    results = run_frames(ctx)
    transfer = next(r for r in results if r.name == "empirical_transfer")
    incentive = next(r for r in results if r.name == "incentive_alignment")
    assert transfer.verdict == FrameVerdict.SUPPORT
    assert incentive.verdict == FrameVerdict.HARD_STOP

    syn = synthesize(results)
    assert syn.action == SynthesisAction.ABSTAIN
    assert "incentive_alignment" in syn.hard_stop_frames


def test_scenario_contradiction_frame_forces_abstain() -> None:
    metrics = _strong_metrics()
    metrics["contradiction_pressure"] = _metric(
        "contradiction_pressure", CONTRADICTION_HARD_STOP + 0.1
    )
    ctx = FrameContext(
        side="YES",
        metrics=metrics,
        transfer_best_stance="APPLIES",
        transfer_recommendation_count=3,
    )
    results = run_frames(ctx)
    contradiction = next(r for r in results if r.name == "contradiction")
    assert contradiction.verdict == FrameVerdict.HARD_STOP
    syn = synthesize(results)
    assert syn.action == SynthesisAction.ABSTAIN
    assert "contradiction" in syn.hard_stop_frames


def test_scenario_reflexivity_downgrades_naive_edge() -> None:
    """High naive edge + high decay → reflexivity WATCH downgrades synthesis."""
    metrics = _strong_metrics(edge=0.22, decay=0.7)
    ctx = FrameContext(
        side="YES",
        metrics=metrics,
        transfer_best_stance="APPLIES",
        transfer_recommendation_count=3,
    )
    results = run_frames(ctx)
    reflex = next(r for r in results if r.name == "reflexivity")
    coord = next(r for r in results if r.name == "coordination_equilibrium")
    assert reflex.verdict == FrameVerdict.WATCH
    # coordination should also be unhappy because |edge|=0.22 is below the
    # ceiling but reflexivity is the one that names the issue.
    assert coord.verdict in (FrameVerdict.WATCH, FrameVerdict.SUPPORT)
    syn = synthesize(results)
    # With reflexivity dissenting and others SUPPORT-or-WATCH, the
    # synthesis must not return SUPPORT.
    assert syn.action in (SynthesisAction.WATCH, SynthesisAction.ABSTAIN)


# ─── Integration with build_decision_trace ───────────────────────────


@dataclass
class _FakeMarket:
    id: str = "mkt"
    organization_id: str = "org"
    title: str = "Will the policy bill pass before June?"
    category: str = "policy"
    current_yes_price: Decimal | None = Decimal("0.45")
    current_no_price: Decimal | None = Decimal("0.55")
    status: str = "OPEN"
    close_time: datetime | None = NOW + timedelta(days=30)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeSource:
    source_type: str
    source_id: str
    text: str = ""
    relevance: float = 0.8
    surfaceable: bool = True
    visibility: str = "PUBLIC"
    metadata: dict[str, Any] = field(default_factory=dict)


def _policy_sources() -> list[_FakeSource]:
    return [
        _FakeSource(
            source_type="CONCLUSION",
            source_id="c_a",
            metadata={
                "disciplines": ["policy"],
                "topic_hint": "policy",
                "created_at": (NOW - timedelta(days=20)).isoformat(),
            },
        ),
        _FakeSource(
            source_type="CLAIM",
            source_id="c_b",
            metadata={
                "disciplines": ["policy"],
                "created_at": (NOW - timedelta(days=10)).isoformat(),
            },
        ),
        _FakeSource(
            source_type="CONCLUSION",
            source_id="c_c",
            metadata={
                "disciplines": ["policy"],
                "created_at": (NOW - timedelta(days=30)).isoformat(),
            },
        ),
    ]


def _direct_citations(n: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ids = ["c_a", "c_b", "c_c"]
    for i in range(n):
        out.append(
            {
                "source_type": "CONCLUSION" if i % 2 == 0 else "CLAIM",
                "source_id": ids[i % len(ids)],
                "quoted_span": "x",
                "support_label": "DIRECT",
            }
        )
    return out


def _payload(p: float, low: float = 0.70, high: float = 0.80) -> dict[str, Any]:
    return {
        "probability_yes": p,
        "confidence_low": low,
        "confidence_high": high,
        "topic_hint": "policy",
    }


def test_build_decision_trace_attaches_frames_and_synthesis() -> None:
    market = _FakeMarket(
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload=_payload(0.75),
        now=NOW,
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
    )
    assert trace.frames, "frames should be attached to the trace"
    assert trace.synthesis is not None
    body = trace.to_dict()
    assert "frames" in body
    assert "synthesis" in body
    frame_names = {f["name"] for f in body["frames"]}
    assert frame_names >= {
        "incentive_alignment",
        "coordination_equilibrium",
        "principal_agent",
        "reflexivity",
        "option_value",
        "contradiction",
        "empirical_transfer",
    }


def test_incentive_hard_stop_downgrades_trace_to_abstain() -> None:
    """A caller-supplied incentive HARD_STOP downgrades the rule-graph
    action when the rule graph would otherwise have escalated.

    The rule graph by itself does not know about ``incentive_signals``;
    the frame engine is the only place that consumes them. So this is
    the integration's value-add: surfacing a signal the rule graph
    cannot see.
    """
    market = _FakeMarket(
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    baseline = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload=_payload(0.75),
        now=NOW,
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
    )
    assert baseline.action in (
        MarketDecisionAction.PAPER_TRADE,
        MarketDecisionAction.LIVE_CANDIDATE,
    )

    blocked = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload=_payload(0.75),
        now=NOW,
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
        incentive_signals=("issuer_conflict",),
    )
    assert blocked.action == MarketDecisionAction.ABSTAIN
    assert blocked.side is None
    assert blocked.synthesis is not None
    assert "incentive_alignment" in blocked.synthesis.hard_stop_frames
    assert any("incentive_alignment" in r for r in blocked.reasons)
