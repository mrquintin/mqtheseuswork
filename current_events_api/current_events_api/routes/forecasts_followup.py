"""Follow-up SSE routes for public Forecasts predictions."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import (
    client_fingerprint,
    enforce_read_rate_limit,
    get_budget,
    get_bus,
    get_metrics,
    get_rate_limits,
    get_store,
    rate_limit_body,
    rate_limit_http_exception,
)
from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.rate_limit import RateLimitExceeded, RateLimitRegistry
from current_events_api.schemas import PublicFollowupMessage, public_followup_message
from current_events_api.sse import sse_frame, sse_response, with_heartbeats

from noosphere.currents.budget import BudgetExhausted
from noosphere.currents.followup import (
    FOLLOWUP_MAX_TOKENS,
    MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS,
    RATE_LIMIT_PER_FINGERPRINT_PER_DAY,
    RATE_LIMIT_PER_SESSION,
    FollowupAnswerChunk,
    FollowupRateLimited,
    _call_followup_llm,
    _charge_budget,
    _parse_followup_response,
    _read_system_prompt,
    _text_chunks,
    _utcnow_naive,
    _wrap_question,
)
from noosphere.currents.opinion_generator import _estimate_tokens, _source_blocks, validate_citations
from noosphere.forecasts.forecast_generator import retrieve_for_market
from noosphere.models import (
    ForecastFollowUpMessage,
    ForecastFollowUpRole,
    ForecastFollowUpSession,
    ForecastPredictionStatus,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/forecasts", tags=["forecasts-follow-up"])


class ForecastFollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=128)


@dataclass(frozen=True)
class _FollowupHit:
    source_kind: str
    source_id: str
    text: str
    score: float
    topic_hint: str | None = None
    origin: str | None = None


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _day_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, now.day)
    return start, start + timedelta(days=1)


def _load_or_create_session(
    *,
    store: Store,
    prediction_id: str,
    session_id: str | None,
    fingerprint: str,
) -> ForecastFollowUpSession:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None or _enum_value(prediction.status) != ForecastPredictionStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "forecast_not_found")
    if session_id:
        session = store.get_forecast_followup_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "followup_session_not_found")
        if session.prediction_id != prediction_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "session_prediction_mismatch")
        return session
    created_id = store.add_forecast_followup_session(
        ForecastFollowUpSession(
            prediction_id=prediction_id,
            client_fingerprint=fingerprint,
        )
    )
    session = store.get_forecast_followup_session(created_id)
    if session is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "session_create_failed")
    return session


def _user_message_count_for_session(store: Store, session_id: str) -> int:
    with store.session() as db:
        rows = db.exec(
            select(ForecastFollowUpMessage)
            .where(ForecastFollowUpMessage.session_id == session_id)
            .where(ForecastFollowUpMessage.role == ForecastFollowUpRole.USER)
        ).all()
        return len(rows)


def _last_user_message_for_session(
    store: Store,
    session_id: str,
) -> ForecastFollowUpMessage | None:
    with store.session() as db:
        return db.exec(
            select(ForecastFollowUpMessage)
            .where(ForecastFollowUpMessage.session_id == session_id)
            .where(ForecastFollowUpMessage.role == ForecastFollowUpRole.USER)
            .order_by(desc(ForecastFollowUpMessage.created_at))
        ).first()


def _fingerprint_user_count_today(
    store: Store,
    fingerprint: str,
    now: datetime,
) -> int:
    day_start, day_end = _day_bounds_utc(now)
    with store.session() as db:
        rows = db.exec(
            select(ForecastFollowUpMessage)
            .join(
                ForecastFollowUpSession,
                ForecastFollowUpMessage.session_id == ForecastFollowUpSession.id,
            )
            .where(ForecastFollowUpSession.client_fingerprint == fingerprint)
            .where(ForecastFollowUpMessage.role == ForecastFollowUpRole.USER)
            .where(ForecastFollowUpMessage.created_at >= day_start)
            .where(ForecastFollowUpMessage.created_at < day_end)
        ).all()
        return len(rows)


def _enforce_forecast_history_limits(
    store: Store,
    session: ForecastFollowUpSession,
    now: datetime,
) -> None:
    if _fingerprint_user_count_today(store, session.client_fingerprint, now) >= RATE_LIMIT_PER_FINGERPRINT_PER_DAY:
        raise FollowupRateLimited("fingerprint_daily_limit")

    if _user_message_count_for_session(store, session.id) >= RATE_LIMIT_PER_SESSION:
        raise FollowupRateLimited("session_message_limit")

    last_user_message = _last_user_message_for_session(store, session.id)
    if last_user_message is not None:
        elapsed = (now - last_user_message.created_at).total_seconds()
        if elapsed < MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS:
            retry_after = max(1, int(MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS - elapsed))
            raise FollowupRateLimited("min_interval", retry_after_s=retry_after)


def _preflight_followup_limits(
    *,
    store: Store,
    limits: RateLimitRegistry,
    fingerprint: str,
    session: ForecastFollowUpSession,
) -> None:
    try:
        _enforce_forecast_history_limits(store, session, _utcnow_naive())
    except FollowupRateLimited as exc:
        headers = {}
        if exc.retry_after_s is not None:
            headers["Retry-After"] = str(exc.retry_after_s)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_limit_body(exc.reason, exc.retry_after_s),
            headers=headers,
        ) from exc
    try:
        limits.check_followup(fingerprint)
        limits.check_session_message(session.id)
    except RateLimitExceeded as exc:
        raise rate_limit_http_exception(exc) from exc


def _chunk_payload(chunk: FollowupAnswerChunk) -> object:
    if chunk.kind == "meta":
        try:
            return json.loads(chunk.text or "{}")
        except json.JSONDecodeError:
            return {"raw": chunk.text or ""}
    if chunk.kind == "token":
        return {"text": chunk.text or ""}
    if chunk.kind == "citation":
        return chunk.citation or {}
    return {}


def _hits_for_question(store: Store, market: object, question: str) -> list[_FollowupHit]:
    question_market = SimpleNamespace(
        title=f"{getattr(market, 'title', '')}\n\nFollow-up question: {question}",
        description=getattr(market, "description", ""),
        resolution_criteria=getattr(market, "resolution_criteria", ""),
        category=getattr(market, "category", ""),
    )
    hits = retrieve_for_market(store, question_market, top_k=8)
    return [
        _FollowupHit(
            source_kind=str(getattr(hit, "source_type", "")).lower(),
            source_id=str(getattr(hit, "source_id", "")),
            text=str(getattr(hit, "text", "")),
            score=float(getattr(hit, "relevance", 0.0) or 0.0),
            topic_hint=getattr(market, "category", None),
            origin="forecasts",
        )
        for hit in hits
    ]


def _followup_prompt(
    *,
    prediction: object,
    market: object,
    session_id: str,
    wrapped_question: str,
    hits: list[_FollowupHit],
) -> str:
    return "\n\n".join(
        [
            "EXISTING FORECAST CONTEXT",
            f"prediction_id: {getattr(prediction, 'id', '')}",
            f"session_id: {session_id}",
            f"market_title: {getattr(market, 'title', '')}",
            f"probability_yes: {getattr(prediction, 'probability_yes', '')}",
            f"headline: {getattr(prediction, 'headline', '')}",
            "reasoning:",
            str(getattr(prediction, "reasoning", "")),
            "FRESHLY RETRIEVED THESEUS SOURCES",
            _source_blocks(hits),
            "UNTRUSTED USER QUESTION",
            wrapped_question,
            "Return the strict JSON object specified by the system prompt.",
        ]
    )


def _authorize_budget(budget: object, *, system: str, user: str) -> None:
    authorize = getattr(budget, "authorize", None)
    if callable(authorize):
        authorize(_estimate_tokens(system, user), FOLLOWUP_MAX_TOKENS)


async def answer_forecast_followup(
    store: Store,
    prediction_id: str,
    session_id: str,
    user_question: str,
    *,
    budget: object,
) -> AsyncIterator[FollowupAnswerChunk]:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None:
        raise KeyError(f"unknown forecast prediction: {prediction_id}")
    session = store.get_forecast_followup_session(session_id)
    if session is None:
        raise KeyError(f"unknown forecast follow-up session: {session_id}")
    if session.prediction_id != prediction_id:
        raise ValueError("follow-up session does not belong to prediction")
    market = store.get_forecast_market(prediction.market_id)
    if market is None:
        raise KeyError(f"unknown forecast market: {prediction.market_id}")

    now = _utcnow_naive()
    _enforce_forecast_history_limits(store, session, now)

    hits = _hits_for_question(store, market, user_question)
    wrapped_question = _wrap_question(user_question)
    system_prompt = _read_system_prompt("followup_system.md")
    user_prompt = _followup_prompt(
        prediction=prediction,
        market=market,
        session_id=session_id,
        wrapped_question=wrapped_question,
        hits=hits,
    )
    _authorize_budget(budget, system=system_prompt, user=user_prompt)

    from noosphere.currents.followup import make_client

    client = make_client()
    response = await _call_followup_llm(client, system=system_prompt, user=user_prompt)
    _charge_budget(budget, response)
    answer_text, raw_citations = _parse_followup_response(response.text)
    citations, _errors = validate_citations(raw_citations, hits, require_any=False)

    store.add_forecast_followup_message(
        ForecastFollowUpMessage(
            session_id=session_id,
            role=ForecastFollowUpRole.USER,
            content=user_question,
            created_at=now,
        )
    )
    store.add_forecast_followup_message(
        ForecastFollowUpMessage(
            session_id=session_id,
            role=ForecastFollowUpRole.ASSISTANT,
            content=answer_text,
            citations=citations,
            created_at=_utcnow_naive(),
        )
    )

    meta = {
        "prediction_id": prediction_id,
        "session_id": session_id,
        "model": response.model,
        "source_count": len(hits),
    }
    yield FollowupAnswerChunk(kind="meta", text=json.dumps(meta, sort_keys=True), citation=None)
    for chunk in _text_chunks(answer_text):
        yield FollowupAnswerChunk(kind="token", text=chunk, citation=None)
    for citation in citations:
        yield FollowupAnswerChunk(kind="citation", text=None, citation=citation)
    yield FollowupAnswerChunk(kind="done", text=None, citation=None)


@router.post("/{prediction_id}/follow-up")
def post_forecast_followup(
    prediction_id: str,
    body: ForecastFollowupRequest,
    request: Request,
    store: Annotated[Store, Depends(get_store)],
    budget: Annotated[object, Depends(get_budget)],
    bus: Annotated[OpinionBus, Depends(get_bus)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    limits: Annotated[RateLimitRegistry, Depends(get_rate_limits)],
) -> StreamingResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_question")
    fingerprint = client_fingerprint(request)
    session = _load_or_create_session(
        store=store,
        prediction_id=prediction_id,
        session_id=body.session_id,
        fingerprint=fingerprint,
    )
    _preflight_followup_limits(
        store=store,
        limits=limits,
        fingerprint=fingerprint,
        session=session,
    )

    async def frames() -> AsyncIterator[bytes]:
        with bus.track_followup_client():
            try:
                async for chunk in answer_forecast_followup(
                    store,
                    prediction_id,
                    session.id,
                    question,
                    budget=budget,
                ):
                    metrics.inc("forecasts_sse_frames_total", {"kind": chunk.kind})
                    yield sse_frame(chunk.kind, _chunk_payload(chunk))
            except FollowupRateLimited as exc:
                yield sse_frame("error", rate_limit_body(exc.reason, exc.retry_after_s))
                yield sse_frame("done", {})
            except BudgetExhausted:
                yield sse_frame("error", {"reason": "budget_exhausted"})
                yield sse_frame("done", {})

    metrics.inc("forecasts_followup_requests_total")
    return sse_response(with_heartbeats(frames()))


@router.get(
    "/{prediction_id}/follow-up/{session_id}/messages",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def list_forecast_followup_messages(
    prediction_id: str,
    session_id: str,
    store: Annotated[Store, Depends(get_store)],
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=50),
) -> dict[str, list[PublicFollowupMessage] | str | None]:
    session = store.get_forecast_followup_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "followup_session_not_found")
    if session.prediction_id != prediction_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "session_prediction_mismatch")

    stmt = select(ForecastFollowUpMessage).where(ForecastFollowUpMessage.session_id == session_id)
    if before is not None:
        stmt = stmt.where(ForecastFollowUpMessage.created_at < before)
    with store.session() as db:
        rows = list(
            db.exec(
                stmt.order_by(desc(ForecastFollowUpMessage.created_at)).limit(limit)
            ).all()
        )
    rows.reverse()
    next_before = rows[0].created_at.isoformat() if len(rows) == limit and rows else None
    return {
        "items": [public_followup_message(row) for row in rows],
        "next_before": next_before,
    }
