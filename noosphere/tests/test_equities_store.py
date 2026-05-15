"""Equities Store accessors, migrations, and shared safety contract."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from noosphere.forecasts.safety import (
    GateFailure,
    check_all_equity_gates,
    gate_context_from_env_for_equities,
)
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPortfolioState,
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
    EquityPriceSource,
    EquityPriceTick,
    EquitySignal,
    EquitySignalCitation,
    EquitySignalDirection,
    EquitySignalStatus,
    ForecastSupportLabel,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)


# ── Seed round-trip ──────────────────────────────────────────────────────────


def test_equities_seed_round_trips_every_store_helper(equities_seed) -> None:
    st = equities_seed["store"]
    org_id = equities_seed["organization_id"]
    stock, etf = equities_seed["instruments"]
    signal = equities_seed["signals"][0]
    position = equities_seed["positions"][0]

    loaded_stock = st.get_equity_instrument(stock.id)
    assert loaded_stock is not None
    assert loaded_stock.symbol == "AAPL"
    assert loaded_stock.exchange == "NASDAQ"
    assert loaded_stock.asset_class == EquityAssetClass.STOCK
    assert loaded_stock.currency == "USD"

    loaded_etf = st.get_equity_instrument_by_symbol("SPY", "NYSE")
    assert loaded_etf is not None
    assert loaded_etf.id == etf.id
    assert loaded_etf.asset_class == EquityAssetClass.ETF

    instruments = st.list_equity_instruments()
    assert {i.id for i in instruments} >= {stock.id, etf.id}

    ticks = st.list_equity_price_ticks(stock.id)
    assert len(ticks) == 3
    # Newest first.
    assert ticks[0].ts >= ticks[-1].ts

    loaded_signal = st.get_equity_signal(signal.id)
    assert loaded_signal is not None
    assert loaded_signal.direction == EquitySignalDirection.BULLISH
    assert loaded_signal.status == EquitySignalStatus.PUBLISHED
    assert loaded_signal.horizon_days == 30

    open_signals = st.list_open_signals(organization_id=org_id)
    assert any(s.id == signal.id for s in open_signals)

    loaded_position = st.get_equity_position(position.id)
    assert loaded_position is not None
    assert loaded_position.mode == EquityPositionMode.PAPER
    assert loaded_position.side == EquityPositionSide.LONG
    assert loaded_position.status == EquityPositionStatus.OPEN

    positions = st.list_positions_for_signal(signal.id)
    assert [p.id for p in positions] == [position.id]

    state = st.get_equity_portfolio_state(org_id)
    assert state is not None
    assert state.paper_balance_usd == Decimal("10000.00")
    assert state.kill_switch_engaged is False


def test_put_equity_signal_citation_round_trips(equities_seed) -> None:
    st = equities_seed["store"]
    signal = equities_seed["signals"][0]
    citation = EquitySignalCitation(
        id="equity_citation_1",
        signal_id=signal.id,
        source_type="Conclusion",
        source_id="conclusion_apple_services",
        quoted_span="Services revenue grew 16% YoY, outpacing hardware.",
        support_label=ForecastSupportLabel.DIRECT,
    )
    st.put_equity_signal_citation(citation)

    rows = st.list_equity_signal_citations(signal.id)
    assert len(rows) == 1
    assert rows[0].source_id == "conclusion_apple_services"
    assert rows[0].support_label == ForecastSupportLabel.DIRECT


# ── Compound unique key: (symbol, exchange) ─────────────────────────────────


def test_compound_unique_key_rejects_duplicate_symbol_exchange(tmp_path) -> None:
    st = Store.from_database_url(f"sqlite:///{tmp_path / 'eq.db'}")
    first = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
    )
    st.put_equity_instrument(first)

    # Inserting a second row by raw session.add (bypassing upsert) must fail
    # on the unique constraint.
    duplicate = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc. duplicate",
    )
    with pytest.raises(IntegrityError):
        with st.session() as s:
            s.add(duplicate)
            s.commit()


def test_compound_unique_key_allows_same_symbol_different_exchange(tmp_path) -> None:
    st = Store.from_database_url(f"sqlite:///{tmp_path / 'eq.db'}")
    st.put_equity_instrument(
        EquityInstrument(
            symbol="AAPL",
            exchange="NASDAQ",
            asset_class=EquityAssetClass.STOCK,
            name="Apple Inc.",
        )
    )
    # An ADR on a different exchange uses the same ticker — must be permitted.
    st.put_equity_instrument(
        EquityInstrument(
            symbol="AAPL",
            exchange="NEOE",
            asset_class=EquityAssetClass.ADR,
            name="Apple Inc. CDR",
        )
    )
    assert len(st.list_equity_instruments()) == 2


# ── live=PAPER allowed without authorization; live=LIVE requires authorization ─


def test_live_position_requires_live_authorized_at(tmp_path) -> None:
    st = Store.from_database_url(f"sqlite:///{tmp_path / 'eq.db'}")
    instrument = EquityInstrument(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
    )
    st.put_equity_instrument(instrument)
    signal = EquitySignal(
        instrument_id=instrument.id,
        organization_id="org_test",
        direction=EquitySignalDirection.BULLISH,
        confidence_low=Decimal("0.55"),
        confidence_high=Decimal("0.70"),
        horizon_days=30,
        headline="x",
        reasoning="x",
        model_name="m",
        status=EquitySignalStatus.PUBLISHED,
    )
    st.put_equity_signal(signal)

    live_unauthorized = EquityPosition(
        signal_id=signal.id,
        instrument_id=instrument.id,
        organization_id="org_test",
        mode=EquityPositionMode.LIVE,
        side=EquityPositionSide.LONG,
        qty=Decimal("1"),
        entry_price=Decimal("100"),
        entry_at=NOW,
        status=EquityPositionStatus.PENDING,
    )
    with pytest.raises(ValueError, match="live_authorized_at"):
        st.put_equity_position(live_unauthorized)


# ── Eight-gate safety contract on an EquityPosition under default env ───────


def test_equity_gate_check_returns_disabled_under_default_env(
    monkeypatch: pytest.MonkeyPatch, equities_seed
) -> None:
    for key in (
        "FORECASTS_LIVE_TRADING_ENABLED",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
        "ROBINHOOD_ENABLED",
        "ROBINHOOD_USERNAME",
        "ROBINHOOD_PASSWORD",
        "FORECASTS_MAX_STAKE_USD",
        "FORECASTS_MAX_DAILY_LOSS_USD",
    ):
        monkeypatch.delenv(key, raising=False)

    state = equities_seed["portfolio"]
    signal = equities_seed["signals"][0]
    position = equities_seed["positions"][0]

    ctx = gate_context_from_env_for_equities(state)
    with pytest.raises(GateFailure) as excinfo:
        check_all_equity_gates(signal=signal, position=position, ctx=ctx)
    assert excinfo.value.code == "DISABLED"


# ── Migrate up / down / up on a throwaway DB ─────────────────────────────────


def test_alembic_upgrade_downgrade_upgrade(tmp_path) -> None:
    """Alembic upgrade head → downgrade -1 → upgrade head leaves equities tables intact."""
    from unittest.mock import MagicMock, patch

    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'mig.db'}"
    ini_path = os.path.join(
        os.path.dirname(__file__), "..", "alembic.ini"
    )

    mock_settings = MagicMock()
    mock_settings.database_url = db_url
    mock_settings.embedding_model_name = "test-model"

    cfg = Config(ini_path)
    with patch("noosphere.config.get_settings", return_value=mock_settings):
        command.upgrade(cfg, "head")

        # Tables present at head.
        from sqlalchemy import create_engine, inspect

        engine = create_engine(db_url)
        tables_at_head = set(inspect(engine).get_table_names())
        engine.dispose()
        for expected in (
            "EquityInstrument",
            "EquityPriceTick",
            "EquitySignal",
            "EquitySignalCitation",
            "EquityPosition",
            "EquityPortfolioState",
        ):
            assert expected in tables_at_head, f"missing table after upgrade: {expected}"

        # Roll back the equities migration.
        command.downgrade(cfg, "-1")
        engine = create_engine(db_url)
        tables_after_down = set(inspect(engine).get_table_names())
        engine.dispose()
        for dropped in (
            "EquityInstrument",
            "EquityPriceTick",
            "EquitySignal",
            "EquitySignalCitation",
            "EquityPosition",
            "EquityPortfolioState",
        ):
            assert dropped not in tables_after_down, f"table {dropped} survived downgrade"
        # Forecast* tables are not touched by this migration.
        assert "ForecastMarket" in tables_after_down

        # And re-applying is clean.
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        tables_redo = set(inspect(engine).get_table_names())
        engine.dispose()
        assert "EquityInstrument" in tables_redo
