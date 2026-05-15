"""Public read-only equity-portfolio surface.

Mirrors the prediction-market portfolio route under a sibling prefix:
the unified `/portfolio` page renders both surfaces side by side and
shares the same audit / authorization language across both. Public
callers only ever see PAPER rows — live rows live behind the operator
console.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.routes.portfolio import (
    LiveStatusPills,
    TrackTotals,
    _decimal_to_float,
    _enum_value,
    _equity_paper_positions,
    _equity_track_totals,
    _organization_id,
    live_status_pills,
)

from noosphere.models import (
    EquityInstrument,
    EquityPortfolioState,
    EquityPosition,
    EquityPositionMode,
    EquityPositionStatus,
    EquitySignal,
    EquitySignalDirection,
    EquitySignalStatus,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])


class EquityOpenPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str
    signal_id: str
    instrument_symbol: str
    instrument_name: str | None = None
    side: str
    qty: float
    entry_price: float
    entry_at: datetime
    unrealized_pnl_usd: float | None = None
    horizon_days: int | None = None
    direction: str
    last_updated: datetime


class EquityRecentSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    instrument_symbol: str
    direction: str
    headline: str
    confidence_low: float
    confidence_high: float
    target_price_low: float | None = None
    target_price_high: float | None = None
    horizon_days: int
    status: str
    created_at: datetime


class EquityCurvePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime
    paper_pnl_usd: float


class MapeBucket(BaseModel):
    """Target-price MAPE for resolved signals, bucketed by horizon."""

    model_config = ConfigDict(extra="forbid")

    horizon_label: str
    n: int
    mean_absolute_pct_error: float | None = None


class EquityPortfolioSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str
    paper_balance_usd: float
    totals: TrackTotals
    live_status: LiveStatusPills
    kill_switch_engaged: bool
    kill_switch_reason: str | None = None
    open_positions: list[EquityOpenPosition]
    recent_signals: list[EquityRecentSignal]
    paper_pnl_curve: list[EquityCurvePoint]
    target_price_mape: list[MapeBucket]


def _instrument(db, instrument_id: str) -> EquityInstrument | None:
    return db.get(EquityInstrument, instrument_id)


def _signal(db, signal_id: str) -> EquitySignal | None:
    return db.get(EquitySignal, signal_id)


def _open_positions(
    store: Store, positions: list[EquityPosition]
) -> list[EquityOpenPosition]:
    open_statuses = {
        EquityPositionStatus.OPEN.value,
        EquityPositionStatus.PENDING.value,
    }
    out: list[EquityOpenPosition] = []
    with store.session() as db:
        for position in positions:
            if _enum_value(position.status) not in open_statuses:
                continue
            instrument = _instrument(db, position.instrument_id)
            signal = _signal(db, position.signal_id)
            out.append(
                EquityOpenPosition(
                    position_id=position.id,
                    signal_id=position.signal_id,
                    instrument_symbol=instrument.symbol if instrument else "?",
                    instrument_name=instrument.name if instrument else None,
                    side=_enum_value(position.side) or "LONG",
                    qty=_decimal_to_float(position.qty),
                    entry_price=_decimal_to_float(position.entry_price),
                    entry_at=position.entry_at,
                    unrealized_pnl_usd=(
                        _decimal_to_float(position.unrealized_pnl_usd)
                        if position.unrealized_pnl_usd is not None
                        else None
                    ),
                    horizon_days=signal.horizon_days if signal else None,
                    direction=_enum_value(signal.direction) if signal else "NEUTRAL",
                    last_updated=position.updated_at,
                )
            )
    return out


def _recent_signals(store: Store, organization_id: str) -> list[EquityRecentSignal]:
    out: list[EquityRecentSignal] = []
    with store.session() as db:
        rows = list(
            db.exec(
                select(EquitySignal)
                .where(EquitySignal.organization_id == organization_id)
                .order_by(desc(EquitySignal.created_at))
                .limit(25)
            ).all()
        )
        for signal in rows:
            instrument = _instrument(db, signal.instrument_id)
            out.append(
                EquityRecentSignal(
                    signal_id=signal.id,
                    instrument_symbol=instrument.symbol if instrument else "?",
                    direction=_enum_value(signal.direction) or "NEUTRAL",
                    headline=signal.headline,
                    confidence_low=_decimal_to_float(signal.confidence_low),
                    confidence_high=_decimal_to_float(signal.confidence_high),
                    target_price_low=(
                        _decimal_to_float(signal.target_price_low)
                        if signal.target_price_low is not None
                        else None
                    ),
                    target_price_high=(
                        _decimal_to_float(signal.target_price_high)
                        if signal.target_price_high is not None
                        else None
                    ),
                    horizon_days=int(signal.horizon_days),
                    status=_enum_value(signal.status) or "PUBLISHED",
                    created_at=signal.created_at,
                )
            )
    return out


def _paper_curve(positions: list[EquityPosition]) -> list[EquityCurvePoint]:
    settled = [
        p
        for p in positions
        if _enum_value(p.status) == EquityPositionStatus.CLOSED.value
        and p.exit_at is not None
        and p.realized_pnl_usd is not None
    ]
    settled.sort(key=lambda p: p.exit_at or datetime.min.replace(tzinfo=timezone.utc))
    out: list[EquityCurvePoint] = []
    cumulative = 0.0
    for p in settled:
        cumulative += _decimal_to_float(p.realized_pnl_usd)
        out.append(EquityCurvePoint(ts=p.exit_at, paper_pnl_usd=cumulative))  # type: ignore[arg-type]
    return out


HORIZONS: list[tuple[str, int, int | None]] = [
    ("≤ 7 days", 0, 7),
    ("8–30 days", 8, 30),
    ("31–90 days", 31, 90),
    ("> 90 days", 91, None),
]


def _target_price_mape(
    store: Store, positions: list[EquityPosition]
) -> list[MapeBucket]:
    by_bucket: dict[str, list[float]] = {label: [] for label, *_ in HORIZONS}
    with store.session() as db:
        for position in positions:
            if (
                _enum_value(position.status) != EquityPositionStatus.CLOSED.value
                or position.exit_price is None
            ):
                continue
            signal = _signal(db, position.signal_id)
            if signal is None:
                continue
            low = signal.target_price_low
            high = signal.target_price_high
            if low is None or high is None:
                continue
            target = (_decimal_to_float(low) + _decimal_to_float(high)) / 2.0
            actual = _decimal_to_float(position.exit_price)
            if target == 0:
                continue
            ape = abs(actual - target) / abs(target)
            for label, lo, hi in HORIZONS:
                horizon = int(signal.horizon_days)
                if horizon < lo:
                    continue
                if hi is not None and horizon > hi:
                    continue
                by_bucket[label].append(ape)
                break
    out: list[MapeBucket] = []
    for label, *_ in HORIZONS:
        rows = by_bucket[label]
        if not rows:
            out.append(MapeBucket(horizon_label=label, n=0, mean_absolute_pct_error=None))
            continue
        out.append(
            MapeBucket(
                horizon_label=label,
                n=len(rows),
                mean_absolute_pct_error=sum(rows) / len(rows),
            )
        )
    return out


@router.get("/equities", dependencies=[Depends(enforce_read_rate_limit)])
def get_equity_portfolio(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> EquityPortfolioSurface:
    organization_id = _organization_id(store)
    positions = _equity_paper_positions(store, organization_id)
    totals = _equity_track_totals(positions)
    equity_state: EquityPortfolioState | None = None
    try:
        equity_state = store.get_equity_portfolio_state(organization_id)
    except Exception:
        equity_state = None
    metrics.inc("forecasts_read_requests_total", {"route": "get_equity_portfolio"})
    return EquityPortfolioSurface(
        organization_id=organization_id,
        paper_balance_usd=(
            _decimal_to_float(equity_state.paper_balance_usd) if equity_state else 0.0
        ),
        totals=totals,
        live_status=live_status_pills(),
        kill_switch_engaged=(
            bool(equity_state.kill_switch_engaged) if equity_state else False
        ),
        kill_switch_reason=(
            equity_state.kill_switch_reason if equity_state else None
        ),
        open_positions=_open_positions(store, positions),
        recent_signals=_recent_signals(store, organization_id),
        paper_pnl_curve=_paper_curve(positions),
        target_price_mape=_target_price_mape(store, positions),
    )
