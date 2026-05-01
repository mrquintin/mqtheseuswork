"""Public read-only Forecasts portfolio routes."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.schemas import (
    CalibrationBucket,
    GateBannerState,
    PipelineCandidate,
    PortfolioPosition,
    PortfolioPoint,
    PortfolioSurface,
    PortfolioSummary,
    PublicBet,
    ResolvedPortfolioPosition,
    TraceGateResult,
    WatchingSummary,
    public_bet,
    public_watched_market,
)

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastMarket,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastResolution,
    ForecastTrace,
    WatchedMarket,
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


def _csv_env(name: str) -> list[str]:
    return [part.strip() for part in os.getenv(name, "").split(",") if part.strip()]


def _live_enabled() -> bool:
    return os.getenv("FORECASTS_LIVE_TRADING_ENABLED", "").strip().lower() == "true"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: object) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _market_url(market: object | None) -> str | None:
    if market is None:
        return None
    raw_payload = getattr(market, "raw_payload", None)
    if isinstance(raw_payload, dict):
        for key in ("url", "market_url", "source_url"):
            value = raw_payload.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    source = _enum_value(getattr(market, "source", ""))
    external_id = str(getattr(market, "external_id", "") or "")
    if not external_id:
        return None
    if source == "POLYMARKET":
        return f"https://polymarket.com/event/{external_id}"
    if source == "KALSHI":
        return f"https://kalshi.com/markets/{external_id}"
    return None


def _trace_for_prediction(db, prediction_id: str) -> ForecastTrace | None:
    return db.exec(
        select(ForecastTrace).where(ForecastTrace.prediction_id == prediction_id)
    ).first()


def _trace_principles(trace: ForecastTrace | None) -> list[dict[str, object]]:
    if trace is None or not isinstance(trace.principles_used, list):
        return []
    return [item for item in trace.principles_used if isinstance(item, dict)]


def _trace_gates(trace: ForecastTrace | None) -> list[TraceGateResult]:
    if trace is None or not isinstance(trace.gate_results, list):
        return []
    out: list[TraceGateResult] = []
    for item in trace.gate_results:
        if not isinstance(item, dict):
            continue
        gate_name = str(item.get("gateName") or item.get("gate_name") or "")
        if not gate_name:
            continue
        out.append(
            TraceGateResult(
                gate_name=gate_name,
                passed=bool(item.get("passed")),
                reason=str(item.get("reason") or ""),
            )
        )
    return out


def _principle_models(trace: ForecastTrace | None):
    from current_events_api.schemas import _trace_principles as to_models

    return to_models(_trace_principles(trace))


def _current_prob_for_side(market: object | None, side: str) -> float | None:
    if market is None:
        return None
    if side == "NO":
        return _float_or_none(getattr(market, "current_no_price", None))
    return _float_or_none(getattr(market, "current_yes_price", None))


def _gate_state(gates: list[TraceGateResult]) -> str:
    failed = [gate for gate in gates if not gate.passed]
    if failed:
        return f"would fail {failed[0].gate_name}: {failed[0].reason}"
    return "paper-ready"


def _banner_state(state: ForecastPortfolioState | None) -> GateBannerState:
    if not _live_enabled():
        return GateBannerState(
            mode="PAPER",
            live_trading_enabled=False,
            failed_gates=[],
        )
    failed: list[TraceGateResult] = []
    if state is not None and state.kill_switch_engaged:
        failed.append(
            TraceGateResult(
                gate_name="kill_switch_clear",
                passed=False,
                reason=state.kill_switch_reason or "portfolio kill switch is engaged",
            )
        )
    if not (os.getenv("POLYMARKET_PRIVATE_KEY", "").strip() or os.getenv("KALSHI_API_KEY_ID", "").strip()):
        failed.append(
            TraceGateResult(
                gate_name="exchange_credentials_configured",
                passed=False,
                reason="no live exchange credentials are configured",
            )
        )
    return GateBannerState(
        mode="GATE-BLOCKED" if failed else "LIVE",
        live_trading_enabled=True,
        failed_gates=failed,
    )


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


def _surface_open_positions(store: Store, organization_id: str) -> list[PortfolioPosition]:
    open_statuses = {
        ForecastBetStatus.PENDING.value,
        ForecastBetStatus.AUTHORIZED.value,
        ForecastBetStatus.CONFIRMED.value,
        ForecastBetStatus.SUBMITTED.value,
        ForecastBetStatus.FILLED.value,
    }
    with store.session() as db:
        bets = list(
            db.exec(
                select(ForecastBet)
                .where(ForecastBet.organization_id == organization_id)
                .where(ForecastBet.status.in_(open_statuses))
                .order_by(desc(ForecastBet.created_at))
                .limit(100)
            ).all()
        )
        out: list[PortfolioPosition] = []
        for bet in bets:
            prediction = db.get(ForecastPrediction, bet.prediction_id)
            if prediction is None:
                continue
            market = db.get(ForecastMarket, prediction.market_id)
            trace = _trace_for_prediction(db, prediction.id)
            side = _enum_value(bet.side)
            out.append(
                PortfolioPosition(
                    bet_id=bet.id,
                    prediction_id=prediction.id,
                    mode=_enum_value(bet.mode),
                    market_title=market.title if market is not None else trace.market_title if trace else prediction.headline,
                    market_url=_market_url(market),
                    side=side,
                    size_usd=_money(bet.stake_usd),
                    avg_price=_money(bet.entry_price),
                    current_implied_prob=_current_prob_for_side(market, side),
                    driving_principles=_principle_models(trace),
                    gate_results=_trace_gates(trace),
                    last_updated=prediction.updated_at,
                )
            )
        return out


def _surface_recently_resolved(store: Store, organization_id: str) -> list[ResolvedPortfolioPosition]:
    with store.session() as db:
        bets = list(
            db.exec(
                select(ForecastBet)
                .where(ForecastBet.organization_id == organization_id)
                .where(ForecastBet.status == ForecastBetStatus.SETTLED.value)
                .order_by(desc(ForecastBet.settled_at))
                .limit(50)
            ).all()
        )
        out: list[ResolvedPortfolioPosition] = []
        for bet in bets:
            prediction = db.get(ForecastPrediction, bet.prediction_id)
            if prediction is None:
                continue
            market = db.get(ForecastMarket, prediction.market_id)
            resolution = db.exec(
                select(ForecastResolution).where(
                    ForecastResolution.prediction_id == prediction.id
                )
            ).first()
            out.append(
                ResolvedPortfolioPosition(
                    bet_id=bet.id,
                    prediction_id=prediction.id,
                    market_title=market.title if market is not None else prediction.headline,
                    market_url=_market_url(market),
                    outcome=_enum_value(resolution.market_outcome) if resolution is not None else "UNKNOWN",
                    our_side=_enum_value(bet.side),
                    pnl_usd=_float_or_none(bet.settlement_pnl_usd),
                    reasoning_href=f"/forecasts/{prediction.id}",
                    resolved_at=resolution.resolved_at if resolution is not None else bet.settled_at,
                )
            )
        return out


def _surface_pipeline(store: Store, organization_id: str) -> list[PipelineCandidate]:
    with store.session() as db:
        rows = list(
            db.exec(
                select(ForecastMarket)
                .where(ForecastMarket.organization_id == organization_id)
                .where(ForecastMarket.status == "OPEN")
                .order_by(desc(ForecastMarket.updated_at))
                .limit(25)
            ).all()
        )
        out: list[PipelineCandidate] = []
        for market in rows:
            prediction = db.exec(
                select(ForecastPrediction)
                .where(ForecastPrediction.market_id == market.id)
                .order_by(desc(ForecastPrediction.created_at))
                .limit(1)
            ).first()
            trace = _trace_for_prediction(db, prediction.id) if prediction else None
            gates = _trace_gates(trace)
            if not gates:
                gates = [
                    TraceGateResult(
                        gate_name="retrieval_queue",
                        passed=True,
                        reason="awaiting the next forecast generator cycle",
                    )
                ]
            out.append(
                PipelineCandidate(
                    market_id=market.id,
                    market_title=market.title,
                    market_url=_market_url(market),
                    source=_enum_value(market.source),
                    category=market.category,
                    driving_principles=_principle_models(trace),
                    gate_results=gates,
                    gate_state=_gate_state(gates),
                    last_updated=market.updated_at,
                )
            )
        return out


def _surface_watching(store: Store, organization_id: str) -> WatchingSummary:
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    with store.session() as db:
        scanned = db.exec(
            select(ForecastMarket).where(ForecastMarket.updated_at >= week_ago)
        ).all()
        watched = list(
            db.exec(
                select(WatchedMarket)
                .where(WatchedMarket.organization_id == organization_id)
                .order_by(desc(WatchedMarket.created_at))
                .limit(50)
            ).all()
        )
    return WatchingSummary(
        polymarket_categories=_csv_env("FORECASTS_POLYMARKET_CATEGORIES"),
        kalshi_categories=_csv_env("FORECASTS_KALSHI_CATEGORIES"),
        watched_markets=[public_watched_market(row) for row in watched],
        scanned_this_week=len(scanned),
    )


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


@router.get("/surface", dependencies=[Depends(enforce_read_rate_limit)])
def get_portfolio_surface(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PortfolioSurface:
    organization_id = _organization_id(store)
    state = _state_for_org(store, organization_id)
    bets = _paper_bets(store, organization_id)
    summary = PortfolioSummary(
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
    metrics.inc("forecasts_read_requests_total", {"route": "get_portfolio_surface"})
    return PortfolioSurface(
        summary=summary,
        gate_banner=_banner_state(state),
        open_positions=_surface_open_positions(store, organization_id),
        recently_resolved=_surface_recently_resolved(store, organization_id),
        pipeline=_surface_pipeline(store, organization_id),
        watching=_surface_watching(store, organization_id),
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
