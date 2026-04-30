"""Forecasts Store accessors and shared-table models."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastCitation,
    ForecastExchange,
    ForecastFollowUpMessage,
    ForecastFollowUpRole,
    ForecastFollowUpSession,
    ForecastPortfolioState,
    ForecastResolution,
    ForecastOutcome,
    ForecastSupportLabel,
)


def test_forecasts_seed_round_trips_every_store_helper(forecasts_seed) -> None:
    st = forecasts_seed["store"]
    org_id = forecasts_seed["organization_id"]
    now = forecasts_seed["now"]
    poly_market, kalshi_market = forecasts_seed["markets"]
    poly_prediction, kalshi_prediction = forecasts_seed["predictions"]

    loaded_poly_market = st.get_forecast_market(poly_market.id)
    assert loaded_poly_market is not None
    assert loaded_poly_market.source == poly_market.source
    assert loaded_poly_market.external_id == "poly_001"
    assert loaded_poly_market.raw_payload["source"] == "polymarket"

    duplicate_market = poly_market.model_copy(
        update={"id": "forecast_market_poly_duplicate", "title": "Updated title"}
    )
    assert st.put_forecast_market(duplicate_market) == poly_market.id
    assert st.get_forecast_market(poly_market.id).title == "Updated title"  # type: ignore[union-attr]

    open_market_ids = {m.id for m in st.list_open_forecast_markets(organization_id=org_id)}
    assert open_market_ids == {poly_market.id, kalshi_market.id}

    assert st.get_forecast_prediction(poly_prediction.id).market_id == poly_market.id  # type: ignore[union-attr]
    assert [
        p.id for p in st.list_recent_forecast_predictions(since=now - timedelta(days=1), limit=10)
    ] == [kalshi_prediction.id, poly_prediction.id]

    citation = ForecastCitation(
        id="forecast_citation_poly",
        prediction_id=poly_prediction.id,
        source_type="CONCLUSION",
        source_id="conclusion_1",
        quoted_span="passage is more likely",
        support_label=ForecastSupportLabel.DIRECT,
        retrieval_score=0.91,
        created_at=now + timedelta(minutes=4),
    )
    assert st.put_forecast_citation(citation) == citation.id
    assert [c.id for c in st.list_forecast_citations(poly_prediction.id)] == [citation.id]

    assert [p.id for p in st.get_unresolved_predictions_for_market(poly_market.id)] == [
        poly_prediction.id
    ]
    resolution = ForecastResolution(
        id="forecast_resolution_poly",
        prediction_id=poly_prediction.id,
        market_outcome=ForecastOutcome.YES,
        brier_score=0.1024,
        log_loss=0.385,
        calibration_bucket=Decimal("0.6"),
        resolved_at=now + timedelta(days=21),
        justification="Fixture market settled YES.",
        raw_settlement={"fixture": True},
    )
    assert st.put_forecast_resolution(resolution) == resolution.id
    duplicate_resolution = resolution.model_copy(update={"id": "forecast_resolution_poly_second"})
    assert st.put_forecast_resolution(duplicate_resolution) == resolution.id
    assert st.get_forecast_resolution(poly_prediction.id).market_outcome == ForecastOutcome.YES  # type: ignore[union-attr]
    assert st.get_unresolved_predictions_for_market(poly_market.id) == []

    assert [b.id for b in st.list_bets_for_prediction(poly_prediction.id)] == [
        "forecast_bet_poly_yes"
    ]
    live_bet = ForecastBet(
        id="forecast_live_without_auth",
        prediction_id=poly_prediction.id,
        organization_id=org_id,
        mode=ForecastBetMode.LIVE,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("10.00"),
        entry_price=Decimal("0.610000"),
        status=ForecastBetStatus.PENDING,
    )
    with pytest.raises(ValueError, match="live_authorized_at"):
        st.put_forecast_bet(live_bet)

    portfolio = ForecastPortfolioState(
        id="forecast_portfolio",
        organization_id=org_id,
        paper_balance_usd=Decimal("10000.00"),
        live_balance_usd=None,
        daily_loss_usd=Decimal("0.00"),
        daily_loss_reset_at=now,
        mean_brier_90d=0.1024,
    )
    assert st.set_portfolio_state(portfolio) == portfolio.id
    updated_portfolio = portfolio.model_copy(
        update={"id": "forecast_portfolio_duplicate", "paper_balance_usd": Decimal("10125.50")}
    )
    assert st.set_portfolio_state(updated_portfolio) == portfolio.id
    assert st.get_portfolio_state(org_id).paper_balance_usd == Decimal("10125.50")  # type: ignore[union-attr]

    session = ForecastFollowUpSession(
        id="forecast_followup_session",
        prediction_id=poly_prediction.id,
        client_fingerprint="forecast-fingerprint",
        created_at=now + timedelta(minutes=5),
        last_activity_at=now + timedelta(minutes=5),
    )
    assert st.add_forecast_followup_session(session) == session.id
    assert st.get_forecast_followup_session(session.id).prediction_id == poly_prediction.id  # type: ignore[union-attr]

    message = ForecastFollowUpMessage(
        id="forecast_followup_message",
        session_id=session.id,
        role=ForecastFollowUpRole.USER,
        content="Which source drove the probability?",
        citations=[{"source_type": "CONCLUSION", "source_id": "conclusion_1"}],
        created_at=now + timedelta(minutes=6),
    )
    assert st.add_forecast_followup_message(message) == message.id
    assert st.get_forecast_followup_message(message.id).citations == message.citations  # type: ignore[union-attr]
    assert st.get_forecast_followup_session(session.id).last_activity_at == message.created_at  # type: ignore[union-attr]
