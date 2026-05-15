"""Unified decision-trace endpoint.

Returns the full audit chain (principle → signal → position → fill →
resolution) for either a ForecastBet (prediction market) or an
EquityPosition (cash equity). The id prefix is used to dispatch:

* ``b_…`` / forecast-shaped ids → ForecastBet branch
* ``pos_…`` / equity-shaped ids → EquityPosition branch
* an explicit ``?type=forecast|equity`` query param overrides

The response carries citations at every link so the founder's
"continuity all the way through" rendering on the unified portfolio
page never has to fan out to other endpoints to fill in trace gaps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.routes.portfolio import (
    _decimal_to_float,
    _enum_value,
    _trace_for_prediction,
    _trace_principles,
    _trace_gates,
)
from current_events_api.schemas import TraceGateResult

from noosphere.models import (
    EquityInstrument,
    EquityPosition,
    EquitySignal,
    EquitySignalCitation,
    ForecastBet,
    ForecastCitation,
    ForecastMarket,
    ForecastPrediction,
    ForecastResolution,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])

TraceKind = Literal["forecast", "equity"]


class TracePrincipleRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion_id: str
    snippet: str
    weight: float | None = None


class TraceCitationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    quoted_span: str
    support_label: str | None = None


class TraceSignalRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    headline: str
    direction_or_side: str
    rationale: str | None = None
    confidence_low: float | None = None
    confidence_high: float | None = None


class TracePositionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: str
    side: str
    size: float
    entry_price: float
    status: str
    created_at: datetime


class TraceFillRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_price: float | None = None
    exit_at: datetime | None = None
    realized_pnl_usd: float | None = None


class TraceResolutionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str | None = None
    resolved_at: datetime | None = None
    brier_score: float | None = None
    justification: str | None = None


class DecisionTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TraceKind
    position_id: str
    market_or_instrument_title: str
    principles: list[TracePrincipleRow]
    citations: list[TraceCitationRow]
    signal: TraceSignalRow | None = None
    position: TracePositionRow
    fill: TraceFillRow | None = None
    resolution: TraceResolutionRow | None = None
    gates: list[TraceGateResult]


def _forecast_trace(store: Store, bet_id: str) -> DecisionTraceResponse | None:
    with store.session() as db:
        bet = db.get(ForecastBet, bet_id)
        if bet is None:
            return None
        prediction = db.get(ForecastPrediction, bet.prediction_id)
        if prediction is None:
            return None
        market = db.get(ForecastMarket, prediction.market_id)
        trace = _trace_for_prediction(db, prediction.id)
        principles = [
            TracePrincipleRow(
                conclusion_id=str(p.get("conclusionId") or p.get("conclusion_id") or ""),
                snippet=str(p.get("snippet") or ""),
                weight=(
                    float(p.get("weight")) if p.get("weight") is not None else None
                ),
            )
            for p in _trace_principles(trace)
        ]
        citations = list(
            db.exec(
                select(ForecastCitation).where(
                    ForecastCitation.prediction_id == prediction.id
                )
            ).all()
        )
        citation_rows = [
            TraceCitationRow(
                source_type=str(c.source_type),
                source_id=str(c.source_id),
                quoted_span=str(c.quoted_span),
                support_label=_enum_value(c.support_label),
            )
            for c in citations
        ]
        signal_row = TraceSignalRow(
            id=prediction.id,
            headline=prediction.headline,
            direction_or_side=_enum_value(bet.side) or "YES",
            rationale=prediction.reasoning,
            confidence_low=_decimal_to_float(prediction.confidence_low)
            if prediction.confidence_low is not None
            else None,
            confidence_high=_decimal_to_float(prediction.confidence_high)
            if prediction.confidence_high is not None
            else None,
        )
        position_row = TracePositionRow(
            id=bet.id,
            mode=_enum_value(bet.mode) or "PAPER",
            side=_enum_value(bet.side) or "YES",
            size=_decimal_to_float(bet.stake_usd),
            entry_price=_decimal_to_float(bet.entry_price),
            status=_enum_value(bet.status) or "PENDING",
            created_at=bet.created_at,
        )
        fill_row = TraceFillRow(
            exit_price=_decimal_to_float(bet.exit_price)
            if bet.exit_price is not None
            else None,
            exit_at=bet.settled_at,
            realized_pnl_usd=_decimal_to_float(bet.settlement_pnl_usd)
            if bet.settlement_pnl_usd is not None
            else None,
        )
        resolution = db.exec(
            select(ForecastResolution).where(
                ForecastResolution.prediction_id == prediction.id
            )
        ).first()
        resolution_row = (
            TraceResolutionRow(
                outcome=_enum_value(resolution.market_outcome),
                resolved_at=resolution.resolved_at,
                brier_score=(
                    float(resolution.brier_score)
                    if resolution.brier_score is not None
                    else None
                ),
                justification=resolution.justification,
            )
            if resolution is not None
            else None
        )
        return DecisionTraceResponse(
            kind="forecast",
            position_id=bet.id,
            market_or_instrument_title=(
                market.title if market is not None else prediction.headline
            ),
            principles=principles,
            citations=citation_rows,
            signal=signal_row,
            position=position_row,
            fill=fill_row,
            resolution=resolution_row,
            gates=_trace_gates(trace),
        )


def _equity_trace(store: Store, position_id: str) -> DecisionTraceResponse | None:
    with store.session() as db:
        position = db.get(EquityPosition, position_id)
        if position is None:
            return None
        signal = db.get(EquitySignal, position.signal_id)
        instrument = db.get(EquityInstrument, position.instrument_id)
        citations = list(
            db.exec(
                select(EquitySignalCitation).where(
                    EquitySignalCitation.signal_id == position.signal_id
                )
            ).all()
        )
        citation_rows = [
            TraceCitationRow(
                source_type=str(c.source_type),
                source_id=str(c.source_id),
                quoted_span=str(c.quoted_span),
                support_label=_enum_value(c.support_label),
            )
            for c in citations
        ]
        signal_row = (
            TraceSignalRow(
                id=signal.id,
                headline=signal.headline,
                direction_or_side=_enum_value(signal.direction) or "NEUTRAL",
                rationale=signal.reasoning,
                confidence_low=_decimal_to_float(signal.confidence_low),
                confidence_high=_decimal_to_float(signal.confidence_high),
            )
            if signal is not None
            else None
        )
        position_row = TracePositionRow(
            id=position.id,
            mode=_enum_value(position.mode) or "PAPER",
            side=_enum_value(position.side) or "LONG",
            size=_decimal_to_float(position.qty),
            entry_price=_decimal_to_float(position.entry_price),
            status=_enum_value(position.status) or "PENDING",
            created_at=position.created_at,
        )
        fill_row = TraceFillRow(
            exit_price=_decimal_to_float(position.exit_price)
            if position.exit_price is not None
            else None,
            exit_at=position.exit_at,
            realized_pnl_usd=_decimal_to_float(position.realized_pnl_usd)
            if position.realized_pnl_usd is not None
            else None,
        )
        title = instrument.symbol if instrument is not None else position.instrument_id
        return DecisionTraceResponse(
            kind="equity",
            position_id=position.id,
            market_or_instrument_title=title,
            # Equity signals don't yet ship structured trace principles —
            # the principle chain lives in the signal citations.
            principles=[],
            citations=citation_rows,
            signal=signal_row,
            position=position_row,
            fill=fill_row,
            resolution=None,
            gates=[],
        )


def _looks_like_equity(position_id: str) -> bool:
    pid = position_id.lower()
    return pid.startswith("pos_") or pid.startswith("eq_")


@router.get(
    "/decision-trace/{position_id}", dependencies=[Depends(enforce_read_rate_limit)]
)
def get_decision_trace(
    position_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    type: TraceKind | None = Query(default=None),
) -> DecisionTraceResponse:
    chosen: TraceKind | None = type
    if chosen is None:
        chosen = "equity" if _looks_like_equity(position_id) else "forecast"
    metrics.inc(
        "forecasts_read_requests_total",
        {"route": "get_decision_trace", "kind": chosen},
    )
    if chosen == "forecast":
        trace = _forecast_trace(store, position_id) or _equity_trace(store, position_id)
    else:
        trace = _equity_trace(store, position_id) or _forecast_trace(store, position_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="position not found")
    return trace
