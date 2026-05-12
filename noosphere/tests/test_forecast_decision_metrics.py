"""Unit tests for the deterministic decision-trace engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.forecasts.decision_metrics import (
    DEFAULT_PAPER_STAKE_USD,
    MarketDecisionAction,
    TRACE_VERSION,
    build_decision_trace,
    compute_calibration_adjusted_confidence,
    compute_contradiction_pressure,
    compute_liquidity_cost_feasibility,
    compute_market_mispricing_edge,
    compute_source_domain_locality,
    compute_temporal_decay_pressure,
    decision_trace_to_dict,
)


NOW = datetime(2026, 5, 12, tzinfo=timezone.utc)


@dataclass
class FakeMarket:
    id: str = "mkt"
    organization_id: str = "org"
    title: str = "Will the policy bill pass before June?"
    category: str = "policy"
    current_yes_price: Decimal | None = Decimal("0.41")
    current_no_price: Decimal | None = Decimal("0.59")
    status: str = "OPEN"
    close_time: datetime | None = NOW + timedelta(days=30)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeSource:
    source_type: str
    source_id: str
    text: str = ""
    relevance: float = 0.8
    surfaceable: bool = True
    visibility: str = "PUBLIC"
    metadata: dict[str, Any] = field(default_factory=dict)


def _policy_sources() -> list[FakeSource]:
    return [
        FakeSource(
            source_type="CONCLUSION",
            source_id="c_a",
            text="Bill sponsorship has broadened.",
            metadata={
                "disciplines": ["policy"],
                "topic_hint": "policy",
                "created_at": (NOW - timedelta(days=20)).isoformat(),
            },
        ),
        FakeSource(
            source_type="CLAIM",
            source_id="c_b",
            text="Markup scheduled.",
            metadata={
                "disciplines": ["policy"],
                "created_at": (NOW - timedelta(days=10)).isoformat(),
            },
        ),
        FakeSource(
            source_type="CONCLUSION",
            source_id="c_c",
            text="Floor calendar is tight.",
            metadata={
                "disciplines": ["policy"],
                "created_at": (NOW - timedelta(days=30)).isoformat(),
            },
        ),
    ]


def _payload(probability_yes: float, *, low: float = 0.52, high: float = 0.74) -> dict[str, Any]:
    return {
        "probability_yes": probability_yes,
        "confidence_low": low,
        "confidence_high": high,
        "topic_hint": "policy",
    }


def _citations(*, contrary: int = 0, direct: int = 2) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(direct):
        out.append(
            {
                "source_type": "CONCLUSION" if i == 0 else "CLAIM",
                "source_id": "c_a" if i == 0 else "c_b",
                "quoted_span": "x",
                "support_label": "DIRECT",
            }
        )
    for i in range(contrary):
        out.append(
            {
                "source_type": "CONCLUSION",
                "source_id": "c_c",
                "quoted_span": "y",
                "support_label": "CONTRARY",
            }
        )
    return out


# ---------------------------------------------------------------------
# Metric units


def test_market_mispricing_edge_signed_value() -> None:
    metric = compute_market_mispricing_edge(0.6, 0.4)
    assert metric.value == pytest.approx(0.2)
    assert metric.range_low == -1.0 and metric.range_high == 1.0
    assert not metric.low_confidence


def test_market_mispricing_edge_missing_inputs_low_confidence() -> None:
    metric = compute_market_mispricing_edge(None, None)
    assert metric.low_confidence is True
    assert metric.value == 0.0


def test_calibration_adjusted_confidence_no_record_marks_low_confidence() -> None:
    metric = compute_calibration_adjusted_confidence(0.5, 0.7, None)
    assert metric.low_confidence is True
    assert metric.value == pytest.approx(0.8)


def test_calibration_adjusted_confidence_uses_domain_factor() -> None:
    metric = compute_calibration_adjusted_confidence(
        0.5,
        0.7,
        {
            "min_samples": 40,
            "recalibration_min_samples": 30,
            "domains": {"policy": 0.9},
        },
        topic_hint="policy",
    )
    assert metric.low_confidence is False
    assert metric.value == pytest.approx(0.72)


def test_source_domain_locality_in_bounds() -> None:
    metric = compute_source_domain_locality(_policy_sources(), _citations(direct=2), FakeMarket())
    assert metric.value == pytest.approx(1.0)


def test_source_domain_locality_missing_category() -> None:
    market = FakeMarket(category="")
    metric = compute_source_domain_locality(_policy_sources(), _citations(), market)
    assert metric.low_confidence is True


def test_contradiction_pressure_counts_contrary_labels() -> None:
    metric = compute_contradiction_pressure(_citations(direct=2, contrary=2))
    assert metric.value == pytest.approx(0.5)


def test_liquidity_cost_feasibility_low_liquidity_flag() -> None:
    market = FakeMarket(raw_payload={"low_liquidity": True})
    metric = compute_liquidity_cost_feasibility(market, suggested_stake_usd=20.0)
    assert metric.value == 0.0


def test_liquidity_cost_feasibility_from_spread() -> None:
    market = FakeMarket(raw_payload={"spread": 0.02, "depth_usd": 1000.0})
    metric = compute_liquidity_cost_feasibility(market, suggested_stake_usd=20.0)
    assert metric.value == pytest.approx(0.98)


def test_temporal_decay_pressure_normalized_against_horizon() -> None:
    sources = _policy_sources()
    metric = compute_temporal_decay_pressure(sources, FakeMarket(), now=NOW)
    # mean age 20 days vs horizon 30 days → 0.66
    assert metric.value == pytest.approx(20.0 / 30.0, abs=0.01)


# ---------------------------------------------------------------------
# End-to-end rule graph scenarios


def test_no_edge_drives_watch() -> None:
    market = FakeMarket(current_yes_price=Decimal("0.60"))
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=2),
        payload=_payload(0.60, low=0.55, high=0.65),
        now=NOW,
        min_distinct_sources=3,
    )
    assert trace.action == MarketDecisionAction.WATCH
    edge = trace.metric("market_mispricing_edge")
    assert edge is not None and abs(edge.value) < 0.05
    assert trace.stake_recommendation_usd is None
    assert trace.trace_version == TRACE_VERSION


def test_strong_edge_low_liquidity_downgrades_to_watch() -> None:
    market = FakeMarket(
        current_yes_price=Decimal("0.30"),
        raw_payload={"low_liquidity": True},
    )
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=2),
        payload=_payload(0.70, low=0.60, high=0.78),
        now=NOW,
        min_distinct_sources=3,
    )
    edge = trace.metric("market_mispricing_edge")
    liquidity = trace.metric("liquidity_cost_feasibility")
    assert edge is not None and edge.value > 0.3
    assert liquidity is not None and liquidity.value == 0.0
    assert trace.action == MarketDecisionAction.WATCH
    assert trace.stake_recommendation_usd is None
    assert any("liquidity" in r for r in trace.reasons)


def test_strong_edge_good_calibration_reaches_live_candidate() -> None:
    market = FakeMarket(
        current_yes_price=Decimal("0.45"),
        current_no_price=Decimal("0.55"),
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=3),
        payload=_payload(0.75, low=0.70, high=0.80),
        now=NOW,
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
        min_distinct_sources=3,
    )
    assert trace.action == MarketDecisionAction.LIVE_CANDIDATE
    assert trace.side == "YES"
    assert trace.stake_recommendation_usd == pytest.approx(DEFAULT_PAPER_STAKE_USD)
    body = decision_trace_to_dict(trace)
    assert body["action"] == "LIVE_CANDIDATE"
    assert {m["name"] for m in body["metrics"]} >= {
        "market_mispricing_edge",
        "calibration_adjusted_confidence",
        "source_domain_locality",
        "contradiction_pressure",
        "liquidity_cost_feasibility",
        "temporal_decay_pressure",
    }


def test_out_of_domain_market_downgrades_to_paper() -> None:
    market = FakeMarket(
        category="crypto",
        current_yes_price=Decimal("0.40"),
        current_no_price=Decimal("0.60"),
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=3),
        payload=_payload(0.75, low=0.70, high=0.80),
        now=NOW,
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"crypto": 1.0},
        },
        min_distinct_sources=3,
    )
    locality = trace.metric("source_domain_locality")
    assert locality is not None and locality.value < 0.6
    # Out-of-domain prevents LIVE_CANDIDATE; edge is wide enough for paper.
    assert trace.action == MarketDecisionAction.PAPER_TRADE
    assert any("locality" in r or "confidence" in r for r in trace.reasons)


def test_contradiction_veto_forces_abstain() -> None:
    market = FakeMarket(current_yes_price=Decimal("0.45"))
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=1, contrary=2),
        payload=_payload(0.70, low=0.62, high=0.78),
        now=NOW,
        min_distinct_sources=3,
    )
    contradiction = trace.metric("contradiction_pressure")
    assert contradiction is not None and contradiction.value >= 0.5
    assert trace.action == MarketDecisionAction.ABSTAIN
    assert trace.side is None
    assert trace.stake_recommendation_usd is None
    assert any("contradiction" in r for r in trace.reasons)


def test_market_closed_short_circuits_to_abstain() -> None:
    market = FakeMarket(status="CLOSED")
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=2),
        payload=_payload(0.75),
        now=NOW,
        min_distinct_sources=3,
    )
    assert trace.action == MarketDecisionAction.ABSTAIN
    closed_rule = next(r for r in trace.rules if r.name == "market_open")
    assert closed_rule.passed is False
    # All later rules short-circuited.
    later = [r for r in trace.rules if r.name != "market_open"]
    assert all(r.fired is False for r in later if r.kind == "veto")


def test_missing_data_yields_low_confidence_metrics_without_crash() -> None:
    market = FakeMarket(current_yes_price=None, raw_payload={})
    trace = build_decision_trace(
        market=market,
        sources=[],
        citations=[],
        payload={"probability_yes": None, "confidence_low": None, "confidence_high": None},
        now=NOW,
        min_distinct_sources=3,
    )
    # No sources → distinct_source_floor veto triggers → ABSTAIN.
    assert trace.action == MarketDecisionAction.ABSTAIN
    for metric in trace.metrics:
        if metric.name in {"market_mispricing_edge", "calibration_adjusted_confidence", "temporal_decay_pressure"}:
            assert metric.low_confidence


def test_decision_trace_to_dict_is_json_stable() -> None:
    market = FakeMarket(
        current_yes_price=Decimal("0.45"),
        current_no_price=Decimal("0.55"),
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    payload = _payload(0.75, low=0.70, high=0.80)
    citations = _citations(direct=3)
    sources = _policy_sources()
    a = build_decision_trace(
        market=market, sources=sources, citations=citations, payload=payload, now=NOW
    )
    b = build_decision_trace(
        market=market, sources=sources, citations=citations, payload=payload, now=NOW
    )
    assert decision_trace_to_dict(a) == decision_trace_to_dict(b)


def test_position_overlay_reduce_on_disagreement() -> None:
    market = FakeMarket(
        current_yes_price=Decimal("0.45"),
        current_no_price=Decimal("0.55"),
        raw_payload={"spread": 0.0, "depth_usd": 5000.0},
    )
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=3),
        payload=_payload(0.70, low=0.62, high=0.78),
        now=NOW,
        position_state={"open_side": "NO"},
        min_distinct_sources=3,
    )
    assert trace.action == MarketDecisionAction.REDUCE


def test_position_overlay_exit_on_revocation() -> None:
    market = FakeMarket(current_yes_price=Decimal("0.45"))
    trace = build_decision_trace(
        market=market,
        sources=_policy_sources(),
        citations=_citations(direct=2),
        payload=_payload(0.55),
        now=NOW,
        position_state={"principles_revoked": True, "open_side": "YES"},
        min_distinct_sources=3,
    )
    assert trace.action == MarketDecisionAction.EXIT
