from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from noosphere.models import (
    Conclusion,
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastCitation,
    ForecastExchange,
    ForecastMarket,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastOutcome,
    ForecastSource,
    ForecastSupportLabel,
)
from noosphere.store import Store

ORG_ID = "org_forecasts_api"
MARKET_ID = "forecast_market_api"
PREDICTION_ID = "forecast_prediction_api"
CONCLUSION_ID = "forecast_conclusion_api"
SOURCE_TEXT = "The committee whip count made passage materially more likely."
NOW = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)


def seed_forecast(store: Store, *, resolved: bool = False) -> str:
    store.put_conclusion(Conclusion(id=CONCLUSION_ID, text=SOURCE_TEXT))
    market = ForecastMarket(
        id=MARKET_ID,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="poly_api_001",
        title="Will the policy bill pass before June?",
        description="A binary policy market.",
        resolution_criteria="Resolves YES if the bill passes before 2026-06-01.",
        category="policy",
        current_yes_price=Decimal("0.610000"),
        current_no_price=Decimal("0.390000"),
        volume=Decimal("125000.0000"),
        open_time=NOW - timedelta(days=3),
        close_time=NOW + timedelta(days=20),
        raw_payload={"fixture": True, "source": "polymarket"},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id=PREDICTION_ID,
        market_id=MARKET_ID,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.680000"),
        confidence_low=Decimal("0.570000"),
        confidence_high=Decimal("0.760000"),
        headline="Sources imply passage is more likely than the market price",
        reasoning="The source-citation path mentions forecast_conclusion_api.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="policy",
        model_name="fixture-model",
        prompt_tokens=123,
        completion_tokens=45,
        created_at=NOW,
        updated_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    store.put_forecast_citation(
        ForecastCitation(
            id="forecast_citation_api",
            prediction_id=PREDICTION_ID,
            source_type="CONCLUSION",
            source_id=CONCLUSION_ID,
            quoted_span="passage materially more likely",
            support_label=ForecastSupportLabel.DIRECT,
            retrieval_score=0.91,
            created_at=NOW + timedelta(minutes=1),
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id="forecast_paper_bet_api",
            prediction_id=PREDICTION_ID,
            organization_id=ORG_ID,
            mode=ForecastBetMode.PAPER,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("100.00"),
            entry_price=Decimal("0.610000"),
            status=ForecastBetStatus.FILLED,
            created_at=NOW + timedelta(minutes=2),
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id="forecast_live_bet_api",
            prediction_id=PREDICTION_ID,
            organization_id=ORG_ID,
            mode=ForecastBetMode.LIVE,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("10.00"),
            entry_price=Decimal("0.610000"),
            status=ForecastBetStatus.SUBMITTED,
            external_order_id="external-live-order",
            client_order_id="client-live-order",
            live_authorized_at=NOW,
            created_at=NOW + timedelta(minutes=3),
        )
    )
    if resolved:
        store.put_forecast_resolution(
            ForecastResolution(
                id="forecast_resolution_api",
                prediction_id=PREDICTION_ID,
                market_outcome=ForecastOutcome.YES,
                brier_score=0.1024,
                log_loss=0.385,
                calibration_bucket=Decimal("0.6"),
                resolved_at=NOW + timedelta(days=21),
                justification="Fixture market settled YES.",
                raw_settlement={"fixture": True},
            )
        )
    return PREDICTION_ID


def test_public_forecast_routes_return_schema_and_strip_internal_fields(client) -> None:
    store = client.app.state.store
    seed_forecast(store)

    list_response = client.get("/v1/forecasts", params={"topic": "policy", "limit": 10})
    detail_response = client.get(f"/v1/forecasts/{PREDICTION_ID}")
    sources_response = client.get(f"/v1/forecasts/{PREDICTION_ID}/sources")
    bets_response = client.get(f"/v1/forecasts/{PREDICTION_ID}/bets")
    market_response = client.get(f"/v1/markets/{MARKET_ID}")

    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["id"] == PREDICTION_ID
    assert item["market"]["id"] == MARKET_ID
    assert item["citations"][0]["source_id"] == CONCLUSION_ID
    assert "prompt_tokens" not in item
    assert "completion_tokens" not in item
    assert "external_order_id" not in item

    assert detail_response.status_code == 200
    assert sources_response.status_code == 200
    assert sources_response.json()[0]["source_text"] == SOURCE_TEXT
    assert bets_response.status_code == 200
    assert [bet["mode"] for bet in bets_response.json()] == ["PAPER"]
    assert "external_order_id" not in str(bets_response.json())
    assert market_response.status_code == 200
    assert market_response.json()["raw_payload"]["source"] == "polymarket"


def test_forecast_resolution_open_and_resolved_status_filters(client) -> None:
    store = client.app.state.store
    seed_forecast(store)

    open_resolution = client.get(f"/v1/forecasts/{PREDICTION_ID}/resolution")
    assert open_resolution.status_code == 404
    assert client.get("/v1/forecasts", params={"status": "PUBLISHED"}).json()["items"][0]["id"] == PREDICTION_ID

    store.put_forecast_resolution(
        ForecastResolution(
            id="forecast_resolution_api",
            prediction_id=PREDICTION_ID,
            market_outcome=ForecastOutcome.YES,
            brier_score=0.1024,
            log_loss=0.385,
            calibration_bucket=Decimal("0.6"),
            resolved_at=NOW + timedelta(days=21),
            justification="Fixture market settled YES.",
        )
    )

    resolved_response = client.get(f"/v1/forecasts/{PREDICTION_ID}/resolution")
    resolved_list = client.get("/v1/forecasts", params={"status": "RESOLVED"})
    published_list = client.get("/v1/forecasts", params={"status": "PUBLISHED"})
    assert resolved_response.status_code == 200
    assert resolved_response.json()["market_outcome"] == "YES"
    assert resolved_list.json()["items"][0]["status"] == "RESOLVED"
    assert published_list.json()["items"] == []


def test_forecast_and_market_unknown_ids_404(client) -> None:
    assert client.get("/v1/forecasts/missing").status_code == 404
    assert client.get("/v1/forecasts/missing/sources").status_code == 404
    assert client.get("/v1/forecasts/missing/bets").status_code == 404
    assert client.get("/v1/markets/missing").status_code == 404


def test_markets_list_filters(client) -> None:
    store = client.app.state.store
    seed_forecast(store)

    kept = client.get(
        "/v1/markets",
        params={"source": "POLYMARKET", "category": "policy", "status": "OPEN"},
    ).json()["items"]
    dropped = client.get("/v1/markets", params={"category": "macro"}).json()["items"]

    assert [item["id"] for item in kept] == [MARKET_ID]
    assert dropped == []
