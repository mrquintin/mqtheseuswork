from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from noosphere.forecasts._polymarket_live_client import PolymarketLiveOrder
from noosphere.forecasts.live_bet_engine import (
    settle_live_bet_on_resolution,
    submit_live_bet,
)
from noosphere.forecasts.safety import (
    GateContext,
    GateFailure,
    check_all_gates,
    gate_context_from_env,
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
ORG_ID = "org_live_safety"


def test_disabled_gate_fails_first() -> None:
    _assert_gate_code(ctx=_ctx(live_trading_enabled=False), code="DISABLED")


def test_not_configured_gate_fails_in_isolation() -> None:
    _assert_gate_code(ctx=_ctx(polymarket_configured=False), code="NOT_CONFIGURED")


def test_not_authorized_gate_fails_in_isolation() -> None:
    prediction = _prediction(live_authorized_at=None)
    _assert_gate_code(prediction=prediction, code="NOT_AUTHORIZED")


def test_not_confirmed_gate_fails_in_isolation() -> None:
    bet = _bet(status=ForecastBetStatus.AUTHORIZED, confirmed_at=None)
    _assert_gate_code(bet=bet, code="NOT_CONFIRMED")


def test_stake_over_ceiling_gate_fails_in_isolation() -> None:
    bet = _bet(stake_usd=Decimal("101.00"))
    _assert_gate_code(bet=bet, code="STAKE_OVER_CEILING")


def test_daily_loss_over_ceiling_gate_fails_in_isolation() -> None:
    _assert_gate_code(ctx=_ctx(daily_loss_usd=101.0), code="DAILY_LOSS_OVER_CEILING")


def test_kill_switch_gate_fails_in_isolation() -> None:
    _assert_gate_code(ctx=_ctx(kill_switch_engaged=True), code="KILL_SWITCH_ENGAGED")


def test_insufficient_balance_gate_fails_in_isolation() -> None:
    _assert_gate_code(ctx=_ctx(live_balance_usd=9.0), code="INSUFFICIENT_BALANCE")


def test_kill_switch_blocks_even_if_authorized() -> None:
    prediction = _prediction(live_authorized_at=NOW)
    bet = _bet(status=ForecastBetStatus.CONFIRMED, confirmed_at=NOW)
    with pytest.raises(GateFailure) as excinfo:
        check_all_gates(
            prediction=prediction,
            bet=bet,
            ctx=_ctx(kill_switch_engaged=True),
        )
    assert excinfo.value.code == "KILL_SWITCH_ENGAGED"


def test_default_env_blocks_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "FORECASTS_LIVE_TRADING_ENABLED",
        "POLYMARKET_PRIVATE_KEY",
        "KALSHI_API_KEY_ID",
        "KALSHI_API_PRIVATE_KEY",
        "KALSHI_PRIVATE_KEY_PEM",
        "FORECASTS_MAX_STAKE_USD",
        "FORECASTS_MAX_DAILY_LOSS_USD",
    ):
        monkeypatch.delenv(key, raising=False)
    ctx = gate_context_from_env(
        ForecastPortfolioState(
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10000.00"),
            live_balance_usd=Decimal("100.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=NOW,
            updated_at=NOW,
        )
    )
    with pytest.raises(GateFailure) as excinfo:
        check_all_gates(prediction=_prediction(), bet=_bet(), ctx=ctx)
    assert excinfo.value.code == "DISABLED"


def test_all_gates_pass_submits_via_polymarket(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id = _seed_live_store()
    client = _MockPolymarketClient(
        [
            PolymarketLiveOrder(
                external_order_id="poly_order_1",
                status="FILLED",
                filled_size=Decimal("10.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    submitted = asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )
    assert submitted.status == ForecastBetStatus.FILLED
    assert submitted.external_order_id == "poly_order_1"

    settled = asyncio.run(settle_live_bet_on_resolution(store, bet_id, "YES"))
    assert settled.status == ForecastBetStatus.SETTLED
    assert settled.settlement_pnl_usd == Decimal("10.00")


def test_no_real_exchange_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live_env(monkeypatch)
    store, bet_id = _seed_live_store(org_id="org_no_real_http")
    calls = {"httpx": 0}

    async def forbidden_request(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        calls["httpx"] += 1
        raise AssertionError("test attempted a real httpx exchange call")

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_request)
    client = _MockPolymarketClient(
        [
            PolymarketLiveOrder(
                external_order_id="poly_order_mocked",
                status="FILLED",
                filled_size=Decimal("10.00"),
                average_price=Decimal("0.500000"),
            )
        ]
    )

    asyncio.run(
        submit_live_bet(
            store,
            bet_id,
            polymarket_client=client,
            operator_id="operator_1",
        )
    )

    assert calls["httpx"] == 0
    assert client.place_order_calls == 1


def _assert_gate_code(
    *,
    code: str,
    prediction: SimpleNamespace | None = None,
    bet: SimpleNamespace | None = None,
    ctx: GateContext | None = None,
) -> None:
    with pytest.raises(GateFailure) as excinfo:
        check_all_gates(
            prediction=prediction or _prediction(),
            bet=bet or _bet(),
            ctx=ctx or _ctx(),
        )
    assert excinfo.value.code == code


def _prediction(*, live_authorized_at: datetime | None = NOW) -> SimpleNamespace:
    return SimpleNamespace(id="prediction_gate", live_authorized_at=live_authorized_at)


def _bet(
    *,
    exchange: ForecastExchange = ForecastExchange.POLYMARKET,
    status: ForecastBetStatus = ForecastBetStatus.CONFIRMED,
    confirmed_at: datetime | None = NOW,
    stake_usd: Decimal = Decimal("10.00"),
) -> SimpleNamespace:
    return SimpleNamespace(
        id="bet_gate",
        organization_id=ORG_ID,
        exchange=exchange,
        status=status,
        confirmed_at=confirmed_at,
        stake_usd=stake_usd,
    )


def _ctx(**overrides) -> GateContext:  # type: ignore[no-untyped-def]
    values = {
        "live_trading_enabled": True,
        "polymarket_configured": True,
        "kalshi_configured": True,
        "max_stake_usd": 100.0,
        "max_daily_loss_usd": 100.0,
        "kill_switch_engaged": False,
        "daily_loss_usd": 0.0,
        "live_balance_usd": 100.0,
    }
    values.update(overrides)
    return GateContext(**values)


def _enable_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "1" * 64)
    monkeypatch.setenv("FORECASTS_MAX_STAKE_USD", "100")
    monkeypatch.setenv("FORECASTS_MAX_DAILY_LOSS_USD", "100")
    monkeypatch.setenv("FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S", "0")


def _seed_live_store(
    *,
    org_id: str = ORG_ID,
    exchange: ForecastExchange = ForecastExchange.POLYMARKET,
    side: ForecastBetSide = ForecastBetSide.YES,
    stake: Decimal = Decimal("10.00"),
    price: Decimal = Decimal("0.500000"),
) -> tuple[Store, str]:
    reset_exchange_error_streak(org_id)
    store = Store.from_database_url("sqlite:///:memory:")
    market = ForecastMarket(
        id=f"market_{org_id}",
        organization_id=org_id,
        source=ForecastSource(exchange.value),
        external_id=f"external_{org_id}",
        title="Live safety fixture market",
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
        id=f"prediction_{org_id}",
        market_id=market.id,
        organization_id=org_id,
        probability_yes=Decimal("0.700000"),
        headline="Live safety forecast",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        model_name="fixture-model",
        live_authorized_at=NOW,
        live_authorized_by="operator_1",
        created_at=NOW,
        updated_at=NOW,
    )
    store.put_forecast_prediction(prediction)
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
    bet = ForecastBet(
        id=f"bet_{org_id}",
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
    return store, bet.id


class _MockPolymarketClient:
    def __init__(self, orders: list[PolymarketLiveOrder]) -> None:
        self._orders = orders
        self.place_order_calls = 0

    async def place_order(self, *_args, **_kwargs) -> PolymarketLiveOrder:  # type: ignore[no-untyped-def]
        self.place_order_calls += 1
        return self._orders[0]

    async def get_order(self, _order_id: str) -> PolymarketLiveOrder:
        return self._orders[-1]
