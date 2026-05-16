"""BetSpec round-trip + memo-derivation tests (Round 19 prompt 15)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from noosphere.bets.spec import (
    AdvisoryAudience,
    AdvisoryBetSpec,
    BetKind,
    BetOutcome,
    BetResolution,
    BetSpec,
    BetStatus,
    MarketBetExchange,
    MarketBetSide,
    MarketBetSpec,
    ScientificBetSpec,
    ScientificDataSource,
    StrategicBetSpec,
    StrategicResourceKind,
    bet_spec_from_implied_bet,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def test_market_bet_round_trips_via_store() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.MARKET_BET,
        proposition="Polymarket binary YES on election",
        resolution_criterion="market settles YES",
        horizon_at=NOW + timedelta(days=7),
        created_by_memo_id="memo_1",
        market_bet=MarketBetSpec(
            exchange=MarketBetExchange.POLYMARKET,
            side=MarketBetSide.YES,
            stake_usd=Decimal("25.00"),
            entry_price=Decimal("0.500000"),
        ),
    )
    store.put_bet_spec(spec)
    fetched = store.get_bet_spec(spec.id)
    assert fetched is not None
    assert fetched.kind == BetKind.MARKET_BET.value
    assert fetched.status == BetStatus.PROPOSED.value
    assert fetched.market_bet is not None
    assert fetched.market_bet.exchange == MarketBetExchange.POLYMARKET.value
    assert Decimal(str(fetched.market_bet.stake_usd)) == Decimal("25.00")


def test_advisory_bet_round_trips_via_store() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.ADVISORY_BET,
        proposition="We believe Z is the case",
        resolution_criterion="if Y observed by date X, we were right",
        horizon_at=NOW + timedelta(days=30),
        created_by_memo_id="memo_advisory",
        advisory_bet=AdvisoryBetSpec(
            position_pill="BULLISH",
            audience=AdvisoryAudience.PUBLIC,
            public_url="https://example.com/memo",
        ),
    )
    store.put_bet_spec(spec)
    fetched = store.get_bet_spec(spec.id)
    assert fetched is not None
    assert fetched.kind == BetKind.ADVISORY_BET.value
    # Non-financial bets open immediately — no eight-gate.
    assert fetched.status == BetStatus.PROPOSED.value
    assert fetched.advisory_bet is not None
    assert fetched.advisory_bet.audience == AdvisoryAudience.PUBLIC.value


def test_scientific_bet_round_trips_via_store() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.SCIENTIFIC_BET,
        proposition="Household debt/income > 1.4 in US by 2026-Q4",
        resolution_criterion="FRED series HDTGPDUSQ163N exceeds 1.4",
        horizon_at=NOW + timedelta(days=90),
        created_by_memo_id="memo_sci",
        scientific_bet=ScientificBetSpec(
            data_source=ScientificDataSource.FRED,
            metric_query={"series_id": "HDTGPDUSQ163N"},
            expected_value=1.4,
            tolerance=0.05,
        ),
    )
    store.put_bet_spec(spec)
    fetched = store.get_bet_spec(spec.id)
    assert fetched is not None
    assert fetched.kind == BetKind.SCIENTIFIC_BET.value
    assert fetched.scientific_bet is not None
    assert fetched.scientific_bet.data_source == ScientificDataSource.FRED.value


def test_strategic_bet_round_trips_via_store() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.STRATEGIC_BET,
        proposition="Commit 200 founder-hours to building partnership X",
        resolution_criterion="partnership signed by EOY",
        horizon_at=NOW + timedelta(days=120),
        created_by_memo_id="memo_strat",
        strategic_bet=StrategicBetSpec(
            resource_kind=StrategicResourceKind.PARTNERSHIP_PURSUIT,
            cost_estimate=200.0,
            cost_unit="hours",
            commitment_review_at=NOW + timedelta(days=60),
        ),
    )
    store.put_bet_spec(spec)
    fetched = store.get_bet_spec(spec.id)
    assert fetched is not None
    assert fetched.kind == BetKind.STRATEGIC_BET.value
    assert fetched.strategic_bet is not None
    assert fetched.strategic_bet.cost_unit == "hours"


def test_bet_spec_validator_requires_matching_subspec() -> None:
    with pytest.raises(ValueError, match="requires the 'advisory_bet' block"):
        BetSpec(
            organization_id="org_a",
            kind=BetKind.ADVISORY_BET,
            proposition="x",
            resolution_criterion="y",
            horizon_at=NOW,
        )


def test_bet_spec_validator_rejects_foreign_subspec() -> None:
    with pytest.raises(ValueError, match="must not carry a 'market_bet' block"):
        BetSpec(
            organization_id="org_a",
            kind=BetKind.ADVISORY_BET,
            proposition="x",
            resolution_criterion="y",
            horizon_at=NOW,
            advisory_bet=AdvisoryBetSpec(),
            market_bet=MarketBetSpec(
                exchange=MarketBetExchange.POLYMARKET,
                side=MarketBetSide.YES,
            ),
        )


def test_bet_spec_from_implied_bet_market_default() -> None:
    spec = bet_spec_from_implied_bet(
        {
            "exchange": "POLYMARKET",
            "side": "YES",
            "stake_usd": "5.00",
            "entry_price": "0.500000",
            "proposition": "thesis text",
            "resolution_criterion": "criterion text",
            "horizon_at": "2026-06-01T00:00:00Z",
        },
        organization_id="org_a",
        memo_id="memo_1",
    )
    assert spec.kind == BetKind.MARKET_BET.value
    assert spec.status == BetStatus.PROPOSED.value  # gated by authorize
    assert spec.market_bet is not None
    assert spec.market_bet.exchange == MarketBetExchange.POLYMARKET.value


def test_bet_spec_from_implied_bet_advisory_opens_immediately() -> None:
    spec = bet_spec_from_implied_bet(
        {
            "kind": "ADVISORY_BET",
            "position_pill": "BEARISH",
            "audience": "FOUNDER_NETWORK",
            "proposition": "we believe X",
            "resolution_criterion": "y by date z",
        },
        organization_id="org_a",
        memo_id="memo_advisory",
    )
    assert spec.kind == BetKind.ADVISORY_BET.value
    assert spec.status == BetStatus.OPEN.value
    assert spec.advisory_bet is not None
    assert spec.advisory_bet.position_pill == "BEARISH"


def test_bet_spec_from_implied_bet_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        bet_spec_from_implied_bet(
            {"proposition": "no kind, no exchange"},
            organization_id="org_a",
            memo_id="memo_x",
        )


def test_bet_resolution_round_trip() -> None:
    store = _store()
    spec = BetSpec(
        organization_id="org_a",
        kind=BetKind.ADVISORY_BET,
        proposition="z",
        resolution_criterion="y",
        horizon_at=NOW,
        advisory_bet=AdvisoryBetSpec(),
    )
    store.put_bet_spec(spec)
    resolution = BetResolution(
        bet_spec_id=spec.id,
        outcome=BetOutcome.CORRECT,
        evidence_note="operator confirmed",
        audience_response="founder Slack reaction",
        resolved_by="operator:mike",
    )
    store.put_bet_resolution(resolution)
    fetched = store.list_bet_resolutions(bet_spec_id=spec.id)
    assert len(fetched) == 1
    assert fetched[0].outcome == BetOutcome.CORRECT.value
    assert fetched[0].audience_response == "founder Slack reaction"
