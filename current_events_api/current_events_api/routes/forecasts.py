"""Public REST routes for Forecasts predictions, markets, and safe bet views."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.schemas import (
    PublicBet,
    PublicForecast,
    PublicForecastSource,
    PublicMarket,
    PublicResolution,
    public_bet,
    public_forecast_from_store,
    public_forecast_source_from_citation,
    public_market,
    public_resolution,
)

from noosphere.models import (
    ForecastBetMode,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
)
from noosphere.forecasts.status import parse_utc_iso, read_status, status_path_from_env
from noosphere.store import Store

router = APIRouter(tags=["forecasts"])

DEFAULT_FORECASTS_INGEST_INTERVAL_S = 900


def _org_filter() -> str | None:
    return (
        os.environ.get("FORECASTS_ORG_ID")
        or os.environ.get("FORECASTS_INGEST_ORG_ID")
        or None
    )


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def forecasts_status_path() -> Path:
    return status_path_from_env()


def forecasts_ingest_interval_seconds() -> float:
    raw = os.environ.get(
        "FORECASTS_INGEST_INTERVAL_S",
        str(DEFAULT_FORECASTS_INGEST_INTERVAL_S),
    )
    try:
        return max(0.001, float(raw))
    except ValueError:
        return float(DEFAULT_FORECASTS_INGEST_INTERVAL_S)


def forecasts_readyz_contract(now: datetime | None = None) -> dict[str, object]:
    """
    Read Forecasts scheduler status and enforce the liveness contract.

    A Forecasts scheduler is stuck when last_ingest_ts is older than
    2 * FORECASTS_INGEST_INTERVAL_S. An engaged kill switch also fails readyz.
    """

    path = forecasts_status_path()
    ingest_interval_s = forecasts_ingest_interval_seconds()
    stuck_after_s = 2.0 * ingest_interval_s
    if not path.is_file():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "code": "forecasts_status_missing",
                "path": str(path),
                "stuck_after_seconds": stuck_after_s,
            },
        )

    try:
        payload = read_status(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "code": "forecasts_status_invalid",
                "path": str(path),
                "error": str(exc),
                "stuck_after_seconds": stuck_after_s,
            },
        ) from exc

    if bool(payload.get("kill_switch_engaged")):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "code": "forecasts_kill_switch_engaged",
                "reason": payload.get("kill_switch_reason"),
                "status": payload,
            },
        )

    last_ingest = parse_utc_iso(payload.get("last_ingest_ts"))
    if last_ingest is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "code": "forecasts_last_ingest_missing",
                "status": payload,
                "stuck_after_seconds": stuck_after_s,
            },
        )

    effective_now = now or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)
    age_s = (effective_now.astimezone(timezone.utc) - last_ingest).total_seconds()
    if age_s > stuck_after_s:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "code": "forecasts_ingest_stuck",
                "age_seconds": round(age_s, 3),
                "stuck_after_seconds": stuck_after_s,
                "ingest_interval_seconds": ingest_interval_s,
                "status": payload,
            },
        )

    return {
        "state": "fresh",
        "age_seconds": round(age_s, 3),
        "stuck_after_seconds": stuck_after_s,
        "ingest_interval_seconds": ingest_interval_s,
        "status": payload,
    }


def _parse_prediction_status(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = value.strip().upper()
    if parsed not in {"PUBLISHED", "RESOLVED"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_status")
    return parsed


def _published_predictions_stmt():
    stmt = select(ForecastPrediction).where(
        ForecastPrediction.status == ForecastPredictionStatus.PUBLISHED.value
    )
    org_id = _org_filter()
    if org_id:
        stmt = stmt.where(ForecastPrediction.organization_id == org_id)
    return stmt


@router.get("/v1/forecasts", dependencies=[Depends(enforce_read_rate_limit)])
def list_forecasts(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    since: datetime | None = None,
    topic: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, list[PublicForecast]]:
    requested_status = _parse_prediction_status(status_filter)
    stmt = _published_predictions_stmt()
    if since is not None:
        stmt = stmt.where(ForecastPrediction.created_at >= since)
    if topic:
        stmt = stmt.where(ForecastPrediction.topic_hint == topic)

    fetch_limit = limit if requested_status is None else max(limit * 5, 50)
    with store.session() as db:
        rows = list(
            db.exec(
                stmt.order_by(desc(ForecastPrediction.created_at)).limit(fetch_limit)
            ).all()
        )
        resolved_ids = set(db.exec(select(ForecastResolution.prediction_id)).all())

    if requested_status == "RESOLVED":
        rows = [row for row in rows if row.id in resolved_ids]
    elif requested_status == "PUBLISHED":
        rows = [row for row in rows if row.id not in resolved_ids]

    metrics.inc("forecasts_read_requests_total", {"route": "list_forecasts"})
    return {"items": [public_forecast_from_store(store, row) for row in rows[:limit]]}


@router.get("/v1/forecasts/{prediction_id}", dependencies=[Depends(enforce_read_rate_limit)])
def get_forecast(
    prediction_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PublicForecast:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
    metrics.inc("forecasts_read_requests_total", {"route": "get_forecast"})
    return public_forecast_from_store(store, prediction)


@router.get(
    "/v1/forecasts/{prediction_id}/sources",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def get_forecast_sources(
    prediction_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> list[PublicForecastSource]:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
    citations = store.list_forecast_citations(prediction_id)
    metrics.inc("forecasts_read_requests_total", {"route": "get_forecast_sources"})
    return [public_forecast_source_from_citation(store, citation) for citation in citations]


@router.get(
    "/v1/forecasts/{prediction_id}/resolution",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def get_forecast_resolution(
    prediction_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PublicResolution:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
    resolution = store.get_forecast_resolution(prediction_id)
    if resolution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_resolution_not_found")
    metrics.inc("forecasts_read_requests_total", {"route": "get_forecast_resolution"})
    public = public_resolution(resolution)
    assert public is not None
    return public


@router.get(
    "/v1/forecasts/{prediction_id}/bets",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def get_forecast_bets(
    prediction_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> list[PublicBet]:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
    bets = [
        bet
        for bet in store.list_bets_for_prediction(prediction_id)
        if _enum_value(bet.mode) == ForecastBetMode.PAPER.value
    ]
    metrics.inc("forecasts_read_requests_total", {"route": "get_forecast_bets"})
    return [public_bet(bet) for bet in bets]


@router.get("/v1/markets/{market_id}", dependencies=[Depends(enforce_read_rate_limit)])
def get_market(
    market_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PublicMarket:
    market = store.get_forecast_market(market_id)
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market_not_found")
    metrics.inc("forecasts_read_requests_total", {"route": "get_market"})
    public = public_market(market)
    assert public is not None
    return public


@router.get("/v1/markets", dependencies=[Depends(enforce_read_rate_limit)])
def list_markets(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    source: str | None = None,
    category: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    since: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, list[PublicMarket]]:
    stmt = select(ForecastMarket)
    org_id = _org_filter()
    if org_id:
        stmt = stmt.where(ForecastMarket.organization_id == org_id)
    if source:
        parsed_source = source.strip().upper()
        if parsed_source not in {item.value for item in ForecastSource}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_source")
        stmt = stmt.where(ForecastMarket.source == parsed_source)
    if category:
        stmt = stmt.where(ForecastMarket.category == category)
    if status_filter:
        parsed_status = status_filter.strip().upper()
        if parsed_status not in {item.value for item in ForecastMarketStatus}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_status")
        stmt = stmt.where(ForecastMarket.status == parsed_status)
    if since is not None:
        stmt = stmt.where(ForecastMarket.updated_at >= since)
    with store.session() as db:
        rows = list(
            db.exec(
                stmt.order_by(desc(ForecastMarket.updated_at)).limit(limit)
            ).all()
        )
    metrics.inc("forecasts_read_requests_total", {"route": "list_markets"})
    return {"items": [item for row in rows if (item := public_market(row)) is not None]}
