"""BetSpec lifecycle tests (Round 19 prompt 15).

Covers the operator-only guarantee for ADVISORY/STRATEGIC bets, the
MARKET_BET path's reuse of the existing ForecastBet/EquityPosition
settlement, and the STRATEGIC commitment-review reminder.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from noosphere.bets.lifecycle import (
    operator_resolve_bet,
    run_lifecycle_once,
    calibration_record_payload,
)
from noosphere.bets.spec import (
    AdvisoryAudience,
    AdvisoryBetSpec,
    BetKind,
    BetOutcome,
    BetSpec,
    BetStatus,
    MarketBetExchange,
    MarketBetSide,
    MarketBetSpec,
    StrategicBetSpec,
    StrategicResourceKind,
)
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def test_advisory_bet_is_not_resolved_unilaterally() -> None:
    store = _store()
    horizon_at = NOW - timedelta(days=2)  # past the 24h grace window
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.ADVISORY_BET,
        proposition="public thesis",
        resolution_criterion="if y observed",
        horizon_at=horizon_at,
        advisory_bet=AdvisoryBetSpec(audience=AdvisoryAudience.PUBLIC),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    report = run_lifecycle_once(store, organization_id="org_a", now=NOW)
    assert report.attempted == 1
    assert report.resolved == 0  # agent refuses to resolve advisory bets
    assert report.deferred == 1
    refetched = store.get_bet_spec(spec.id)
    assert refetched is not None
    assert refetched.status == BetStatus.OPEN.value
    assert refetched.outcome is None


def test_strategic_commitment_review_fires_reminder() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.STRATEGIC_BET,
        proposition="commit founder time",
        resolution_criterion="partnership signed",
        horizon_at=NOW + timedelta(days=120),  # not past horizon yet
        strategic_bet=StrategicBetSpec(
            resource_kind=StrategicResourceKind.FOUNDER_TIME,
            cost_estimate=100.0,
            cost_unit="hours",
            commitment_review_at=NOW - timedelta(hours=1),  # review due
        ),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    report = run_lifecycle_once(store, organization_id="org_a", now=NOW)
    assert report.review_reminders == 1
    refetched = store.get_bet_spec(spec.id)
    assert refetched is not None
    assert refetched.status == BetStatus.OPEN.value


def test_strategic_review_not_due_yet() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.STRATEGIC_BET,
        proposition="commit founder time",
        resolution_criterion="partnership signed",
        horizon_at=NOW + timedelta(days=120),
        strategic_bet=StrategicBetSpec(
            resource_kind=StrategicResourceKind.FOUNDER_TIME,
            cost_estimate=100.0,
            cost_unit="hours",
            commitment_review_at=NOW + timedelta(days=10),  # future
        ),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    report = run_lifecycle_once(store, organization_id="org_a", now=NOW)
    assert report.review_reminders == 0


def test_market_bet_resolves_when_downstream_forecastbet_settles() -> None:
    store = _store()
    # Seed a ForecastBet in the SETTLED state with a P&L.
    forecast_bet = ForecastBet(
        id="fbet_test_1",
        prediction_id="pred_x",
        organization_id="org_a",
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("10.00"),
        entry_price=Decimal("0.500000"),
        status=ForecastBetStatus.SETTLED,
        settlement_pnl_usd=Decimal("3.50"),
        settled_at=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(days=3),
    )
    with store.session() as s:
        s.add(forecast_bet)
        s.commit()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.MARKET_BET,
        proposition="binary YES",
        resolution_criterion="market settles YES",
        horizon_at=NOW - timedelta(days=2),
        created_by_memo_id="memo_market",
        originating_algorithm_id="algo_42",
        market_bet=MarketBetSpec(
            exchange=MarketBetExchange.POLYMARKET,
            side=MarketBetSide.YES,
            stake_usd=Decimal("10.00"),
            entry_price=Decimal("0.500000"),
            forecast_bet_id=forecast_bet.id,
        ),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    recorded: list[dict] = []
    report = run_lifecycle_once(
        store,
        organization_id="org_a",
        now=NOW,
        calibration_recorder=lambda s, r: recorded.append(
            calibration_record_payload(s, r)
        ),
    )
    assert report.resolved == 1
    refetched = store.get_bet_spec(spec.id)
    assert refetched is not None
    assert refetched.status == BetStatus.RESOLVED.value
    assert refetched.outcome == BetOutcome.CORRECT.value
    resolutions = store.list_bet_resolutions(bet_spec_id=spec.id)
    assert len(resolutions) == 1
    assert resolutions[0].pnl_usd == 3.5
    assert recorded == [
        {
            "bet_spec_id": spec.id,
            "organization_id": "org_a",
            "kind": BetKind.MARKET_BET.value,
            "memo_id": "memo_market",
            "originating_algorithm_id": "algo_42",
            "outcome": BetOutcome.CORRECT.value,
            "pnl_usd": 3.5,
            "accuracy_score": None,
            "resolved_at": resolutions[0].resolved_at.isoformat(),
        }
    ]


def test_market_bet_defers_when_downstream_unsettled() -> None:
    store = _store()
    forecast_bet = ForecastBet(
        id="fbet_pending",
        prediction_id="pred_x",
        organization_id="org_a",
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("10.00"),
        entry_price=Decimal("0.500000"),
        status=ForecastBetStatus.FILLED,
        created_at=NOW - timedelta(days=3),
    )
    with store.session() as s:
        s.add(forecast_bet)
        s.commit()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.MARKET_BET,
        proposition="binary YES",
        resolution_criterion="market settles YES",
        horizon_at=NOW - timedelta(days=2),
        market_bet=MarketBetSpec(
            exchange=MarketBetExchange.POLYMARKET,
            side=MarketBetSide.YES,
            forecast_bet_id=forecast_bet.id,
        ),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    report = run_lifecycle_once(store, organization_id="org_a", now=NOW)
    assert report.resolved == 0
    assert report.deferred == 1
    refetched = store.get_bet_spec(spec.id)
    assert refetched is not None
    assert refetched.status == BetStatus.OPEN.value


def test_operator_resolves_advisory_bet() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.ADVISORY_BET,
        proposition="public stance",
        resolution_criterion="we were right",
        horizon_at=NOW,
        advisory_bet=AdvisoryBetSpec(),
        status=BetStatus.OPEN,
    )
    store.put_bet_spec(spec)
    resolved = operator_resolve_bet(
        store,
        spec.id,
        outcome="CORRECT",
        evidence_note="reach metrics + follow-through",
        operator_id="operator:mike",
    )
    assert resolved is not None
    assert resolved.status == BetStatus.RESOLVED.value
    resolutions = store.list_bet_resolutions(bet_spec_id=spec.id)
    assert len(resolutions) == 1
    assert resolutions[0].resolved_by == "operator:mike"
