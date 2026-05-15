"""Gated live-equity submission and close.

The single live entry point — :func:`submit_live_equity_order` — refuses to
talk to any broker until the eight-gate safety contract in
:mod:`noosphere.forecasts.safety` has passed. The broker_client argument is
expected to be either an :class:`AlpacaClient` (paper or live host) or a
:class:`RobinhoodLiveClient`; both expose the same dict-shaped order surface
so this module stays broker-agnostic.

Three consecutive broker errors auto-engage the portfolio kill switch via
the same streak tracker used by the prediction-market live engine.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from noosphere.equities._alpaca_client import AlpacaAPIError
from noosphere.equities._robinhood_live_client import LiveBrokerError
from noosphere.forecasts.safety import (
    check_all_equity_gates,
    gate_context_from_env_for_equities,
    record_exchange_error,
    reset_exchange_error_streak,
)
from noosphere.models import (
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
)
from noosphere.observability import get_logger

log = get_logger(__name__)

_FILL_POLL_INTERVAL_S = 0.5
_FILL_TIMEOUT_S = 30.0
_MONEY = Decimal("0.01")


async def submit_live_equity_order(
    store: Any,
    position_id: str,
    *,
    operator_id: str,
    broker_client: Any,
    poll_interval_s: float = _FILL_POLL_INTERVAL_S,
    fill_timeout_s: float = _FILL_TIMEOUT_S,
) -> EquityPosition:
    """Submit a PENDING live ``EquityPosition`` to ``broker_client``.

    On a clean fill the row is moved to OPEN with broker-supplied price/qty,
    and the portfolio's ``liveBalanceUsd`` is decremented by ``qty * fill``.
    Any broker exception flips the row to FAILED and increments the error
    streak — three consecutive errors auto-engage the kill switch.
    """

    if not operator_id or not operator_id.strip():
        raise ValueError("operator_id is required for live equity submission")

    position, signal, instrument, portfolio = _load_open_context(store, position_id)
    if _enum(position.mode) != EquityPositionMode.LIVE.value:
        raise ValueError(
            "submit_live_equity_order only accepts LIVE EquityPositions"
        )
    if _enum(position.status) != EquityPositionStatus.PENDING.value:
        log.info(
            "equity_live_order_already_submitted",
            position_id=position.id,
            status=_enum(position.status),
            external_order_id=position.external_order_id,
        )
        return position

    ctx = gate_context_from_env_for_equities(portfolio)
    check_all_equity_gates(signal=signal, position=position, ctx=ctx)

    broker_name = _broker_name(broker_client)
    side = _broker_side(position.side, opening=True)
    try:
        order = await broker_client.place_order(
            symbol=instrument.symbol,
            qty=str(position.qty),
            side=side,
            type="market",
            time_in_force="day",
            client_order_id=f"live-open-{position.id}",
        )
    except (AlpacaAPIError, LiveBrokerError) as exc:
        _on_broker_error(store, position, broker_name, exc)
        raise

    order_id = str(order.get("id") or "").strip()
    fill = await _poll_until_terminal(
        broker_client,
        order=order,
        poll_interval_s=poll_interval_s,
        timeout_s=fill_timeout_s,
    )
    status = _normalised_status(fill)
    fill_price = _decimal_or_none(
        fill.get("filled_avg_price") or fill.get("limit_price")
    )
    fill_qty = _decimal_or_none(fill.get("filled_qty")) or position.qty
    filled_at = _parse_dt(fill.get("filled_at")) or _now()

    if status == "filled" and fill_price is not None:
        updated = _mark_filled(
            store,
            position_id,
            fill_price=fill_price,
            fill_qty=fill_qty,
            filled_at=filled_at,
            order_id=order_id,
            organization_id=position.organization_id,
        )
        reset_exchange_error_streak(updated.organization_id)
        log.info(
            "equity_live_order_filled",
            position_id=updated.id,
            broker=broker_name,
            symbol=instrument.symbol,
            entry_price=str(fill_price),
            qty=str(fill_qty),
        )
        return updated

    error = LiveBrokerError(
        broker=broker_name,
        code="ORDER_NOT_FILLED",
        detail=f"terminal status={status!r}",
    )
    _on_broker_error(store, position, broker_name, error, order_id=order_id)
    raise error


async def close_live_equity_position(
    store: Any,
    position_id: str,
    *,
    operator_id: str,
    broker_client: Any,
    poll_interval_s: float = _FILL_POLL_INTERVAL_S,
    fill_timeout_s: float = _FILL_TIMEOUT_S,
) -> EquityPosition:
    """Mirror of :func:`submit_live_equity_order` for closing an OPEN live row."""

    if not operator_id or not operator_id.strip():
        raise ValueError("operator_id is required for live equity close")

    position = store.get_equity_position(position_id)
    if position is None:
        raise KeyError(f"unknown EquityPosition {position_id!r}")
    if _enum(position.mode) != EquityPositionMode.LIVE.value:
        raise ValueError("close_live_equity_position only accepts LIVE positions")
    if _enum(position.status) != EquityPositionStatus.OPEN.value:
        raise ValueError(
            f"close_live_equity_position requires status=OPEN, got {position.status!r}"
        )
    instrument = store.get_equity_instrument(position.instrument_id)
    if instrument is None:
        raise KeyError(
            f"position {position_id} references unknown instrument {position.instrument_id!r}"
        )

    broker_name = _broker_name(broker_client)
    side = _broker_side(position.side, opening=False)
    try:
        order = await broker_client.place_order(
            symbol=instrument.symbol,
            qty=str(position.qty),
            side=side,
            type="market",
            time_in_force="day",
            client_order_id=f"live-close-{position.id}",
        )
    except (AlpacaAPIError, LiveBrokerError) as exc:
        _on_broker_error(store, position, broker_name, exc)
        raise

    fill = await _poll_until_terminal(
        broker_client,
        order=order,
        poll_interval_s=poll_interval_s,
        timeout_s=fill_timeout_s,
    )
    status = _normalised_status(fill)
    exit_price = _decimal_or_none(
        fill.get("filled_avg_price") or fill.get("limit_price")
    )
    exit_at = _parse_dt(fill.get("filled_at")) or _now()

    if status != "filled" or exit_price is None:
        error = LiveBrokerError(
            broker=broker_name,
            code="CLOSE_NOT_FILLED",
            detail=f"terminal status={status!r}",
        )
        _on_broker_error(store, position, broker_name, error)
        raise error

    updated = _mark_closed(
        store,
        position_id,
        exit_price=exit_price,
        exit_at=exit_at,
    )
    reset_exchange_error_streak(updated.organization_id)
    log.info(
        "equity_live_position_closed",
        position_id=updated.id,
        broker=broker_name,
        symbol=instrument.symbol,
        exit_price=str(exit_price),
        realized_pnl_usd=str(updated.realized_pnl_usd),
    )
    return updated


# ── Internals ────────────────────────────────────────────────────────────────


def _load_open_context(
    store: Any, position_id: str
) -> tuple[EquityPosition, Any, Any, Any]:
    position = store.get_equity_position(position_id)
    if position is None:
        raise KeyError(f"unknown EquityPosition {position_id!r}")
    signal = store.get_equity_signal(position.signal_id)
    if signal is None:
        raise KeyError(
            f"position {position_id} references unknown signal {position.signal_id!r}"
        )
    instrument = store.get_equity_instrument(position.instrument_id)
    if instrument is None:
        raise KeyError(
            f"position {position_id} references unknown instrument "
            f"{position.instrument_id!r}"
        )
    portfolio = store.get_equity_portfolio_state(position.organization_id)
    return position, signal, instrument, portfolio


def _mark_filled(
    store: Any,
    position_id: str,
    *,
    fill_price: Decimal,
    fill_qty: Decimal,
    filled_at: datetime,
    order_id: str,
    organization_id: str,
) -> EquityPosition:
    position = store.get_equity_position(position_id)
    if position is None:
        raise KeyError(f"unknown EquityPosition {position_id!r}")
    position.entry_price = fill_price
    position.entry_at = filled_at
    position.qty = fill_qty
    if order_id:
        position.external_order_id = order_id
    position.status = EquityPositionStatus.OPEN
    position.updated_at = _now()
    store.put_equity_position(position)

    notional = (fill_price * fill_qty).quantize(_MONEY, rounding=ROUND_HALF_UP)
    portfolio = store.get_equity_portfolio_state(organization_id)
    if portfolio is not None:
        current = portfolio.live_balance_usd
        if current is not None:
            portfolio.live_balance_usd = (Decimal(current) - notional).quantize(
                _MONEY, rounding=ROUND_HALF_UP
            )
            portfolio.updated_at = _now()
            store.set_equity_portfolio_state(portfolio)
    return position


def _mark_closed(
    store: Any,
    position_id: str,
    *,
    exit_price: Decimal,
    exit_at: datetime,
) -> EquityPosition:
    position = store.get_equity_position(position_id)
    if position is None:
        raise KeyError(f"unknown EquityPosition {position_id!r}")
    position.exit_price = exit_price
    position.exit_at = exit_at
    position.status = EquityPositionStatus.CLOSED
    position.realized_pnl_usd = _realized_pnl(
        side=position.side,
        qty=position.qty,
        entry=position.entry_price,
        exit_=exit_price,
    )
    position.updated_at = _now()
    store.put_equity_position(position)
    return position


def _on_broker_error(
    store: Any,
    position: EquityPosition,
    broker_name: str,
    exc: BaseException,
    *,
    order_id: str | None = None,
) -> None:
    try:
        latest = store.get_equity_position(position.id) or position
    except Exception:  # pragma: no cover - defensive
        latest = position
    latest.status = EquityPositionStatus.FAILED
    if order_id:
        latest.external_order_id = order_id
    latest.updated_at = _now()
    try:
        store.put_equity_position(latest)
    except Exception:  # pragma: no cover - defensive
        pass
    streak = record_exchange_error(store, latest.organization_id)
    log.error(
        "equity_live_order_failed",
        position_id=latest.id,
        broker=broker_name,
        error_code=getattr(exc, "code", type(exc).__name__),
        error_detail=str(exc),
        streak=streak,
    )


async def _poll_until_terminal(
    client: Any,
    *,
    order: dict[str, Any],
    poll_interval_s: float,
    timeout_s: float,
) -> dict[str, Any]:
    if _is_terminal(order):
        return order
    order_id = str(order.get("id") or "").strip()
    if not order_id:
        return order
    deadline = asyncio.get_event_loop().time() + max(0.1, timeout_s)
    while True:
        fresh = await client.get_order(order_id)
        if fresh is None:
            return order
        if _is_terminal(fresh):
            return fresh
        if asyncio.get_event_loop().time() >= deadline:
            return fresh
        await asyncio.sleep(max(0.0, poll_interval_s))


def _is_terminal(order: dict[str, Any]) -> bool:
    return _normalised_status(order) in {
        "filled",
        "canceled",
        "rejected",
        "expired",
        "done_for_day",
    }


def _normalised_status(order: dict[str, Any]) -> str:
    raw = str(order.get("status") or "").lower()
    if raw == "cancelled":
        return "canceled"
    return raw


def _broker_side(side: Any, *, opening: bool) -> str:
    value = _enum(side)
    if value == EquityPositionSide.LONG.value:
        return "buy" if opening else "sell"
    if value == EquityPositionSide.SHORT.value:
        return "sell" if opening else "buy"
    raise ValueError(f"cannot map {side!r} to a broker side")


def _realized_pnl(
    *, side: Any, qty: Decimal, entry: Decimal, exit_: Decimal
) -> Decimal:
    value = _enum(side)
    direction = (
        Decimal("1") if value == EquityPositionSide.LONG.value else Decimal("-1")
    )
    return ((Decimal(exit_) - Decimal(entry)) * Decimal(qty) * direction).quantize(
        _MONEY, rounding=ROUND_HALF_UP
    )


def _broker_name(client: Any) -> str:
    name = getattr(client, "broker_name", None)
    if isinstance(name, str) and name:
        return name.upper()
    # AlpacaClient does not declare broker_name; default to ALPACA for it.
    return "ALPACA"


def _enum(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "submit_live_equity_order",
    "close_live_equity_position",
]
