from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import select

from noosphere.forecasts.resolution_tracker import poll_market
from noosphere.models import (
    ForecastMarket,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
)
from noosphere.store import Store


NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
ORG_ID = "org_resolution_tests"


class _FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[str] = []

    async def get_market(self, external_id: str) -> dict[str, Any]:
        self.requests.append(external_id)
        return self.payload


def test_resolves_yes_outcome() -> None:
    store = _store()
    market = _seed_market(store)
    prediction = _seed_prediction(store, market, "p_yes", Decimal("0.700000"))

    result = asyncio.run(
        poll_market(store, market.id, polymarket_client=_FakeClient(_yes_payload()))
    )

    assert result.outcome == "YES"
    assert result.resolved_predictions == 1
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.YES
    assert resolution.brier_score == _approx(0.09)
    assert resolution.log_loss == _approx(-math.log(0.7))
    assert resolution.calibration_bucket == Decimal("0.7")


def test_resolves_no_outcome() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_no")
    prediction = _seed_prediction(store, market, "p_no", Decimal("0.700000"))

    result = asyncio.run(
        poll_market(store, market.id, polymarket_client=_FakeClient(_no_payload()))
    )

    assert result.outcome == "NO"
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.NO
    assert resolution.brier_score == _approx(0.49)
    assert resolution.log_loss == _approx(-math.log(0.3))
    assert resolution.calibration_bucket == Decimal("0.7")


def test_handles_cancelled_market() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_cancelled")
    prediction = _seed_prediction(store, market, "p_cancelled", Decimal("0.700000"))
    initial_state = ForecastPortfolioState(
        organization_id=ORG_ID,
        paper_balance_usd=Decimal("10000.00"),
        daily_loss_usd=Decimal("0.00"),
        daily_loss_reset_at=NOW,
        mean_brier_90d=0.25,
        mean_log_loss_90d=0.75,
        total_resolved=3,
    )
    store.set_portfolio_state(initial_state)

    result = asyncio.run(
        poll_market(
            store,
            market.id,
            polymarket_client=_FakeClient(
                {
                    "conditionId": "poly_cancelled",
                    "status": "cancelled",
                    "resolvedAt": NOW.isoformat(),
                }
            ),
        )
    )

    assert result.outcome == "CANCELLED"
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.CANCELLED
    assert resolution.brier_score is None
    assert resolution.log_loss is None
    assert resolution.calibration_bucket is None
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.mean_brier_90d == 0.25
    assert state.mean_log_loss_90d == 0.75
    assert state.total_resolved == 3


def test_idempotent_repolling() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_idempotent")
    prediction = _seed_prediction(store, market, "p_idempotent", Decimal("0.700000"))
    client = _FakeClient(_yes_payload())

    first = asyncio.run(poll_market(store, market.id, polymarket_client=client))
    second = asyncio.run(poll_market(store, market.id, polymarket_client=client))

    assert first.resolved_predictions == 1
    assert second.resolved_predictions == 0
    with store.session() as session:
        rows = session.exec(select(ForecastResolution)).all()
    assert [row.prediction_id for row in rows] == [prediction.id]

    duplicate = ForecastResolution(
        id="duplicate_resolution",
        prediction_id=prediction.id,
        market_outcome=ForecastOutcome.NO,
        resolved_at=NOW,
        justification="Attempted duplicate append.",
    )
    assert store.put_forecast_resolution(duplicate) != duplicate.id
    assert store.get_forecast_resolution(prediction.id).market_outcome == ForecastOutcome.YES  # type: ignore[union-attr]


def test_still_open_no_op() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_open")
    prediction = _seed_prediction(store, market, "p_open", Decimal("0.700000"))

    result = asyncio.run(
        poll_market(
            store,
            market.id,
            polymarket_client=_FakeClient({"conditionId": "poly_open", "active": True}),
        )
    )

    assert result.outcome == "STILL_OPEN"
    assert result.resolved_predictions == 0
    assert store.get_forecast_resolution(prediction.id) is None


def test_aggregate_metrics() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_aggregate")
    probabilities = [
        Decimal("0.100000"),
        Decimal("0.300000"),
        Decimal("0.500000"),
        Decimal("0.700000"),
        Decimal("0.900000"),
    ]
    for idx, probability in enumerate(probabilities):
        _seed_prediction(store, market, f"p_agg_{idx}", probability)

    result = asyncio.run(
        poll_market(store, market.id, polymarket_client=_FakeClient(_yes_payload()))
    )

    assert result.resolved_predictions == 5
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    expected_brier = sum((float(p) - 1.0) ** 2 for p in probabilities) / len(probabilities)
    expected_log_loss = sum(-math.log(float(p)) for p in probabilities) / len(probabilities)
    assert state.mean_brier_90d == _approx(expected_brier)
    assert state.mean_log_loss_90d == _approx(expected_log_loss)
    assert state.total_resolved == 5


def test_calibration_bucket_assignment() -> None:
    store = _store()
    market = _seed_market(store, external_id="poly_buckets")
    for prediction_id, probability in [
        ("p_bucket_005", Decimal("0.050000")),
        ("p_bucket_045", Decimal("0.450000")),
        ("p_bucket_095", Decimal("0.950000")),
    ]:
        _seed_prediction(store, market, prediction_id, probability)

    asyncio.run(poll_market(store, market.id, polymarket_client=_FakeClient(_yes_payload())))

    with store.session() as session:
        rows = session.exec(
            select(ForecastResolution).order_by(ForecastResolution.prediction_id)
        ).all()
    assert [row.calibration_bucket for row in rows] == [
        Decimal("0.0"),
        Decimal("0.4"),
        Decimal("0.9"),
    ]


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_market(
    store: Store,
    *,
    external_id: str = "poly_yes",
) -> ForecastMarket:
    market = ForecastMarket(
        id=f"market_{external_id}",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=external_id,
        title=f"Fixture market {external_id}",
        description="Fixture binary market.",
        resolution_criteria="Resolves against a fixture payload.",
        current_yes_price=Decimal("0.500000"),
        current_no_price=Decimal("0.500000"),
        open_time=NOW - timedelta(days=7),
        close_time=NOW - timedelta(hours=1),
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    return market


def _seed_prediction(
    store: Store,
    market: ForecastMarket,
    prediction_id: str,
    probability_yes: Decimal,
) -> ForecastPrediction:
    prediction = ForecastPrediction(
        id=prediction_id,
        market_id=market.id,
        organization_id=market.organization_id,
        probability_yes=probability_yes,
        confidence_low=max(Decimal("0"), probability_yes - Decimal("0.100000")),
        confidence_high=min(Decimal("1"), probability_yes + Decimal("0.100000")),
        headline=f"Fixture forecast {prediction_id}",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="fixture",
        model_name="fixture-model",
        created_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    return prediction


def _yes_payload() -> dict[str, Any]:
    return {
        "conditionId": "poly_yes",
        "result": "YES",
        "resolvedAt": NOW.isoformat(),
    }


def _no_payload() -> dict[str, Any]:
    return {
        "conditionId": "poly_no",
        "result": "NO",
        "resolvedAt": NOW.isoformat(),
    }


def _approx(value: float) -> float:
    return pytest.approx(value, rel=1e-12, abs=1e-12)
