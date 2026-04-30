from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    ForecastResolution,
    ForecastOutcome,
    ForecastSource,
)

ORG_ID = "org_portfolio_api"
NOW = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)


def seed_portfolio(store) -> None:
    market = ForecastMarket(
        id="portfolio_market",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="portfolio_market_external",
        title="Will the market resolve yes?",
        category="policy",
        current_yes_price=Decimal("0.600000"),
        current_no_price=Decimal("0.400000"),
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id="portfolio_prediction",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.700000"),
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        headline="Portfolio fixture forecast",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="policy",
        model_name="fixture-model",
        created_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    store.put_forecast_resolution(
        ForecastResolution(
            id="portfolio_resolution",
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.YES,
            brier_score=0.09,
            log_loss=0.357,
            calibration_bucket=Decimal("0.7"),
            resolved_at=NOW + timedelta(days=1),
            justification="Resolved YES.",
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id="portfolio_paper_bet",
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
    )
    store.put_forecast_bet(
        ForecastBet(
            id="portfolio_live_bet",
            prediction_id=prediction.id,
            organization_id=ORG_ID,
            mode=ForecastBetMode.LIVE,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("10.00"),
            entry_price=Decimal("0.600000"),
            status=ForecastBetStatus.SUBMITTED,
            external_order_id="live-order",
            live_authorized_at=NOW,
            created_at=NOW + timedelta(minutes=2),
        )
    )
    store.set_portfolio_state(
        ForecastPortfolioState(
            id="portfolio_state",
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10066.67"),
            live_balance_usd=Decimal("1000.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=NOW,
            kill_switch_engaged=True,
            kill_switch_reason="OPERATOR",
            total_resolved=1,
            mean_brier_90d=0.09,
            mean_log_loss_90d=0.357,
            updated_at=NOW + timedelta(days=1),
        )
    )


def test_portfolio_summary_and_calibration_are_public_safe(client) -> None:
    seed_portfolio(client.app.state.store)

    summary_response = client.get("/v1/portfolio")
    calibration_response = client.get("/v1/portfolio/calibration")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["organization_id"] == ORG_ID
    assert summary["paper_balance_usd"] == 10066.67
    assert summary["mean_brier_90d"] == 0.09
    assert summary["total_bets"] == 1
    assert summary["kill_switch_engaged"] is True
    assert summary["paper_pnl_curve"][0]["paper_pnl_usd"] == 66.67
    assert "live-order" not in str(summary)

    assert calibration_response.status_code == 200
    bucket = calibration_response.json()["items"][0]
    assert bucket["bucket"] == 0.7
    assert bucket["empirical_yes_rate"] == 1.0


def test_portfolio_bets_returns_only_paper_bets(client) -> None:
    seed_portfolio(client.app.state.store)

    response = client.get("/v1/portfolio/bets")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["portfolio_paper_bet"]
    assert "portfolio_live_bet" not in str(items)
    assert "external_order_id" not in str(items)
