"""Authenticated Forecasts operator routes."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import get_bus, get_store
from current_events_api.event_bus import OpinionBus
from current_events_api.routes.forecasts_stream import (
    forecast_sse_frame,
    forecast_sse_response,
    with_forecast_heartbeats,
)
from current_events_api.schemas import (
    OperatorBet,
    PublicForecast,
    operator_bet,
    public_forecast_from_store,
)

from noosphere.forecasts.live_bet_engine import submit_live_bet
from noosphere.forecasts.safety import GateFailure, disengage_kill_switch, engage_kill_switch
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/operator", tags=["operator"])

OPERATOR_HEADER = "x-forecasts-operator"
OPERATOR_TIMESTAMP_HEADER = "x-forecasts-timestamp"
OPERATOR_REPLAY_WINDOW_SECONDS = 300


class OperatorAuthorizeRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    csrf_token: str = Field(min_length=1, max_length=256)


class OperatorConfirmRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    csrf_token: str = Field(min_length=1, max_length=256)


class OperatorCancelRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    csrf_token: str = Field(min_length=1, max_length=256)


class KillSwitchEngageRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=1000)
    csrf_token: str = Field(min_length=1, max_length=256)


class KillSwitchDisengageRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=20, max_length=1000)
    csrf_token: str = Field(min_length=1, max_length=256)


def compute_operator_hmac(
    secret: str,
    *,
    timestamp: str,
    path: str,
    body: bytes,
) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    message = "\n".join([timestamp, path, body_hash]).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


async def require_operator(request: Request) -> None:
    secret = os.getenv("FORECASTS_OPERATOR_SECRET", "").strip()
    if not secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator_secret_not_configured")

    supplied = request.headers.get(OPERATOR_HEADER, "").strip()
    timestamp = request.headers.get(OPERATOR_TIMESTAMP_HEADER, "").strip()
    if not supplied or not timestamp:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator_auth_required")

    try:
        supplied_time = float(timestamp)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator_timestamp_invalid") from exc
    if abs(time.time() - supplied_time) > OPERATOR_REPLAY_WINDOW_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator_timestamp_stale")

    body = await request.body()
    expected = compute_operator_hmac(
        secret,
        timestamp=timestamp,
        path=request.url.path,
        body=body,
    )
    supplied_digest = supplied.removeprefix("sha256=").strip()
    if not hmac.compare_digest(expected, supplied_digest):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator_auth_invalid")


def _require_csrf(csrf_token: str) -> None:
    expected = os.getenv("FORECASTS_OPERATOR_CSRF_TOKEN", "").strip()
    if not csrf_token.strip():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf_required")
    if expected and not hmac.compare_digest(expected, csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf_invalid")


def _live_enabled() -> bool:
    return os.getenv("FORECASTS_LIVE_TRADING_ENABLED", "").strip().lower() == "true"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


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


def _state_payload(store: Store, organization_id: str) -> dict[str, object]:
    state = store.get_portfolio_state(organization_id)
    return {
        "organization_id": organization_id,
        "kill_switch_engaged": bool(state.kill_switch_engaged) if state else False,
        "kill_switch_reason": state.kill_switch_reason if state else None,
        "updated_at": state.updated_at.isoformat() if state else None,
    }


def _bet_event_name(bet: ForecastBet) -> str:
    status_value = _enum_value(bet.status)
    if status_value == ForecastBetStatus.SUBMITTED.value:
        return "bet.submitted"
    if status_value == ForecastBetStatus.FILLED.value:
        return "bet.filled"
    if status_value == ForecastBetStatus.CANCELLED.value:
        return "bet.cancelled"
    if status_value == ForecastBetStatus.FAILED.value:
        return "bet.failed"
    return "bet.submitted"


@router.post(
    "/forecasts/{prediction_id}/authorize-live",
    dependencies=[Depends(require_operator)],
)
def authorize_live(
    prediction_id: str,
    body: OperatorAuthorizeRequest,
    store: Annotated[Store, Depends(get_store)],
) -> PublicForecast:
    _require_csrf(body.csrf_token)
    if not _live_enabled():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "live_trading_disabled")

    timestamp = datetime.now(UTC)
    with store.session() as db:
        prediction = db.get(ForecastPrediction, prediction_id)
        if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
        prediction.live_authorized_at = timestamp
        prediction.live_authorized_by = body.operator_id
        prediction.updated_at = timestamp
        db.add(prediction)
        db.commit()

    refreshed = store.get_forecast_prediction(prediction_id)
    assert refreshed is not None
    return public_forecast_from_store(store, refreshed)


@router.post(
    "/forecasts/{prediction_id}/bets/{bet_id}/confirm",
    dependencies=[Depends(require_operator)],
)
async def confirm_live_bet(
    prediction_id: str,
    bet_id: str,
    body: OperatorConfirmRequest,
    store: Annotated[Store, Depends(get_store)],
    bus: Annotated[OpinionBus, Depends(get_bus)],
) -> OperatorBet:
    _require_csrf(body.csrf_token)
    timestamp = datetime.now(UTC)
    with store.session() as db:
        prediction = db.get(ForecastPrediction, prediction_id)
        bet = db.get(ForecastBet, bet_id)
        if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
        if bet is None or bet.prediction_id != prediction_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "bet_not_found")
        if _enum_value(bet.mode) != ForecastBetMode.LIVE.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_a_live_bet")
        if _enum_value(bet.status) == ForecastBetStatus.AUTHORIZED.value:
            bet.status = ForecastBetStatus.CONFIRMED
            bet.confirmed_at = timestamp
        elif _enum_value(bet.status) == ForecastBetStatus.CONFIRMED.value and bet.confirmed_at is None:
            bet.confirmed_at = timestamp
        if bet.live_authorized_at is None and prediction.live_authorized_at is not None:
            bet.live_authorized_at = prediction.live_authorized_at
        db.add(bet)
        db.commit()

    try:
        submitted = await submit_live_bet(store, bet_id, operator_id=body.operator_id)
    except GateFailure as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"gate_code": exc.code, "detail": exc.detail},
        ) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bet_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    payload = operator_bet(submitted)
    await bus.publish_operator(_bet_event_name(submitted), payload.model_dump(mode="json"))
    return payload


@router.post(
    "/forecasts/{prediction_id}/bets/{bet_id}/cancel",
    dependencies=[Depends(require_operator)],
)
async def cancel_live_bet(
    prediction_id: str,
    bet_id: str,
    body: OperatorCancelRequest,
    store: Annotated[Store, Depends(get_store)],
    bus: Annotated[OpinionBus, Depends(get_bus)],
) -> OperatorBet:
    _require_csrf(body.csrf_token)
    with store.session() as db:
        prediction = db.get(ForecastPrediction, prediction_id)
        bet = db.get(ForecastBet, bet_id)
        if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
        if bet is None or bet.prediction_id != prediction_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "bet_not_found")
        if _enum_value(bet.mode) != ForecastBetMode.LIVE.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_a_live_bet")
        if _enum_value(bet.status) != ForecastBetStatus.AUTHORIZED.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bet_not_cancelable")
        if bet.external_order_id or bet.submitted_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "exchange_order_already_submitted")
        bet.status = ForecastBetStatus.CANCELLED
        db.add(bet)
        db.commit()
        db.refresh(bet)
        payload = operator_bet(bet)

    await bus.publish_operator("bet.cancelled", payload.model_dump(mode="json"))
    return payload


@router.post("/kill-switch/engage", dependencies=[Depends(require_operator)])
async def engage_operator_kill_switch(
    body: KillSwitchEngageRequest,
    store: Annotated[Store, Depends(get_store)],
    bus: Annotated[OpinionBus, Depends(get_bus)],
) -> dict[str, object]:
    _require_csrf(body.csrf_token)
    organization_id = _organization_id(store)
    engage_kill_switch(store, organization_id, reason=body.reason)
    payload = _state_payload(store, organization_id)
    await bus.publish_operator("kill_switch.engaged", payload)
    return payload


@router.post("/kill-switch/disengage", dependencies=[Depends(require_operator)])
async def disengage_operator_kill_switch(
    body: KillSwitchDisengageRequest,
    store: Annotated[Store, Depends(get_store)],
    bus: Annotated[OpinionBus, Depends(get_bus)],
) -> dict[str, object]:
    _require_csrf(body.csrf_token)
    organization_id = _organization_id(store)
    try:
        disengage_kill_switch(
            store,
            organization_id,
            operator_id=body.operator_id,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    payload = _state_payload(store, organization_id)
    await bus.publish_operator("kill_switch.disengaged", payload)
    return payload


@router.get("/live-bets", dependencies=[Depends(require_operator)])
def list_live_bets(
    store: Annotated[Store, Depends(get_store)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[OperatorBet] | int | None]:
    organization_id = _organization_id(store)
    with store.session() as db:
        rows = list(
            db.exec(
                select(ForecastBet)
                .where(ForecastBet.organization_id == organization_id)
                .where(ForecastBet.mode == ForecastBetMode.LIVE.value)
                .order_by(desc(ForecastBet.created_at))
                .offset(offset)
                .limit(limit + 1)
            ).all()
        )
    next_offset = offset + limit if len(rows) > limit else None
    return {
        "items": [operator_bet(row) for row in rows[:limit]],
        "next_offset": next_offset,
    }


@router.get("/stream", dependencies=[Depends(require_operator)])
def stream_operator(
    bus: Annotated[OpinionBus, Depends(get_bus)],
) -> StreamingResponse:
    async def frames() -> AsyncIterator[bytes]:
        async for message in bus.subscribe_operator():
            event = str(message.get("event") or message.get("kind") or "operator.event")
            payload = message.get("data", message.get("payload", {}))
            yield forecast_sse_frame(event, payload)

    return forecast_sse_response(with_forecast_heartbeats(frames()))
