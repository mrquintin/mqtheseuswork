"""Public read-only Forecasts portfolio routes."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.schemas import (
    CalibrationBucket,
    PortfolioPoint,
    PortfolioSummary,
    PublicBet,
    public_bet,
)

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastResolution,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])


def _org_filter() -> str | None:
    return (
        os.environ.get("FORECASTS_ORG_ID")
        or os.environ.get("FORECASTS_INGEST_ORG_ID")
        or None
    )


def _organization_id(store: Store) -> str:
    explicit = _org_filter()
    if explicit:
        return explicit
    with store.session() as db:
        state = db.exec(select(ForecastPortfolioState).limit(1)).first()
        if state is not None:
            return state.organization_id
        prediction = db.exec(select(ForecastPrediction).limit(1)).first()
        if prediction is not None:
            return prediction.organization_id
    return "default"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _state_for_org(store: Store, organization_id: str) -> ForecastPortfolioState | None:
    return store.get_portfolio_state(organization_id)


def _paper_bets(
    store: Store,
    organization_id: str,
    *,
    limit: int | None = None,
    offset: int = 0,
    newest_first: bool = False,
) -> list[ForecastBet]:
    with store.session() as db:
        stmt = (
            select(ForecastBet)
            .where(ForecastBet.organization_id == organization_id)
            .where(ForecastBet.mode == ForecastBetMode.PAPER.value)
        )
        order = desc(ForecastBet.created_at) if newest_first else ForecastBet.created_at
        stmt = stmt.order_by(order)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.exec(stmt).all())


def _paper_pnl_curve(
    bets: list[ForecastBet],
    state: ForecastPortfolioState | None,
) -> list[PortfolioPoint]:
    cumulative = 0.0
    points: list[PortfolioPoint] = []
    balance = float(state.paper_balance_usd) if state is not None else 0.0
    for bet in sorted(bets, key=lambda row: row.created_at):
        if bet.settlement_pnl_usd is not None:
            cumulative += float(bet.settlement_pnl_usd)
        points.append(
            PortfolioPoint(
                ts=bet.settled_at or bet.created_at,
                paper_balance_usd=balance,
                paper_pnl_usd=cumulative,
            )
        )
    return points


def _calibration(
    store: Store,
    organization_id: str,
) -> list[CalibrationBucket]:
    buckets: dict[float, list[tuple[ForecastResolution, ForecastPrediction]]] = defaultdict(list)
    with store.session() as db:
        rows = list(
            db.exec(
                select(ForecastResolution, ForecastPrediction)
                .join(
                    ForecastPrediction,
                    ForecastPrediction.id == ForecastResolution.prediction_id,
                )
                .where(ForecastPrediction.organization_id == organization_id)
                .where(ForecastResolution.calibration_bucket.is_not(None))
            ).all()
        )
    for resolution, prediction in rows:
        if resolution.calibration_bucket is None:
            continue
        buckets[float(resolution.calibration_bucket)].append((resolution, prediction))

    out: list[CalibrationBucket] = []
    for bucket, bucket_rows in sorted(buckets.items()):
        resolved = [
            (resolution, prediction)
            for resolution, prediction in bucket_rows
            if _enum_value(resolution.market_outcome) in {"YES", "NO"}
        ]
        yes_count = sum(
            1
            for resolution, _prediction in resolved
            if _enum_value(resolution.market_outcome) == "YES"
        )
        probabilities = [
            float(prediction.probability_yes)
            for _resolution, prediction in resolved
            if prediction.probability_yes is not None
        ]
        briers = [
            float(resolution.brier_score)
            for resolution, _prediction in resolved
            if resolution.brier_score is not None
        ]
        out.append(
            CalibrationBucket(
                bucket=bucket,
                prediction_count=len(bucket_rows),
                resolved_count=len(resolved),
                mean_probability_yes=(
                    sum(probabilities) / len(probabilities) if probabilities else None
                ),
                empirical_yes_rate=yes_count / len(resolved) if resolved else None,
                mean_brier=sum(briers) / len(briers) if briers else None,
            )
        )
    return out


@router.get("", dependencies=[Depends(enforce_read_rate_limit)])
def get_portfolio(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PortfolioSummary:
    organization_id = _organization_id(store)
    state = _state_for_org(store, organization_id)
    bets = _paper_bets(store, organization_id)
    metrics.inc("forecasts_read_requests_total", {"route": "get_portfolio"})
    return PortfolioSummary(
        organization_id=organization_id,
        paper_balance_usd=float(state.paper_balance_usd) if state else 0.0,
        paper_pnl_curve=_paper_pnl_curve(bets, state),
        calibration=_calibration(store, organization_id),
        mean_brier_90d=state.mean_brier_90d if state else None,
        total_bets=len(bets),
        kill_switch_engaged=bool(state.kill_switch_engaged) if state else False,
        kill_switch_reason=state.kill_switch_reason if state else None,
        updated_at=state.updated_at if state else None,
    )


@router.get("/calibration", dependencies=[Depends(enforce_read_rate_limit)])
def get_calibration(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> dict[str, list[CalibrationBucket]]:
    organization_id = _organization_id(store)
    metrics.inc("forecasts_read_requests_total", {"route": "get_calibration"})
    return {"items": _calibration(store, organization_id)}


@router.get("/bets", dependencies=[Depends(enforce_read_rate_limit)])
def list_portfolio_bets(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[PublicBet] | int | None]:
    organization_id = _organization_id(store)
    rows = _paper_bets(
        store,
        organization_id,
        limit=limit + 1,
        offset=offset,
        newest_first=True,
    )
    next_offset = offset + limit if len(rows) > limit else None
    metrics.inc("forecasts_read_requests_total", {"route": "list_portfolio_bets"})
    return {
        "items": [public_bet(row) for row in rows[:limit]],
        "next_offset": next_offset,
    }
