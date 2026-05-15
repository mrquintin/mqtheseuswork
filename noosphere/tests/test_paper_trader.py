"""Tests for the Alpaca paper-trade adapter."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.equities.paper_trader import (
    PaperTradeError,
    close_paper_position,
    submit_paper_order,
)
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
    EquitySignal,
    EquitySignalDirection,
    EquitySignalStatus,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 15, 15, 30, tzinfo=timezone.utc)
ORG_ID = "org_paper_trader_test"


class _FakeAlpacaClient:
    """Minimal stand-in for ``AlpacaClient`` driving the paper trader."""

    def __init__(
        self,
        *,
        order_responses: list[dict[str, Any]],
        poll_responses: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.order_responses = list(order_responses)
        self.poll_responses = {k: list(v) for k, v in (poll_responses or {}).items()}
        self.place_calls: list[dict[str, Any]] = []
        self.poll_calls: list[str] = []

    async def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.place_calls.append(kwargs)
        return self.order_responses.pop(0)

    async def get_order(self, order_id: str) -> dict[str, Any]:
        self.poll_calls.append(order_id)
        queue = self.poll_responses.get(order_id, [])
        if queue:
            return queue.pop(0)
        return {"id": order_id, "status": "filled"}

    async def aclose(self) -> None:
        return None


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_pending_long(store: Store) -> tuple[EquityInstrument, EquityPosition]:
    instrument = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("182.00"),
        last_price_at=NOW,
    )
    store.put_equity_instrument(instrument)
    instrument = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    assert instrument is not None
    signal = EquitySignal(
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        direction=EquitySignalDirection.BULLISH,
        confidence_low=Decimal("0.60"),
        confidence_high=Decimal("0.70"),
        horizon_days=30,
        headline="Test signal",
        reasoning="Fixture.",
        model_name="fixture",
        status=EquitySignalStatus.PUBLISHED,
    )
    store.put_equity_signal(signal)
    position = EquityPosition(
        signal_id=signal.id,
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        mode=EquityPositionMode.PAPER,
        side=EquityPositionSide.LONG,
        qty=Decimal("10.000000"),
        entry_price=Decimal("0"),  # filled in by adapter
        entry_at=NOW,
        status=EquityPositionStatus.PENDING,
    )
    store.put_equity_position(position)
    return instrument, position


def test_pending_to_open_to_closed_round_trip(store: Store) -> None:
    instrument, position = _seed_pending_long(store)

    client = _FakeAlpacaClient(
        order_responses=[
            {
                "id": "ord_open_1",
                "status": "filled",
                "filled_avg_price": "182.00",
                "filled_qty": "10",
                "filled_at": NOW.isoformat().replace("+00:00", "Z"),
            },
            {
                "id": "ord_close_1",
                "status": "filled",
                "filled_avg_price": "192.00",
                "filled_qty": "10",
                "filled_at": (NOW.replace(hour=16))
                .isoformat()
                .replace("+00:00", "Z"),
            },
        ]
    )

    opened = asyncio.run(
        submit_paper_order(
            store,
            position.id,
            client=client,
            poll_interval_s=0,
            max_poll_attempts=1,
        )
    )
    assert opened.status == EquityPositionStatus.OPEN
    assert opened.entry_price == Decimal("182.00")
    assert opened.external_order_id == "ord_open_1"
    assert opened.mode == EquityPositionMode.PAPER

    # The first place_order must be a BUY for a LONG open.
    assert client.place_calls[0]["side"] == "buy"
    assert client.place_calls[0]["symbol"] == "AAPL"

    closed = asyncio.run(
        close_paper_position(
            store,
            position.id,
            client=client,
            poll_interval_s=0,
            max_poll_attempts=1,
        )
    )
    assert closed.status == EquityPositionStatus.CLOSED
    assert closed.exit_price == Decimal("192.00")
    # Long: (192 - 182) * 10 = 100.00 USD realised.
    assert closed.realized_pnl_usd == Decimal("100.00")
    # The closing place_order must be a SELL for a LONG.
    assert client.place_calls[1]["side"] == "sell"


def test_short_round_trip_uses_inverse_sides_and_pnl(store: Store) -> None:
    instrument, position = _seed_pending_long(store)
    # Reseat to SHORT for this case.
    position.side = EquityPositionSide.SHORT
    store.put_equity_position(position)

    client = _FakeAlpacaClient(
        order_responses=[
            {
                "id": "ord_short_open",
                "status": "filled",
                "filled_avg_price": "182.00",
                "filled_qty": "10",
                "filled_at": NOW.isoformat().replace("+00:00", "Z"),
            },
            {
                "id": "ord_short_close",
                "status": "filled",
                "filled_avg_price": "172.00",
                "filled_qty": "10",
                "filled_at": NOW.isoformat().replace("+00:00", "Z"),
            },
        ]
    )

    asyncio.run(
        submit_paper_order(
            store, position.id, client=client, poll_interval_s=0, max_poll_attempts=1
        )
    )
    assert client.place_calls[0]["side"] == "sell"

    closed = asyncio.run(
        close_paper_position(
            store, position.id, client=client, poll_interval_s=0, max_poll_attempts=1
        )
    )
    assert client.place_calls[1]["side"] == "buy"
    # Short: (172 - 182) * 10 * -1 = +100.00 USD.
    assert closed.realized_pnl_usd == Decimal("100.00")


def test_rejected_order_marks_position_failed(store: Store) -> None:
    _, position = _seed_pending_long(store)

    client = _FakeAlpacaClient(
        order_responses=[
            {
                "id": "ord_rejected",
                "status": "rejected",
            }
        ]
    )

    with pytest.raises(PaperTradeError):
        asyncio.run(
            submit_paper_order(
                store, position.id, client=client, poll_interval_s=0, max_poll_attempts=1
            )
        )
    reloaded = store.get_equity_position(position.id)
    assert reloaded is not None
    assert reloaded.status == EquityPositionStatus.FAILED


def test_submit_requires_paper_mode_pending(store: Store) -> None:
    _, position = _seed_pending_long(store)
    # Flip to OPEN to violate the precondition.
    position.status = EquityPositionStatus.OPEN
    store.put_equity_position(position)

    client = _FakeAlpacaClient(order_responses=[])
    with pytest.raises(PaperTradeError, match="status=PENDING"):
        asyncio.run(
            submit_paper_order(
                store, position.id, client=client, poll_interval_s=0, max_poll_attempts=1
            )
        )
