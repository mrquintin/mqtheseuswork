"""P9 — kill switch blocks every live path.

With ``ForecastPortfolioState.kill_switch_engaged=True``, every
attempted live bet across every ``MARKET_BET`` subkind is refused
with ``GateFailure(code="KILL_SWITCH_ENGAGED")``. With the kill
switch clear, the kill-switch gate passes (other gates may still
fail in isolation — that's an orthogonal concern).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from noosphere.forecasts.safety import (
    GateContext,
    GateFailure,
    check_all_equity_gates,
    check_all_gates,
    evaluate_equity_gate_results,
    evaluate_gate_results,
)


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)


def _prediction_market_ctx(*, kill_switch: bool) -> GateContext:
    return GateContext(
        live_trading_enabled=True,
        polymarket_configured=True,
        kalshi_configured=True,
        max_stake_usd=100.0,
        max_daily_loss_usd=100.0,
        kill_switch_engaged=kill_switch,
        daily_loss_usd=0.0,
        live_balance_usd=100.0,
    )


def _equity_ctx(*, kill_switch: bool) -> GateContext:
    return GateContext(
        live_trading_enabled=True,
        polymarket_configured=False,
        kalshi_configured=False,
        max_stake_usd=10_000.0,
        max_daily_loss_usd=10_000.0,
        kill_switch_engaged=kill_switch,
        daily_loss_usd=0.0,
        live_balance_usd=10_000.0,
        alpaca_configured=True,
        robinhood_configured=True,
    )


def _prediction() -> SimpleNamespace:
    return SimpleNamespace(id="prn_kill", live_authorized_at=NOW)


def _market_bet(exchange: str, *, stake: Decimal = Decimal("10.00")) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"bet_kill_{exchange.lower()}",
        organization_id="org_kill",
        exchange=exchange,
        status="CONFIRMED",
        confirmed_at=NOW,
        stake_usd=stake,
    )


def _signal() -> SimpleNamespace:
    return SimpleNamespace(id="sig_kill", live_authorized_at=NOW)


def _position(*, qty: Decimal = Decimal("1"), price: Decimal = Decimal("50.00")) -> SimpleNamespace:
    return SimpleNamespace(
        id="pos_kill",
        organization_id="org_kill",
        status="PENDING",
        live_authorized_at=NOW,
        qty=qty,
        entry_price=price,
    )


# ── Prediction-market subkinds: POLYMARKET and KALSHI ─────────────────────


@pytest.mark.parametrize("exchange", ["POLYMARKET", "KALSHI"])
def test_kill_switch_engaged_blocks_market_bet(exchange: str) -> None:
    ctx = _prediction_market_ctx(kill_switch=True)
    with pytest.raises(GateFailure) as exc:
        check_all_gates(
            prediction=_prediction(),
            bet=_market_bet(exchange),
            ctx=ctx,
        )
    assert exc.value.code == "KILL_SWITCH_ENGAGED"


@pytest.mark.parametrize("exchange", ["POLYMARKET", "KALSHI"])
def test_kill_switch_clear_does_not_raise_kill_switch_code(exchange: str) -> None:
    """With kill switch clear, no gate raises KILL_SWITCH_ENGAGED.

    Other gates may still fail under a stricter context — that is
    fine; the property under test is the kill-switch gate specifically.
    """

    ctx = _prediction_market_ctx(kill_switch=False)
    results = evaluate_gate_results(
        prediction=_prediction(),
        bet=_market_bet(exchange),
        ctx=ctx,
    )
    failing = [r for r in results if not r.passed]
    # The kill-switch gate must not be in the failure set.
    assert not any(r.code == "KILL_SWITCH_ENGAGED" for r in failing), (
        f"with kill_switch_engaged=False, no gate should report "
        f"KILL_SWITCH_ENGAGED; got {failing}"
    )


# ── Equity subkinds: ALPACA and ROBINHOOD ─────────────────────────────────


@pytest.mark.parametrize("exchange", ["ALPACA", "ROBINHOOD"])
def test_kill_switch_engaged_blocks_equity_position(exchange: str) -> None:
    # The equity gate path is broker-agnostic at the kill-switch gate
    # itself — the broker name is recorded in gate_name="broker_credentials
    # _configured" but the kill-switch gate evaluates the same field.
    # We parameterize on the exchange label for clarity and so a future
    # broker-specific kill-switch path (if ever added) is covered.
    del exchange  # the kill-switch gate is broker-agnostic by design
    ctx = _equity_ctx(kill_switch=True)
    with pytest.raises(GateFailure) as exc:
        check_all_equity_gates(
            signal=_signal(),
            position=_position(),
            ctx=ctx,
        )
    assert exc.value.code == "KILL_SWITCH_ENGAGED"


@pytest.mark.parametrize("exchange", ["ALPACA", "ROBINHOOD"])
def test_kill_switch_clear_does_not_raise_for_equity(exchange: str) -> None:
    del exchange
    ctx = _equity_ctx(kill_switch=False)
    results = evaluate_equity_gate_results(
        signal=_signal(),
        position=_position(),
        ctx=ctx,
    )
    failing = [r for r in results if not r.passed]
    assert not any(r.code == "KILL_SWITCH_ENGAGED" for r in failing), (
        f"with kill_switch_engaged=False, equity gate set should not "
        f"report KILL_SWITCH_ENGAGED; got {failing}"
    )
