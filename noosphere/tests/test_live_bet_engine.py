from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from noosphere.forecasts._kalshi_live_client import KalshiLiveOrder
from noosphere.forecasts._polymarket_live_client import PolymarketLiveOrder
from noosphere.forecasts.live_bet_engine import (
    settle_live_bet_on_resolution,
    submit_live_bet,
)
from noosphere.forecasts.safety import (
    disengage_kill_switch,
    engage_kill_switch,
    reset_exchange_error_streak,
)
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)
from noosphere.store import Store

NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


def test_polymarket_filled_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_poly",
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
    )
    client = _MockPolymarketClient(
        [
            PolymarketLiveOrder(
                external_order_id="poly_order_filled",
                status="FILLED",
                filled_size=Decimal("10.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    filled = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )

    assert filled.status == ForecastBetStatus.FILLED
    assert store.get_portfolio_state(org_id).live_balance_usd == Decimal("990.00")  # type: ignore[union-attr]

    settled = asyncio.run(settle_live_bet_on_resolution(store, bet_id, "YES"))
    assert settled.status == ForecastBetStatus.SETTLED
    assert settled.settlement_pnl_usd == Decimal("10.00")
    assert store.get_portfolio_state(org_id).live_balance_usd == Decimal("1010.00")  # type: ignore[union-attr]


def test_kalshi_filled_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live_env(monkeypatch, kalshi=True)
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_kalshi",
        exchange=ForecastExchange.KALSHI,
        side=ForecastBetSide.NO,
    )
    client = _MockKalshiClient(
        [
            KalshiLiveOrder(
                external_order_id="kalshi_order_filled",
                status="executed",
                filled_size=Decimal("10.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    filled = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            kalshi_client=client,
            operator_id="operator_1",
        )
    )

    assert filled.status == ForecastBetStatus.FILLED
    assert store.get_portfolio_state(org_id).live_balance_usd == Decimal("990.00")  # type: ignore[union-attr]

    settled = asyncio.run(settle_live_bet_on_resolution(store, bet_id, "NO"))
    assert settled.status == ForecastBetStatus.SETTLED
    assert settled.settlement_pnl_usd == Decimal("10.00")
    assert store.get_portfolio_state(org_id).live_balance_usd == Decimal("1010.00")  # type: ignore[union-attr]


def test_partial_fill_remains_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_partial",
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake=Decimal("100.00"),
    )
    client = _MockPolymarketClient(
        [
            PolymarketLiveOrder(
                external_order_id="poly_order_partial",
                status="live",
                filled_size=Decimal("50.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    partial = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )

    assert partial.status == ForecastBetStatus.SUBMITTED
    assert store.get_portfolio_state(org_id).live_balance_usd == Decimal("1000.00")  # type: ignore[union-attr]


def test_exchange_error_streak_engages_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_live_env(monkeypatch)
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_engine_error_streak"
    reset_exchange_error_streak(org_id)
    bet_ids = [
        _seed_live_bet(store, org_id=org_id, bet_suffix=str(index))
        for index in range(3)
    ]
    client = _FailingPolymarketClient()

    for bet_id in bet_ids:
        failed = asyncio.run(
            submit_live_bet(
                store,
                bet_id,
                polymarket_client=client,
                operator_id="operator_1",
            )
        )
        assert failed.status == ForecastBetStatus.FAILED

    state = store.get_portfolio_state(org_id)
    assert state is not None
    assert state.kill_switch_engaged is True
    assert state.kill_switch_reason == "EXCHANGE_ERROR_STREAK"


def test_submit_is_idempotent_when_already_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_idempotent",
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
    )
    first_order = PolymarketLiveOrder(
        external_order_id="poly_order_first",
        status="FILLED",
        filled_size=Decimal("10.00"),
        average_price=Decimal("0.500000"),
    )
    client = _CountingPolymarketClient([first_order])

    first = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )
    assert first.status == ForecastBetStatus.FILLED
    assert client.place_order_calls == 1

    second = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )
    assert second.status == ForecastBetStatus.FILLED
    assert second.external_order_id == "poly_order_first"
    assert client.place_order_calls == 1


def test_polling_error_after_submit_leaves_bet_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_live_env(monkeypatch)
    # Give the poll loop a non-zero budget so get_order actually fires.
    monkeypatch.setenv("FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S", "0.05")
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_polling_err",
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
    )
    placed_order = PolymarketLiveOrder(
        external_order_id="poly_order_pending",
        status="live",
        filled_size=Decimal("0"),
        average_price=None,
    )
    client = _PollingErrorPolymarketClient(placed_order)

    result = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )

    assert result.status == ForecastBetStatus.SUBMITTED
    assert result.external_order_id == "poly_order_pending"
    state = store.get_portfolio_state(org_id)
    assert state is not None
    assert state.kill_switch_engaged is False, (
        "polling errors must not auto-engage the kill switch via the exchange-error "
        "streak path once the order is already at the exchange"
    )


def test_gate_failure_does_not_record_exchange_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id, org_id = _seed_live_store(
        org_id="org_engine_gate_block",
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
    )
    # Engage the kill switch so the kill_switch_clear gate fails.
    engage_kill_switch(store, org_id, reason="OPERATOR", engaged_at=NOW)
    client = _MockPolymarketClient(
        [
            PolymarketLiveOrder(
                external_order_id="poly_order_unused",
                status="FILLED",
                filled_size=Decimal("10.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    from noosphere.forecasts.safety import GateFailure

    with pytest.raises(GateFailure) as excinfo:
        asyncio.run(
            submit_live_bet(
                store,
                bet_id,
                polymarket_client=client,
                operator_id="operator_1",
            )
        )
    assert excinfo.value.code == "KILL_SWITCH_ENGAGED"

    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        assert bet is not None
        assert bet.status == ForecastBetStatus.CONFIRMED
        assert bet.external_order_id is None


def test_disengage_requires_long_note() -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_engine_disengage"
    _seed_portfolio(store, org_id)
    engage_kill_switch(store, org_id, reason="OPERATOR", engaged_at=NOW)

    with pytest.raises(ValueError, match="at least 20 chars"):
        disengage_kill_switch(
            store,
            org_id,
            operator_id="operator_1",
            note="too short",
        )

    disengage_kill_switch(
        store,
        org_id,
        operator_id="operator_1",
        note="Reviewed the incident and cleared live risk.",
    )
    state = store.get_portfolio_state(org_id)
    assert state is not None
    assert state.kill_switch_engaged is False
    assert state.kill_switch_reason is None


def _enable_live_env(monkeypatch: pytest.MonkeyPatch, *, kalshi: bool = False) -> None:
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "1" * 64)
    monkeypatch.setenv("FORECASTS_MAX_STAKE_USD", "100")
    monkeypatch.setenv("FORECASTS_MAX_DAILY_LOSS_USD", "100")
    monkeypatch.setenv("FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S", "0")
    if kalshi:
        monkeypatch.setenv("KALSHI_API_KEY_ID", "kalshi_key")
        monkeypatch.setenv(
            "KALSHI_API_PRIVATE_KEY",
            "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----",
        )


def _seed_live_store(
    *,
    org_id: str,
    exchange: ForecastExchange,
    side: ForecastBetSide,
    stake: Decimal = Decimal("10.00"),
    price: Decimal = Decimal("0.500000"),
) -> tuple[Store, str, str]:
    store = Store.from_database_url("sqlite:///:memory:")
    bet_id = _seed_live_bet(
        store,
        org_id=org_id,
        exchange=exchange,
        side=side,
        stake=stake,
        price=price,
    )
    return store, bet_id, org_id


def _seed_live_bet(
    store: Store,
    *,
    org_id: str,
    bet_suffix: str = "main",
    exchange: ForecastExchange = ForecastExchange.POLYMARKET,
    side: ForecastBetSide = ForecastBetSide.YES,
    stake: Decimal = Decimal("10.00"),
    price: Decimal = Decimal("0.500000"),
) -> str:
    reset_exchange_error_streak(org_id)
    market = ForecastMarket(
        id=f"market_{org_id}_{bet_suffix}",
        organization_id=org_id,
        source=ForecastSource(exchange.value),
        external_id=f"external_{org_id}_{bet_suffix}",
        title="Live engine fixture market",
        description="Fixture market.",
        resolution_criteria="Fixture resolution.",
        current_yes_price=price,
        current_no_price=Decimal("1.000000") - price,
        raw_payload={
            "outcomes": ["Yes", "No"],
            "clobTokenIds": ["token_yes", "token_no"],
        },
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id=f"prediction_{org_id}_{bet_suffix}",
        market_id=market.id,
        organization_id=org_id,
        probability_yes=Decimal("0.700000"),
        headline="Live engine forecast",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        model_name="fixture-model",
        live_authorized_at=NOW,
        live_authorized_by="operator_1",
        created_at=NOW,
        updated_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    if store.get_portfolio_state(org_id) is None:
        _seed_portfolio(store, org_id)
    bet = ForecastBet(
        id=f"bet_{org_id}_{bet_suffix}",
        prediction_id=prediction.id,
        organization_id=org_id,
        mode=ForecastBetMode.LIVE,
        exchange=exchange,
        side=side,
        stake_usd=stake,
        entry_price=price,
        status=ForecastBetStatus.CONFIRMED,
        live_authorized_at=NOW,
        confirmed_at=NOW,
        created_at=NOW,
    )
    store.put_forecast_bet(bet)
    return bet.id


def _seed_portfolio(store: Store, org_id: str) -> None:
    store.set_portfolio_state(
        ForecastPortfolioState(
            organization_id=org_id,
            paper_balance_usd=Decimal("10000.00"),
            live_balance_usd=Decimal("1000.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=NOW,
            kill_switch_engaged=False,
            updated_at=NOW,
        )
    )


class _MockPolymarketClient:
    def __init__(self, orders: list[PolymarketLiveOrder]) -> None:
        self._orders = orders

    async def place_order(self, *_args, **_kwargs) -> PolymarketLiveOrder:  # type: ignore[no-untyped-def]
        return self._orders[0]

    async def get_order(self, _order_id: str) -> PolymarketLiveOrder:
        return self._orders[-1]


class _MockKalshiClient:
    def __init__(self, orders: list[KalshiLiveOrder]) -> None:
        self._orders = orders

    async def place_order(self, *_args, **_kwargs) -> KalshiLiveOrder:  # type: ignore[no-untyped-def]
        return self._orders[0]

    async def get_order(self, _order_id: str) -> KalshiLiveOrder:
        return self._orders[-1]


class _FailingPolymarketClient:
    async def place_order(self, *_args, **_kwargs) -> PolymarketLiveOrder:  # type: ignore[no-untyped-def]
        raise RuntimeError("mock exchange outage")


class _CountingPolymarketClient(_MockPolymarketClient):
    def __init__(self, orders: list[PolymarketLiveOrder]) -> None:
        super().__init__(orders)
        self.place_order_calls = 0

    async def place_order(self, *_args, **_kwargs) -> PolymarketLiveOrder:  # type: ignore[no-untyped-def]
        self.place_order_calls += 1
        return self._orders[0]


class _PollingErrorPolymarketClient:
    def __init__(self, placed_order: PolymarketLiveOrder) -> None:
        self._placed_order = placed_order

    async def place_order(self, *_args, **_kwargs) -> PolymarketLiveOrder:  # type: ignore[no-untyped-def]
        return self._placed_order

    async def get_order(self, _order_id: str) -> PolymarketLiveOrder:
        raise RuntimeError("mock polling error after submission")
