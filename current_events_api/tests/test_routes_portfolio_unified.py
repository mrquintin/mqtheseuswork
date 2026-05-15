"""Tests for the unified portfolio API surface.

Exercises:

* ``GET /v1/portfolio`` — now returns the cross-asset-class overview
  with the prior forecast fields preserved at the top level.
* ``GET /v1/portfolio/equities`` — the equity-track surface.
* ``GET /v1/portfolio/decision-trace/{position_id}`` — round-trips both
  a ForecastBet id and an EquityPosition id.
* Live-status pills reflect ``FORECASTS_LIVE_TRADING_ENABLED`` and
  ``EQUITIES_LIVE_TRADING_ENABLED`` environment flags.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPortfolioState,
    EquityPosition,
    EquityPositionMode,
    EquityPositionSide,
    EquityPositionStatus,
    EquitySignal,
    EquitySignalCitation,
    EquitySignalDirection,
    EquitySignalStatus,
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastCitation,
    ForecastExchange,
    ForecastMarket,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    ForecastSupportLabel,
    ForecastTrace,
)

ORG_ID = "org_unified_portfolio"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


def _seed_forecast(store) -> str:
    market = ForecastMarket(
        id="uport_market",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="uport_market_external",
        title="Will the proposition pass?",
        category="policy",
        current_yes_price=Decimal("0.600000"),
        current_no_price=Decimal("0.400000"),
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id="uport_prediction",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.700000"),
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        headline="Unified portfolio forecast fixture",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="policy",
        model_name="fixture-model",
        created_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    store.put_forecast_citation(
        ForecastCitation(
            id="uport_citation",
            prediction_id=prediction.id,
            source_type="CONCLUSION",
            source_id="uport_conclusion_1",
            quoted_span="proposition pass",
            support_label=ForecastSupportLabel.DIRECT,
            retrieval_score=0.91,
        )
    )
    store.put_forecast_trace(
        ForecastTrace(
            id="uport_trace",
            prediction_id=prediction.id,
            market_id=market.id,
            organization_id=ORG_ID,
            market_title=market.title,
            principles_used=[
                {
                    "conclusionId": "uport_conclusion_1",
                    "weight": 0.91,
                    "snippet": "Term-end clustering favors YES",
                }
            ],
            model_output={
                "side": "YES",
                "edge": 0.1,
                "confidence": 0.8,
                "rationale": prediction.headline,
            },
            gate_results=[
                {
                    "gateName": "paper_edge_threshold",
                    "passed": True,
                    "reason": "paper fill recorded",
                }
            ],
        )
    )
    store.put_forecast_resolution(
        ForecastResolution(
            id="uport_resolution",
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.YES,
            brier_score=0.09,
            log_loss=0.357,
            calibration_bucket=Decimal("0.7"),
            resolved_at=NOW + timedelta(days=1),
            justification="Resolved YES.",
        )
    )
    settled_bet = ForecastBet(
        id="uport_paper_bet",
        prediction_id=prediction.id,
        organization_id=ORG_ID,
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("100.00"),
        entry_price=Decimal("0.600000"),
        exit_price=Decimal("1.000000"),
        status=ForecastBetStatus.SETTLED,
        settlement_pnl_usd=Decimal("66.67"),
        created_at=NOW + timedelta(minutes=1),
        settled_at=NOW + timedelta(days=1),
    )
    store.put_forecast_bet(settled_bet)
    # Open paper bet so the overview's active-principles rail has data.
    open_bet = ForecastBet(
        id="uport_open_bet",
        prediction_id=prediction.id,
        organization_id=ORG_ID,
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("50.00"),
        entry_price=Decimal("0.620000"),
        status=ForecastBetStatus.FILLED,
        created_at=NOW + timedelta(minutes=2),
    )
    store.put_forecast_bet(open_bet)
    store.set_portfolio_state(
        ForecastPortfolioState(
            id="uport_state",
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10066.67"),
            live_balance_usd=Decimal("1000.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=NOW,
            kill_switch_engaged=False,
            kill_switch_reason=None,
            total_resolved=1,
            mean_brier_90d=0.09,
            mean_log_loss_90d=0.357,
            updated_at=NOW + timedelta(days=1),
        )
    )
    return settled_bet.id


def _seed_equity(store) -> str:
    instrument = EquityInstrument(
        id="uport_instrument",
        symbol="MSFT",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Microsoft Corporation",
        currency="USD",
    )
    store.put_equity_instrument(instrument)
    signal = EquitySignal(
        id="uport_signal",
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        direction=EquitySignalDirection.BULLISH,
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        target_price_low=Decimal("370.000000"),
        target_price_high=Decimal("410.000000"),
        horizon_days=30,
        headline="Re-rating on AI margin expansion",
        reasoning="Margin lift sustains.",
        model_name="fixture-model",
        status=EquitySignalStatus.PUBLISHED,
        created_at=NOW,
    )
    store.put_equity_signal(signal)
    store.put_equity_signal_citation(
        EquitySignalCitation(
            id="uport_signal_cit",
            signal_id=signal.id,
            source_type="TRANSCRIPT",
            source_id="msft_q3_call",
            quoted_span="AI margin expansion lifted gross margin",
            support_label=ForecastSupportLabel.DIRECT,
        )
    )
    open_position = EquityPosition(
        id="pos_uport_open",
        signal_id=signal.id,
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        mode=EquityPositionMode.PAPER,
        side=EquityPositionSide.LONG,
        qty=Decimal("5.000000"),
        entry_price=Decimal("350.120000"),
        entry_at=NOW,
        status=EquityPositionStatus.OPEN,
        unrealized_pnl_usd=Decimal("12.5000"),
    )
    store.put_equity_position(open_position)
    closed_position = EquityPosition(
        id="pos_uport_closed",
        signal_id=signal.id,
        instrument_id=instrument.id,
        organization_id=ORG_ID,
        mode=EquityPositionMode.PAPER,
        side=EquityPositionSide.LONG,
        qty=Decimal("4.000000"),
        entry_price=Decimal("355.000000"),
        entry_at=NOW - timedelta(days=10),
        exit_price=Decimal("380.000000"),
        exit_at=NOW + timedelta(days=2),
        status=EquityPositionStatus.CLOSED,
        realized_pnl_usd=Decimal("100.0000"),
    )
    store.put_equity_position(closed_position)
    store.set_equity_portfolio_state(
        EquityPortfolioState(
            id="uport_eq_state",
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("9500.00"),
            daily_loss_window_reset_at=NOW,
            kill_switch_engaged=False,
        )
    )
    return open_position.id


def test_unified_overview_is_superset_of_forecast_summary(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORECASTS_ORG_ID", ORG_ID)
    monkeypatch.delenv("FORECASTS_LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("EQUITIES_LIVE_TRADING_ENABLED", raising=False)
    _seed_forecast(client.app.state.store)
    _seed_equity(client.app.state.store)

    response = client.get("/v1/portfolio")
    assert response.status_code == 200
    body = response.json()

    # Back-compat: old payload fields still served at the same paths.
    assert body["organization_id"] == ORG_ID
    assert body["paper_balance_usd"] == 10066.67
    assert body["mean_brier_90d"] == 0.09
    assert body["total_bets"] == 2
    assert body["paper_pnl_curve"][0]["paper_pnl_usd"] == 66.67

    # New unified fields exist.
    assert body["forecasts"]["open_positions"] == 1
    assert body["forecasts"]["realized_paper_pnl_usd"] == 66.67
    assert body["equities"]["open_positions"] == 1
    assert body["equities"]["realized_paper_pnl_usd"] == 100.0
    assert body["net_paper_pnl_usd"] == pytest.approx(166.67)
    curve_values = sorted(pt["paper_pnl_usd"] for pt in body["net_paper_pnl_curve"])
    assert curve_values[0] == pytest.approx(66.67)
    assert curve_values[-1] == pytest.approx(166.67)

    # Live pills default to DISABLED when no env flag is set.
    assert body["live_status"]["forecasts"] == "DISABLED"
    assert body["live_status"]["equities"] == "DISABLED"

    # Active principles surface the conclusion from the open paper bet.
    principle_ids = [p["conclusion_id"] for p in body["active_principles"]]
    assert "uport_conclusion_1" in principle_ids
    assert body["active_principles"][0]["position_count"] == 1


def test_unified_overview_renders_with_one_track_empty(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORECASTS_ORG_ID", ORG_ID)
    _seed_forecast(client.app.state.store)
    response = client.get("/v1/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["equities"]["open_positions"] == 0
    assert body["equities"]["realized_paper_pnl_usd"] == 0.0
    assert body["forecasts"]["open_positions"] == 1


def test_live_status_pills_reflect_env_flags(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORECASTS_ORG_ID", ORG_ID)
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("EQUITIES_LIVE_TRADING_ENABLED", "true")
    monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_KEY_ID", raising=False)
    monkeypatch.delenv("ROBINHOOD_USERNAME", raising=False)
    _seed_forecast(client.app.state.store)
    response = client.get("/v1/portfolio")
    body = response.json()
    # Flag is on but no exchange credentials present → awaiting auth.
    assert body["live_status"]["forecasts"] == "ENABLED-AWAITING-AUTH"
    assert body["live_status"]["equities"] == "ENABLED-AWAITING-AUTH"

    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "fake-key")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "fake-id")
    response = client.get("/v1/portfolio")
    body = response.json()
    assert body["live_status"]["forecasts"] == "ENABLED"
    assert body["live_status"]["equities"] == "ENABLED"


def test_equity_portfolio_surface_returns_paper_positions_only(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORECASTS_ORG_ID", ORG_ID)
    _seed_equity(client.app.state.store)
    response = client.get("/v1/portfolio/equities")
    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == ORG_ID
    assert body["paper_balance_usd"] == 9500.0
    open_symbols = [pos["instrument_symbol"] for pos in body["open_positions"]]
    assert open_symbols == ["MSFT"]
    assert body["recent_signals"][0]["headline"] == "Re-rating on AI margin expansion"
    assert body["paper_pnl_curve"][-1]["paper_pnl_usd"] == 100.0
    # MAPE bucket: target midpoint is 390, actual exit is 380 → |380-390|/390 ≈ 0.0256
    populated = [b for b in body["target_price_mape"] if b["n"] > 0]
    assert populated, "expected at least one MAPE bucket to be populated"
    assert populated[0]["horizon_label"] == "8–30 days"
    assert populated[0]["mean_absolute_pct_error"] == pytest.approx(
        abs(380 - 390) / 390
    )


def test_decision_trace_round_trips_forecast_and_equity_positions(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORECASTS_ORG_ID", ORG_ID)
    forecast_bet_id = _seed_forecast(client.app.state.store)
    equity_position_id = _seed_equity(client.app.state.store)

    # Forecast trace.
    response = client.get(
        f"/v1/portfolio/decision-trace/{forecast_bet_id}",
        params={"type": "forecast"},
    )
    assert response.status_code == 200, response.text
    forecast_trace = response.json()
    assert forecast_trace["kind"] == "forecast"
    assert forecast_trace["position_id"] == forecast_bet_id
    assert forecast_trace["market_or_instrument_title"] == "Will the proposition pass?"
    assert forecast_trace["principles"][0]["conclusion_id"] == "uport_conclusion_1"
    assert forecast_trace["citations"][0]["source_id"] == "uport_conclusion_1"
    assert forecast_trace["signal"]["headline"] == "Unified portfolio forecast fixture"
    assert forecast_trace["fill"]["realized_pnl_usd"] == 66.67
    assert forecast_trace["resolution"]["outcome"] == "YES"

    # Equity trace.
    response = client.get(
        f"/v1/portfolio/decision-trace/{equity_position_id}",
        params={"type": "equity"},
    )
    assert response.status_code == 200, response.text
    equity_trace = response.json()
    assert equity_trace["kind"] == "equity"
    assert equity_trace["position_id"] == equity_position_id
    assert equity_trace["market_or_instrument_title"] == "MSFT"
    assert equity_trace["signal"]["direction_or_side"] == "BULLISH"
    assert equity_trace["citations"][0]["source_id"] == "msft_q3_call"
    assert equity_trace["resolution"] is None

    # Prefix-based dispatch (id starts with "pos_" → equity branch).
    response = client.get(f"/v1/portfolio/decision-trace/{equity_position_id}")
    assert response.status_code == 200
    assert response.json()["kind"] == "equity"

    # Missing id → 404.
    response = client.get("/v1/portfolio/decision-trace/does_not_exist")
    assert response.status_code == 404
