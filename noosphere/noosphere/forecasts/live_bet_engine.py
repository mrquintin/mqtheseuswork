"""Gated live-bet submission and settlement for Forecasts."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from noosphere.forecasts._kalshi_live_client import KalshiLiveClient, KalshiLiveOrder
from noosphere.forecasts._polymarket_live_client import (
    PolymarketLiveClient,
    PolymarketLiveOrder,
)
from noosphere.forecasts.safety import (
    check_all_gates,
    gate_context_from_env,
    maybe_engage_daily_loss_kill_switch,
    record_exchange_error,
    reset_exchange_error_streak,
)
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
)
from noosphere.observability import get_logger

log = get_logger(__name__)
MONEY = Decimal("0.01")
PRICE = Decimal("0.000001")


async def submit_live_bet(
    store: Any,
    bet_id: str,
    *,
    polymarket_client: Any = None,
    kalshi_client: Any = None,
    operator_id: str,
) -> ForecastBet:
    """
    Gate and submit one live bet. This function never submits unless
    check_all_gates has passed and operator_id is non-empty.
    """

    if not operator_id or not operator_id.strip():
        raise ValueError("operator_id is required for live bet submission")

    bet, prediction, market, portfolio = _load_submission_context(store, bet_id)
    ctx = gate_context_from_env(portfolio)
    check_all_gates(prediction=prediction, bet=bet, ctx=ctx)

    try:
        if _enum_value(bet.exchange) == ForecastExchange.POLYMARKET.value:
            client = polymarket_client or PolymarketLiveClient.from_env()
            order = await _submit_polymarket_order(client, bet, market)
        elif _enum_value(bet.exchange) == ForecastExchange.KALSHI.value:
            client = kalshi_client or KalshiLiveClient.from_env()
            order = await _submit_kalshi_order(client, bet, market)
        else:
            raise ValueError(f"unsupported live exchange: {bet.exchange!r}")

        submitted = _mark_submitted(
            store,
            bet.id,
            order,
            submitted_at=datetime.now(UTC),
        )
        terminal_order, terminal_status = await _poll_order_status(
            client,
            order,
            expected_fill=Decimal(submitted.stake_usd),
        )
        updated = _apply_order_status(
            store,
            submitted.id,
            terminal_order,
            terminal_status,
        )
        if updated.status == ForecastBetStatus.FILLED:
            reset_exchange_error_streak(updated.organization_id)
        return updated
    except Exception as exc:
        updated = _mark_failed(store, bet.id, exc)
        record_exchange_error(store, updated.organization_id)
        return updated


async def settle_live_bet_on_resolution(
    store: Any,
    bet_id: str,
    market_outcome: Literal["YES", "NO", "CANCELLED"],
) -> ForecastBet:
    """Mirror paper settlement and credit live balance with realized payoff."""

    outcome = ForecastOutcome(market_outcome)
    timestamp = datetime.now(UTC)
    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        if bet is None:
            raise KeyError(f"unknown forecast bet: {bet_id}")
        if _enum_value(bet.mode) != ForecastBetMode.LIVE.value:
            raise ValueError("settle_live_bet_on_resolution only accepts LIVE bets")
        if _enum_value(bet.status) == ForecastBetStatus.SETTLED.value:
            return bet.model_copy()
        if _enum_value(bet.status) != ForecastBetStatus.FILLED.value:
            raise ValueError("only FILLED live bets can be settled")

        payoff, exit_price = _settlement_payoff(bet, outcome)
        pnl = _money(payoff - Decimal(bet.stake_usd))
        bet.status = ForecastBetStatus.SETTLED
        bet.exit_price = exit_price
        bet.settlement_pnl_usd = pnl
        bet.settled_at = timestamp

        state = _portfolio_state(session, bet.organization_id, now=timestamp)
        state.live_balance_usd = _money(Decimal(state.live_balance_usd or 0) + payoff)
        if pnl < Decimal("0"):
            state.daily_loss_usd = _money(Decimal(state.daily_loss_usd) + abs(pnl))
        state.updated_at = timestamp

        session.add(state)
        session.add(bet)
        session.commit()
        session.refresh(bet)
        result = bet.model_copy()

    maybe_engage_daily_loss_kill_switch(store, result.organization_id)
    return result


def _load_submission_context(
    store: Any,
    bet_id: str,
) -> tuple[
    ForecastBet,
    ForecastPrediction,
    ForecastMarket,
    ForecastPortfolioState | None,
]:
    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        if bet is None:
            raise KeyError(f"unknown forecast bet: {bet_id}")
        if _enum_value(bet.mode) != ForecastBetMode.LIVE.value:
            raise ValueError("submit_live_bet only accepts LIVE bets")
        prediction = session.get(ForecastPrediction, bet.prediction_id)
        if prediction is None:
            raise KeyError(f"unknown forecast prediction: {bet.prediction_id}")
        market = session.get(ForecastMarket, prediction.market_id)
        if market is None:
            raise KeyError(f"unknown forecast market: {prediction.market_id}")
        state = _portfolio_state_or_none(session, bet.organization_id)
        return (
            bet.model_copy(),
            prediction.model_copy(),
            market.model_copy(),
            state.model_copy() if state is not None else None,
        )


async def _submit_polymarket_order(
    client: Any,
    bet: ForecastBet,
    market: ForecastMarket,
) -> PolymarketLiveOrder:
    side = ForecastBetSide(_enum_value(bet.side))
    token_id, outcome_index = _polymarket_token_id(market, side)
    price = _decimal(bet.entry_price)
    size = _money(_decimal(bet.stake_usd) / price)
    return await client.place_order(
        token_id,
        outcome_index,
        "BUY",
        size,
        price,
        os.getenv("FORECASTS_LIVE_ORDER_TYPE", "GTC"),
    )


async def _submit_kalshi_order(
    client: Any,
    bet: ForecastBet,
    market: ForecastMarket,
) -> KalshiLiveOrder:
    side = ForecastBetSide(_enum_value(bet.side))
    price = _decimal(bet.entry_price)
    count = max(
        1,
        int((_decimal(bet.stake_usd) / price).to_integral_value(rounding=ROUND_DOWN)),
    )
    return await client.place_order(
        market.external_id,
        side.value,
        count,
        price,
        os.getenv("FORECASTS_LIVE_ORDER_TYPE", "GTC"),
        bet.client_order_id or bet.id,
    )


async def _poll_order_status(
    client: Any,
    initial_order: Any,
    *,
    expected_fill: Decimal,
) -> tuple[Any, ForecastBetStatus]:
    order = initial_order
    status = _bet_status_from_order(order)
    if status in {
        ForecastBetStatus.FILLED,
        ForecastBetStatus.CANCELLED,
        ForecastBetStatus.FAILED,
    }:
        return order, status
    if _is_partial_fill(order, expected_fill):
        return order, ForecastBetStatus.SUBMITTED

    deadline = time.monotonic() + _poll_timeout_s()
    while time.monotonic() < deadline:
        order = await client.get_order(order.external_order_id)
        status = _bet_status_from_order(order)
        if status in {
            ForecastBetStatus.FILLED,
            ForecastBetStatus.CANCELLED,
            ForecastBetStatus.FAILED,
        }:
            return order, status
        if _is_partial_fill(order, expected_fill):
            return order, ForecastBetStatus.SUBMITTED
        await asyncio.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return order, ForecastBetStatus.SUBMITTED


def _mark_submitted(
    store: Any,
    bet_id: str,
    order: Any,
    *,
    submitted_at: datetime,
) -> ForecastBet:
    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        if bet is None:
            raise KeyError(f"unknown forecast bet: {bet_id}")
        bet.status = ForecastBetStatus.SUBMITTED
        bet.external_order_id = order.external_order_id
        bet.submitted_at = submitted_at
        session.add(bet)
        session.commit()
        session.refresh(bet)
        return bet.model_copy()


def _apply_order_status(
    store: Any,
    bet_id: str,
    order: Any,
    status: ForecastBetStatus,
) -> ForecastBet:
    timestamp = datetime.now(UTC)
    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        if bet is None:
            raise KeyError(f"unknown forecast bet: {bet_id}")
        bet.external_order_id = order.external_order_id
        if status != ForecastBetStatus.SUBMITTED:
            bet.status = status
        if status == ForecastBetStatus.FILLED:
            state = _portfolio_state(session, bet.organization_id, now=timestamp)
            state.live_balance_usd = _money(
                Decimal(state.live_balance_usd or 0) - Decimal(bet.stake_usd)
            )
            state.updated_at = timestamp
            session.add(state)
        session.add(bet)
        session.commit()
        session.refresh(bet)
        return bet.model_copy()


def _mark_failed(store: Any, bet_id: str, exc: Exception) -> ForecastBet:
    log.warning(
        "forecast_live_bet_exchange_error",
        bet_id=bet_id,
        error_code=type(exc).__name__,
        error_message=str(exc),
    )
    with store.session() as session:
        bet = session.get(ForecastBet, bet_id)
        if bet is None:
            raise KeyError(f"unknown forecast bet: {bet_id}") from exc
        bet.status = ForecastBetStatus.FAILED
        session.add(bet)
        session.commit()
        session.refresh(bet)
        return bet.model_copy()


def _portfolio_state_or_none(
    session: Any,
    organization_id: str,
) -> ForecastPortfolioState | None:
    from sqlmodel import select

    return session.exec(
        select(ForecastPortfolioState).where(
            ForecastPortfolioState.organization_id == organization_id
        )
    ).first()


def _portfolio_state(
    session: Any,
    organization_id: str,
    *,
    now: datetime,
) -> ForecastPortfolioState:
    state = _portfolio_state_or_none(session, organization_id)
    if state is not None:
        return state
    state = ForecastPortfolioState(
        organization_id=organization_id,
        paper_balance_usd=Decimal("0.00"),
        live_balance_usd=Decimal("0.00"),
        daily_loss_usd=Decimal("0.00"),
        daily_loss_reset_at=now,
        kill_switch_engaged=False,
        kill_switch_reason=None,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _bet_status_from_order(order: Any) -> ForecastBetStatus:
    status = str(getattr(order, "status", "")).strip().upper()
    if status in {"FILLED", "EXECUTED", "MATCHED"}:
        return ForecastBetStatus.FILLED
    if status in {"CANCELLED", "CANCELED", "CANCEL"}:
        return ForecastBetStatus.CANCELLED
    if status in {"FAILED", "FAIL", "REJECTED", "ERROR"}:
        return ForecastBetStatus.FAILED
    return ForecastBetStatus.SUBMITTED


def _is_partial_fill(order: Any, expected_fill: Decimal) -> bool:
    filled = _decimal(getattr(order, "filled_size", Decimal("0")))
    return Decimal("0") < filled < expected_fill


def _settlement_payoff(
    bet: ForecastBet,
    outcome: ForecastOutcome,
) -> tuple[Decimal, Decimal]:
    if outcome == ForecastOutcome.CANCELLED:
        return _money(Decimal(bet.stake_usd)), _price(Decimal(bet.entry_price))
    side_won = (
        (outcome == ForecastOutcome.YES and _enum_value(bet.side) == "YES")
        or (outcome == ForecastOutcome.NO and _enum_value(bet.side) == "NO")
    )
    if not side_won:
        return Decimal("0.00"), Decimal("0.000000")
    return (
        _money(Decimal(bet.stake_usd) / Decimal(bet.entry_price)),
        Decimal("1.000000"),
    )


def _polymarket_token_id(
    market: ForecastMarket,
    side: ForecastBetSide,
) -> tuple[str, int]:
    outcome_index = 0 if side == ForecastBetSide.YES else 1
    token_ids = _payload_array(
        market.raw_payload.get("clobTokenIds")
        or market.raw_payload.get("clob_token_ids")
        or market.raw_payload.get("tokenIds")
        or market.raw_payload.get("token_ids")
    )
    outcomes = [_outcome_label(item).lower() for item in _payload_array(
        market.raw_payload.get("outcomes") or market.raw_payload.get("outcome")
    )]
    if outcomes:
        try:
            outcome_index = outcomes.index(side.value.lower())
        except ValueError:
            pass
    if token_ids and outcome_index < len(token_ids):
        return str(token_ids[outcome_index]), outcome_index
    return market.external_id, outcome_index


def _payload_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            import json

            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, list) else []
        return [stripped]
    return []


def _outcome_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("label")
            or value.get("outcome")
            or ""
        )
    return str(value)


def _poll_timeout_s() -> float:
    raw = os.getenv("FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S", "30")
    return max(0.0, float(raw))


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a decimal value: {value!r}") from exc


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _price(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PRICE, rounding=ROUND_HALF_UP)


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)
