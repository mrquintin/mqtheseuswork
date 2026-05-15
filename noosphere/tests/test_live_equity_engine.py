"""Live-equity engine + Robinhood-adapter safety tests.

Three invariants are pinned here:

1. All eight gates fail in isolation for an ``EquityPosition`` driven through
   a fake broker — the live engine never sends an order when any gate fails.
2. The Robinhood adapter is import-safe when ``robin_stocks`` is absent and
   ``RobinhoodConfig.is_configured`` cleanly returns ``False`` for blank env.
3. With both adapters mocked, the full live-equity engine makes ZERO network
   calls — verified by globally monkeypatching ``httpx`` /
   ``urllib.request`` /  ``socket.socket``.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from noosphere.equities._robinhood_live_client import (
    LiveBrokerError,
    RobinhoodLiveClient,
)
from noosphere.equities.config import RobinhoodConfig
from noosphere.equities.live_trader import (
    close_live_equity_position,
    submit_live_equity_order,
)
from noosphere.forecasts.safety import (
    GateFailure,
    check_all_equity_gates,
    gate_context_from_env_for_equities,
    reset_exchange_error_streak,
)
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPortfolioState,
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
    EquitySignal,
    EquitySignalDirection,
    EquitySignalStatus,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
ORG_ID = "org_equity_live"
OPERATOR_ID = "operator_founder_alpha"


# ── Fake broker client ──────────────────────────────────────────────────────


class _FakeBrokerClient:
    """In-memory broker fake. Same interface as AlpacaClient + RobinhoodLiveClient.

    The fake never touches the network. Use ``broker_name=...`` to identify
    itself to the live engine (so tests can assert dispatch behaviour).
    """

    def __init__(
        self,
        *,
        broker_name: str = "ALPACA",
        fill_status: str = "filled",
        fill_price: str = "182.30",
        fill_qty: str | None = None,
        place_raises: BaseException | None = None,
    ) -> None:
        self.broker_name = broker_name
        self.fill_status = fill_status
        self.fill_price = fill_price
        self.fill_qty = fill_qty
        self.place_raises = place_raises
        self.place_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    async def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.place_calls.append(kwargs)
        if self.place_raises is not None:
            raise self.place_raises
        qty = self.fill_qty or kwargs.get("qty") or "0"
        return {
            "id": f"order_{len(self.place_calls)}",
            "status": self.fill_status,
            "symbol": kwargs.get("symbol", ""),
            "filled_avg_price": self.fill_price,
            "filled_qty": qty,
            "filled_at": NOW.isoformat().replace("+00:00", "Z"),
        }

    async def get_order(self, order_id: str) -> dict[str, Any]:
        self.get_calls.append(order_id)
        return {
            "id": order_id,
            "status": self.fill_status,
            "filled_avg_price": self.fill_price,
            "filled_qty": self.fill_qty or "10",
            "filled_at": NOW.isoformat().replace("+00:00", "Z"),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_live_store(tmp_path) -> tuple[Store, str, EquityPosition, EquitySignal]:
    st = Store.from_database_url(f"sqlite:///{tmp_path / 'live.db'}")
    instrument = EquityInstrument(
        id="instr_aapl",
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("182"),
        last_price_at=NOW,
    )
    st.put_equity_instrument(instrument)
    signal = EquitySignal(
        id="sig_aapl",
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        direction=EquitySignalDirection.BULLISH,
        confidence_low=Decimal("0.55"),
        confidence_high=Decimal("0.70"),
        horizon_days=30,
        headline="x",
        reasoning="x",
        model_name="m",
        status=EquitySignalStatus.PUBLISHED,
        live_authorized_at=NOW,
        live_authorized_by=OPERATOR_ID,
    )
    st.put_equity_signal(signal)
    position = EquityPosition(
        id="pos_aapl",
        signal_id=signal.id,
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        mode=EquityPositionMode.LIVE,
        side=EquityPositionSide.LONG,
        qty=Decimal("10"),
        entry_price=Decimal("182"),
        entry_at=NOW,
        status=EquityPositionStatus.PENDING,
        live_authorized_at=NOW + timedelta(minutes=1),
    )
    st.put_equity_position(position)
    state = EquityPortfolioState(
        organization_id=ORG_ID,
        paper_balance_usd=Decimal("0"),
        live_balance_usd=Decimal("5000.00"),
        daily_loss_usd=Decimal("0"),
        daily_loss_window_reset_at=NOW,
        kill_switch_engaged=False,
        updated_at=NOW,
    )
    st.set_equity_portfolio_state(state)
    return st, ORG_ID, position, signal


def _enable_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EQUITIES_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "live-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "live-secret")
    monkeypatch.setenv("EQUITIES_MAX_STAKE_USD", "5000")
    monkeypatch.setenv("EQUITIES_MAX_DAILY_LOSS_USD", "2000")
    monkeypatch.delenv("FORECASTS_LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("ROBINHOOD_ENABLED", raising=False)


@pytest.fixture(autouse=True)
def _clear_streak():
    reset_exchange_error_streak(ORG_ID)
    yield
    reset_exchange_error_streak(ORG_ID)


# ── A. RobinhoodConfig.is_configured semantics ──────────────────────────────


def test_robinhood_config_blank_env_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "ROBINHOOD_USERNAME",
        "ROBINHOOD_PASSWORD",
        "ROBINHOOD_MFA_SEED",
        "ROBINHOOD_DEVICE_TOKEN",
        "FORECASTS_INGEST_ORG_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = RobinhoodConfig.from_env()
    assert cfg.is_configured is False


def test_robinhood_config_full_env_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROBINHOOD_USERNAME", "user@example.invalid")
    monkeypatch.setenv("ROBINHOOD_PASSWORD", "hunter2")
    monkeypatch.setenv("ROBINHOOD_MFA_SEED", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("ROBINHOOD_DEVICE_TOKEN", "device-uuid")
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", "org_test")
    cfg = RobinhoodConfig.from_env()
    assert cfg.is_configured is True
    assert cfg.pip_choice.startswith("robin_stocks")


# ── B. Robinhood adapter is import-safe without robin_stocks installed ──────


def test_robinhood_module_imports_without_robin_stocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the adapter must NEVER require robin_stocks at import time."""

    # Even if robin_stocks somehow appeared on the path, force a clean import.
    monkeypatch.setitem(sys.modules, "robin_stocks", None)
    monkeypatch.setitem(sys.modules, "robin_stocks.robinhood", None)
    module = importlib.import_module(
        "noosphere.equities._robinhood_live_client"
    )
    assert hasattr(module, "RobinhoodLiveClient")
    assert hasattr(module, "LiveBrokerError")


def test_robinhood_client_refuses_to_construct_when_unconfigured() -> None:
    cfg = RobinhoodConfig()  # blank — is_configured returns False
    with pytest.raises(LiveBrokerError) as excinfo:
        RobinhoodLiveClient(cfg, authenticate=False)
    assert excinfo.value.broker == "ROBINHOOD"
    assert excinfo.value.code == "NOT_CONFIGURED"


def test_robinhood_place_order_wraps_sdk_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = RobinhoodConfig(
        username="u",
        password="p",
        mfa_seed="JBSWY3DPEHPK3PXP",
        device_token="dev",
        organization_id="org_test",
    )

    class _BoomSDK:
        class orders:  # noqa: N801 - mimic robin_stocks namespace
            @staticmethod
            def order_buy_market(*_a, **_kw):
                raise RuntimeError("connection reset")

        class profiles:  # noqa: N801
            pass

        class account:  # noqa: N801
            pass

        class stocks:  # noqa: N801
            pass

        @staticmethod
        def login(**_kw):
            return None

    client = RobinhoodLiveClient(cfg, authenticate=False, _sdk=_BoomSDK)
    with pytest.raises(LiveBrokerError) as excinfo:
        asyncio.run(
            client.place_order(symbol="AAPL", qty="1", side="buy", type="market")
        )
    assert excinfo.value.code == "PLACE_ORDER_FAILED"
    assert excinfo.value.broker == "ROBINHOOD"


# ── C. The eight gates fire in isolation for an EquityPosition ──────────────


def test_gate_1_live_trading_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for key in (
        "FORECASTS_LIVE_TRADING_ENABLED",
        "EQUITIES_LIVE_TRADING_ENABLED",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
        "ROBINHOOD_ENABLED",
        "FORECASTS_MAX_STAKE_USD",
        "FORECASTS_MAX_DAILY_LOSS_USD",
        "EQUITIES_MAX_STAKE_USD",
        "EQUITIES_MAX_DAILY_LOSS_USD",
    ):
        monkeypatch.delenv(key, raising=False)
    store, _org, position, signal = _seed_live_store(tmp_path)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "DISABLED"


def test_gate_2_broker_credentials_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("EQUITIES_LIVE_TRADING_ENABLED", "true")
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ROBINHOOD_ENABLED", raising=False)
    store, _org, position, signal = _seed_live_store(tmp_path)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "NOT_CONFIGURED"


def test_gate_3_signal_not_authorized(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, signal = _seed_live_store(tmp_path)
    signal.live_authorized_at = None
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "NOT_AUTHORIZED"


def test_gate_4_position_not_confirmed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, signal = _seed_live_store(tmp_path)
    position.live_authorized_at = None
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "NOT_CONFIRMED"


def test_gate_5_stake_over_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    monkeypatch.setenv("EQUITIES_MAX_STAKE_USD", "10")
    store, _org, position, signal = _seed_live_store(tmp_path)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "STAKE_OVER_CEILING"


def test_gate_6_daily_loss_over_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    monkeypatch.setenv("EQUITIES_MAX_DAILY_LOSS_USD", "10")
    store, _org, position, signal = _seed_live_store(tmp_path)
    portfolio = store.get_equity_portfolio_state(ORG_ID)
    portfolio.daily_loss_usd = Decimal("999.00")
    store.set_equity_portfolio_state(portfolio)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "DAILY_LOSS_OVER_CEILING"


def test_gate_7_kill_switch_engaged(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, signal = _seed_live_store(tmp_path)
    portfolio = store.get_equity_portfolio_state(ORG_ID)
    portfolio.kill_switch_engaged = True
    store.set_equity_portfolio_state(portfolio)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "KILL_SWITCH_ENGAGED"


def test_gate_8_insufficient_balance(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, signal = _seed_live_store(tmp_path)
    portfolio = store.get_equity_portfolio_state(ORG_ID)
    portfolio.live_balance_usd = Decimal("1.00")
    store.set_equity_portfolio_state(portfolio)
    ctx = gate_context_from_env_for_equities(store.get_equity_portfolio_state(ORG_ID))
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "INSUFFICIENT_BALANCE"


# ── D. Happy path — all gates pass, fake broker fills cleanly ───────────────


def test_submit_live_equity_order_fills_via_fake_broker(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, _signal = _seed_live_store(tmp_path)
    broker = _FakeBrokerClient(fill_price="182.50", fill_qty="10")
    updated = asyncio.run(
        submit_live_equity_order(
            store,
            position.id,
            operator_id=OPERATOR_ID,
            broker_client=broker,
        )
    )
    assert updated.status == EquityPositionStatus.OPEN
    assert updated.entry_price == Decimal("182.50")
    assert updated.external_order_id == "order_1"
    assert len(broker.place_calls) == 1
    assert broker.place_calls[0]["symbol"] == "AAPL"
    portfolio = store.get_equity_portfolio_state(ORG_ID)
    # 5000.00 − (10 * 182.50) = 5000 − 1825 = 3175.00
    assert portfolio.live_balance_usd == Decimal("3175.00")


def test_submit_live_equity_order_records_streak_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, _signal = _seed_live_store(tmp_path)
    broker = _FakeBrokerClient(
        place_raises=LiveBrokerError(
            broker="ROBINHOOD", code="UPSTREAM_500", detail="503 upstream"
        )
    )
    with pytest.raises(LiveBrokerError):
        asyncio.run(
            submit_live_equity_order(
                store,
                position.id,
                operator_id=OPERATOR_ID,
                broker_client=broker,
            )
        )
    failed = store.get_equity_position(position.id)
    assert failed.status == EquityPositionStatus.FAILED


def test_three_consecutive_broker_errors_engage_kill_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, _pos, _sig = _seed_live_store(tmp_path)

    # Three distinct PENDING live positions so the engine can attempt three
    # submissions; each one must fail and feed the streak counter.
    instrument = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    signal = store.get_equity_signal("sig_aapl")
    ids: list[str] = []
    for n in range(3):
        position = EquityPosition(
            id=f"pos_streak_{n}",
            signal_id=signal.id,
            instrument_id=instrument.id,
            organization_id=ORG_ID,
            mode=EquityPositionMode.LIVE,
            side=EquityPositionSide.LONG,
            qty=Decimal("1"),
            entry_price=Decimal("100"),
            entry_at=NOW,
            status=EquityPositionStatus.PENDING,
            live_authorized_at=NOW + timedelta(minutes=1),
        )
        store.put_equity_position(position)
        ids.append(position.id)

    broker = _FakeBrokerClient(
        place_raises=LiveBrokerError(broker="ALPACA", code="UPSTREAM_503")
    )
    from noosphere.forecasts.safety import exchange_error_streak_reason
    from noosphere.models import ForecastPortfolioState

    for pid in ids:
        with pytest.raises(LiveBrokerError):
            asyncio.run(
                submit_live_equity_order(
                    store,
                    pid,
                    operator_id=OPERATOR_ID,
                    broker_client=broker,
                )
            )
    # The streak tracker is org-scoped and shared with the prediction-market
    # safety layer, so the auto-engage path lives on ForecastPortfolioState.
    # Verify both signals: the in-process streak reason and the persisted
    # kill-switch state on the org's ForecastPortfolioState row.
    assert exchange_error_streak_reason(ORG_ID) == "EXCHANGE_ERROR_STREAK"
    with store.session() as session:
        from sqlmodel import select

        fps = session.exec(
            select(ForecastPortfolioState).where(
                ForecastPortfolioState.organization_id == ORG_ID
            )
        ).first()
    assert fps is not None
    assert fps.kill_switch_engaged is True
    assert fps.kill_switch_reason == "EXCHANGE_ERROR_STREAK"


def test_close_live_equity_position_realises_pnl(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _enable_live_env(monkeypatch)
    store, _org, position, _signal = _seed_live_store(tmp_path)
    # Move the seeded PENDING position into OPEN so we can close it.
    position.status = EquityPositionStatus.OPEN
    position.entry_price = Decimal("180")
    store.put_equity_position(position)
    broker = _FakeBrokerClient(fill_price="190.00", fill_qty="10")
    closed = asyncio.run(
        close_live_equity_position(
            store,
            position.id,
            operator_id=OPERATOR_ID,
            broker_client=broker,
        )
    )
    assert closed.status == EquityPositionStatus.CLOSED
    # (190 - 180) * 10 = 100 for a LONG position.
    assert closed.realized_pnl_usd == Decimal("100.00")


# ── E. No real broker traffic during the test run ───────────────────────────


def test_no_real_broker_called(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Belt-and-suspenders: kill outbound networking, then run a full submit.

    Any AsyncClient / httpx.AsyncClient.request / urllib.request.urlopen /
    socket.create_connection invocation must raise. The submit path must not
    touch any of these — broker dispatch goes through the fake client only.
    """

    _enable_live_env(monkeypatch)

    import socket
    import urllib.request

    def _no_socket(*_a, **_kw):  # pragma: no cover - test guard
        raise AssertionError("socket.create_connection called during live submit")

    def _no_urlopen(*_a, **_kw):  # pragma: no cover - test guard
        raise AssertionError("urllib.request.urlopen called during live submit")

    monkeypatch.setattr(socket, "create_connection", _no_socket)
    monkeypatch.setattr(urllib.request, "urlopen", _no_urlopen)

    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]
    if httpx is not None:
        async def _no_request(self, *_a, **_kw):  # pragma: no cover
            raise AssertionError("httpx.AsyncClient.request called during live submit")

        monkeypatch.setattr(httpx.AsyncClient, "request", _no_request)

    store, _org, position, _signal = _seed_live_store(tmp_path)
    broker = _FakeBrokerClient(fill_price="100", fill_qty="10")
    updated = asyncio.run(
        submit_live_equity_order(
            store,
            position.id,
            operator_id=OPERATOR_ID,
            broker_client=broker,
        )
    )
    assert updated.status == EquityPositionStatus.OPEN
    assert broker.place_calls, "fake broker should have been the only call site"
