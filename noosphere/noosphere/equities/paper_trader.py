"""Paper-trade adapter against Alpaca's paper environment.

Eight-gate checks are NOT applied here — paper is the rehearsal surface,
not the live one. Live trading on Alpaca is gated separately (see the
shared safety contract in ``noosphere.forecasts.safety``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from noosphere.equities._alpaca_client import AlpacaAPIError, AlpacaClient
from noosphere.models import (
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
)
from noosphere.observability import get_logger
from noosphere.store import Store


# Default polling cadence when waiting for a paper order to fill. Kept
# small for tests; production callers can pre-fill the order id.
_FILL_POLL_INTERVAL_S = 0.25
_FILL_POLL_MAX_ATTEMPTS = 20

log = get_logger(__name__)


class PaperTradeError(RuntimeError):
    """Raised when a paper-trade adapter call cannot complete cleanly."""


async def submit_paper_order(
    store: Store,
    position_id: str,
    *,
    client: AlpacaClient,
    poll_interval_s: float = _FILL_POLL_INTERVAL_S,
    max_poll_attempts: int = _FILL_POLL_MAX_ATTEMPTS,
) -> EquityPosition:
    """Submit a PENDING ``EquityPosition`` to Alpaca paper and await fill.

    On a fill, the position is moved to OPEN with ``entry_price`` /
    ``entry_at`` set from the broker response. On a rejection the row is
    moved to FAILED. The position MUST be ``mode=PAPER``.
    """

    position = store.get_equity_position(position_id)
    if position is None:
        raise PaperTradeError(f"unknown EquityPosition id {position_id!r}")
    if _enum_value(position.mode) != EquityPositionMode.PAPER.value:
        raise PaperTradeError(
            f"submit_paper_order requires mode=PAPER, got {position.mode!r}"
        )
    if _enum_value(position.status) != EquityPositionStatus.PENDING.value:
        raise PaperTradeError(
            f"submit_paper_order requires status=PENDING, "
            f"got {position.status!r}"
        )

    instrument = store.get_equity_instrument(position.instrument_id)
    if instrument is None:
        raise PaperTradeError(
            f"position {position_id} references unknown instrument "
            f"{position.instrument_id!r}"
        )

    side = _broker_side(position.side, opening=True)
    try:
        order = await client.place_order(
            symbol=instrument.symbol,
            qty=str(position.qty),
            side=side,
            type="market",
            time_in_force="day",
            client_order_id=f"paper-open-{position.id}",
        )
    except AlpacaAPIError as exc:
        position.status = EquityPositionStatus.FAILED
        store.put_equity_position(position)
        log.info(
            "alpaca_paper_order_rejected",
            position_id=position.id,
            symbol=instrument.symbol,
            status_code=exc.status_code,
        )
        raise

    order_id = str(order.get("id") or "").strip()
    fill = await _poll_until_terminal(
        client,
        order=order,
        poll_interval_s=poll_interval_s,
        max_attempts=max_poll_attempts,
    )

    fill_price = _decimal_or_none(
        fill.get("filled_avg_price") or fill.get("limit_price")
    )
    fill_qty = _decimal_or_none(fill.get("filled_qty")) or position.qty
    filled_at = _parse_dt(fill.get("filled_at")) or _now()
    status = str(fill.get("status") or "").lower()

    if status == "filled" and fill_price is not None:
        position.entry_price = fill_price
        position.entry_at = filled_at
        position.qty = fill_qty
        position.external_order_id = order_id or position.external_order_id
        position.status = EquityPositionStatus.OPEN
        store.put_equity_position(position)
        log.info(
            "alpaca_paper_order_filled",
            position_id=position.id,
            symbol=instrument.symbol,
            entry_price=str(fill_price),
            qty=str(fill_qty),
        )
        return position

    position.status = EquityPositionStatus.FAILED
    position.external_order_id = order_id or position.external_order_id
    store.put_equity_position(position)
    log.info(
        "alpaca_paper_order_failed",
        position_id=position.id,
        symbol=instrument.symbol,
        terminal_status=status,
    )
    raise PaperTradeError(
        f"paper order did not fill cleanly: status={status!r}"
    )


async def close_paper_position(
    store: Store,
    position_id: str,
    *,
    client: AlpacaClient,
    poll_interval_s: float = _FILL_POLL_INTERVAL_S,
    max_poll_attempts: int = _FILL_POLL_MAX_ATTEMPTS,
) -> EquityPosition:
    """Submit the closing order for an OPEN paper position and settle P&L."""

    position = store.get_equity_position(position_id)
    if position is None:
        raise PaperTradeError(f"unknown EquityPosition id {position_id!r}")
    if _enum_value(position.mode) != EquityPositionMode.PAPER.value:
        raise PaperTradeError(
            f"close_paper_position requires mode=PAPER, got {position.mode!r}"
        )
    if _enum_value(position.status) != EquityPositionStatus.OPEN.value:
        raise PaperTradeError(
            f"close_paper_position requires status=OPEN, got {position.status!r}"
        )

    instrument = store.get_equity_instrument(position.instrument_id)
    if instrument is None:
        raise PaperTradeError(
            f"position {position_id} references unknown instrument "
            f"{position.instrument_id!r}"
        )

    side = _broker_side(position.side, opening=False)
    order = await client.place_order(
        symbol=instrument.symbol,
        qty=str(position.qty),
        side=side,
        type="market",
        time_in_force="day",
        client_order_id=f"paper-close-{position.id}",
    )

    fill = await _poll_until_terminal(
        client,
        order=order,
        poll_interval_s=poll_interval_s,
        max_attempts=max_poll_attempts,
    )

    exit_price = _decimal_or_none(
        fill.get("filled_avg_price") or fill.get("limit_price")
    )
    exit_at = _parse_dt(fill.get("filled_at")) or _now()
    status = str(fill.get("status") or "").lower()
    if status != "filled" or exit_price is None:
        raise PaperTradeError(
            f"paper close did not fill cleanly: status={status!r}"
        )

    position.exit_price = exit_price
    position.exit_at = exit_at
    position.status = EquityPositionStatus.CLOSED
    position.realized_pnl_usd = _realized_pnl(
        side=position.side,
        qty=position.qty,
        entry=position.entry_price,
        exit_=exit_price,
    )
    store.put_equity_position(position)
    log.info(
        "alpaca_paper_position_closed",
        position_id=position.id,
        symbol=instrument.symbol,
        exit_price=str(exit_price),
        realized_pnl_usd=str(position.realized_pnl_usd),
    )
    return position


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _poll_until_terminal(
    client: AlpacaClient,
    *,
    order: dict[str, Any],
    poll_interval_s: float,
    max_attempts: int,
) -> dict[str, Any]:
    if _is_terminal(order):
        return order
    order_id = str(order.get("id") or "").strip()
    if not order_id:
        return order
    for _ in range(max(1, int(max_attempts))):
        fresh = await client.get_order(order_id)
        if fresh is None:
            break
        if _is_terminal(fresh):
            return fresh
        await asyncio.sleep(poll_interval_s)
    return order


def _is_terminal(order: dict[str, Any]) -> bool:
    status = str(order.get("status") or "").lower()
    return status in {
        "filled",
        "canceled",
        "cancelled",
        "rejected",
        "expired",
        "done_for_day",
    }


def _broker_side(side: Any, *, opening: bool) -> str:
    value = _enum_value(side)
    if value == EquityPositionSide.LONG.value:
        return "buy" if opening else "sell"
    if value == EquityPositionSide.SHORT.value:
        return "sell" if opening else "buy"
    raise PaperTradeError(f"cannot map {side!r} to a broker side")


def _realized_pnl(
    *,
    side: Any,
    qty: Decimal,
    entry: Decimal,
    exit_: Decimal,
) -> Decimal:
    value = _enum_value(side)
    direction = Decimal("1") if value == EquityPositionSide.LONG.value else Decimal("-1")
    return (Decimal(exit_) - Decimal(entry)) * Decimal(qty) * direction


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


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)
