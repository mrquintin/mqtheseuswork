"""Follow-up SSE routes for public Currents opinions."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
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
    FollowupAnswerChunk,
    FollowupRateLimited,
    _enforce_rate_limits,
    _utcnow_naive,
    answer_followup,
)
from noosphere.models import FollowUpMessage, FollowUpSession
from noosphere.store import Store

router = APIRouter(prefix="/v1/currents", tags=["follow-up"])


class FollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=128)


def _load_or_create_session(
    *,
    store: Store,
    opinion_id: str,
    session_id: str | None,
    fingerprint: str,
) -> FollowUpSession:
    if store.get_event_opinion(opinion_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opinion_not_found")
    if session_id:
        session = store.get_followup_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "followup_session_not_found")
        if session.opinion_id != opinion_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "session_opinion_mismatch")
        return session
    created_id = store.add_followup_session(
        FollowUpSession(
            opinion_id=opinion_id,
            client_fingerprint=fingerprint,
        )
    )
    session = store.get_followup_session(created_id)
    if session is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "session_create_failed")
    return session


def _preflight_followup_limits(
    *,
    store: Store,
    limits: RateLimitRegistry,
    fingerprint: str,
    session: FollowUpSession,
) -> None:
    try:
        _enforce_rate_limits(store, session, _utcnow_naive())
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


@router.post("/{opinion_id}/follow-up")
def post_followup(
    opinion_id: str,
    body: FollowupRequest,
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
        opinion_id=opinion_id,
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
                async for chunk in answer_followup(
                    store,
                    opinion_id,
                    session.id,
                    question,
                    budget=budget,
                ):
                    metrics.inc("currents_sse_frames_total", {"kind": chunk.kind})
                    yield sse_frame(chunk.kind, _chunk_payload(chunk))
            except FollowupRateLimited as exc:
                yield sse_frame(
                    "error",
                    rate_limit_body(exc.reason, exc.retry_after_s),
                )
                yield sse_frame("done", {})
            except BudgetExhausted:
                yield sse_frame("error", {"reason": "budget_exhausted"})
                yield sse_frame("done", {})

    metrics.inc("currents_followup_requests_total")
    return sse_response(with_heartbeats(frames()))


@router.get(
    "/{opinion_id}/follow-up/{session_id}/messages",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def list_followup_messages(
    opinion_id: str,
    session_id: str,
    store: Annotated[Store, Depends(get_store)],
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=50),
) -> dict[str, list[PublicFollowupMessage] | str | None]:
    session = store.get_followup_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "followup_session_not_found")
    if session.opinion_id != opinion_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "session_opinion_mismatch")

    stmt = select(FollowUpMessage).where(FollowUpMessage.session_id == session_id)
    if before is not None:
        stmt = stmt.where(FollowUpMessage.created_at < before)
    with store.session() as db:
        rows = list(
            db.exec(
                stmt.order_by(desc(FollowUpMessage.created_at)).limit(limit)
            ).all()
        )
    rows.reverse()
    next_before = rows[0].created_at.isoformat() if len(rows) == limit and rows else None
    return {
        "items": [public_followup_message(row) for row in rows],
        "next_before": next_before,
    }
