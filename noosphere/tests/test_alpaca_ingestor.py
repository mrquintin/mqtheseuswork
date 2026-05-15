"""Tests for the Alpaca equity ingestor."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.equities.alpaca_ingestor import (
    PRICE_UPDATE_THRESHOLD,
    ingest_once,
)
from noosphere.equities.config import AlpacaConfig
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPositionSide,
    EquityPriceSource,
    EquitySignal,
    EquitySignalDirection,
    EquitySignalStatus,
)
from noosphere.store import Store


API_BASE = "https://paper-api.alpaca.test"
DATA_BASE = "https://data.alpaca.test"
NOW = datetime(2026, 5, 15, 15, 30, tzinfo=timezone.utc)
ORG_ID = "org_equities_test"


def _config(symbols: list[str] | None = None) -> AlpacaConfig:
    return AlpacaConfig(
        api_base=API_BASE,
        data_base=DATA_BASE,
        api_key_id="PKTEST",
        api_secret_key="secret",
        organization_id=ORG_ID,
        is_paper=True,
        accepted_symbols=symbols or [],
    )


class _StubAlpacaClient:
    """Module-level stub installed via monkeypatch."""

    def __init__(
        self,
        *,
        assets: list[dict[str, Any]],
        bars: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.assets = assets
        self.bars = bars or {}
        self.list_calls = 0
        self.bar_calls: list[str] = []
        self.closed = False

    def factory(self, *_args: Any, **_kwargs: Any) -> "_StubAlpacaClient":
        return self

    async def list_assets(self, **_: Any) -> list[dict[str, Any]]:
        self.list_calls += 1
        return list(self.assets)

    async def get_bars(self, symbol: str, **_: Any) -> list[dict[str, Any]]:
        self.bar_calls.append(symbol)
        return list(self.bars.get(symbol, []))

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture
def forbid_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: ensure no real httpx client is constructed during ingestor tests."""
    import httpx

    class _Forbidden:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError(
                f"unexpected httpx.AsyncClient construction during test: "
                f"args={args!r} kwargs={kwargs!r}"
            )

    monkeypatch.setattr(httpx, "AsyncClient", _Forbidden)


def _install_stub(
    monkeypatch: pytest.MonkeyPatch, stub: _StubAlpacaClient
) -> None:
    from noosphere.equities import alpaca_ingestor

    monkeypatch.setattr(alpaca_ingestor, "AlpacaClient", stub.factory)


def test_not_configured_is_noop_and_skips_httpx(
    store: Store, forbid_httpx: None
) -> None:
    cfg = AlpacaConfig(api_key_id="", api_secret_key="")
    result = asyncio.run(ingest_once(store, config=cfg, now=NOW))
    assert result.fetched == 0
    assert result.inserted == 0
    assert result.errors == []
    assert store.list_equity_instruments() == []


def test_fresh_insert_creates_instrument(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    forbid_httpx: None,
) -> None:
    stub = _StubAlpacaClient(
        assets=[
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Apple Inc.",
                "tradable": True,
                "last_price": "182.50",
            }
        ]
    )
    _install_stub(monkeypatch, stub)

    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert (result.fetched, result.inserted, result.updated, result.skipped) == (
        1, 1, 0, 0,
    )
    loaded = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    assert loaded is not None
    assert loaded.last_price == Decimal("182.50")
    # SQLite strips tzinfo on round-trip; compare on the naive timestamp.
    assert loaded.last_price_at is not None
    assert loaded.last_price_at.replace(tzinfo=None) == NOW.replace(tzinfo=None)
    assert loaded.asset_class == EquityAssetClass.STOCK


def test_update_when_price_moves_beyond_threshold(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    forbid_httpx: None,
) -> None:
    # Seed an existing instrument at $100 with a recent timestamp so only
    # an above-threshold move can trigger the update.
    seeded = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("100.000000"),
        last_price_at=NOW - timedelta(seconds=30),
    )
    store.put_equity_instrument(seeded)

    threshold_price = Decimal("100.000000") * (Decimal("1") + PRICE_UPDATE_THRESHOLD)
    stub = _StubAlpacaClient(
        assets=[
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Apple Inc.",
                "tradable": True,
                "last_price": str(threshold_price),
            }
        ]
    )
    _install_stub(monkeypatch, stub)

    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert result.updated == 1
    assert result.inserted == 0
    loaded = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    assert loaded is not None
    assert loaded.last_price == threshold_price


def test_skip_when_price_unchanged_and_fresh(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    forbid_httpx: None,
) -> None:
    seeded = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("100.000000"),
        last_price_at=NOW - timedelta(seconds=30),
    )
    store.put_equity_instrument(seeded)

    sub_threshold = Decimal("100.10")  # 0.1% move — under the 0.5% gate.
    stub = _StubAlpacaClient(
        assets=[
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Apple Inc.",
                "tradable": True,
                "last_price": str(sub_threshold),
            }
        ]
    )
    _install_stub(monkeypatch, stub)

    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert result.skipped == 1
    assert result.updated == 0
    loaded = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    assert loaded is not None
    assert loaded.last_price == Decimal("100.000000")


def test_intraday_bars_only_fetched_for_held_signal_instruments(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    forbid_httpx: None,
) -> None:
    # Seed a published signal on AAPL only; MSFT has no signal — should be skipped.
    aapl = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("182.00"),
        last_price_at=NOW - timedelta(minutes=10),
    )
    msft = EquityInstrument(
        symbol="MSFT",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Microsoft Corp.",
        last_price=Decimal("420.00"),
        last_price_at=NOW - timedelta(minutes=10),
    )
    store.put_equity_instrument(aapl)
    store.put_equity_instrument(msft)
    aapl = store.get_equity_instrument_by_symbol("AAPL", "NASDAQ")
    msft = store.get_equity_instrument_by_symbol("MSFT", "NASDAQ")
    assert aapl is not None and msft is not None
    signal = EquitySignal(
        instrument_id=aapl.id,
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

    stub = _StubAlpacaClient(
        assets=[
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Apple Inc.",
                "tradable": True,
                "last_price": "183.00",
            },
            {
                "symbol": "MSFT",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Microsoft Corp.",
                "tradable": True,
                "last_price": "421.00",
            },
        ],
        bars={
            "AAPL": [
                {
                    "t": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                    "o": 182.5,
                    "h": 183.1,
                    "l": 182.3,
                    "c": 183.0,
                    "v": 8500,
                }
            ],
            "MSFT": [
                {
                    "t": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                    "o": 420.0,
                    "h": 421.0,
                    "l": 419.9,
                    "c": 421.0,
                    "v": 9000,
                }
            ],
        },
    )
    _install_stub(monkeypatch, stub)

    asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert stub.bar_calls == ["AAPL"]
    assert len(store.list_equity_price_ticks(aapl.id)) == 1
    assert store.list_equity_price_ticks(msft.id) == []
    tick = store.list_equity_price_ticks(aapl.id)[0]
    assert tick.source == EquityPriceSource.ALPACA


def test_accepted_symbols_filters_assets(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    forbid_httpx: None,
) -> None:
    stub = _StubAlpacaClient(
        assets=[
            {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Apple Inc.",
                "tradable": True,
                "last_price": "182.50",
            },
            {
                "symbol": "TSLA",
                "exchange": "NASDAQ",
                "class": "us_equity",
                "name": "Tesla Inc.",
                "tradable": True,
                "last_price": "250.00",
            },
        ]
    )
    _install_stub(monkeypatch, stub)

    result = asyncio.run(
        ingest_once(store, config=_config(symbols=["AAPL"]), now=NOW)
    )
    assert result.fetched == 1
    assert store.get_equity_instrument_by_symbol("TSLA", "NASDAQ") is None
