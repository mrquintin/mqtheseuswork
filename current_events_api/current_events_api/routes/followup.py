"""Follow-up chat routes (SSE-streamed answers + history replay)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from noosphere.currents import (
    RateLimitExceeded,
    answer_followup,
    compute_client_fingerprint,
    get_or_create_session,
)
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.store import Store

from current_events_api.deps import get_budget, get_store
from current_events_api.rate_limit import FOLLOWUP_RATE
from current_events_api.schemas import (
    FollowupRequest,
    PublicFollowupMessage,
    citation_to_public,
    followup_msg_to_public,
)
from current_events_api.sse import format_sse


router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _citation_to_public_dict(c) -> dict:  # noqa: ANN001 - OpinionCitation
    return citation_to_public(c).model_dump()


@router.post("/currents/{opinion_id}/follow-up")
async def follow_up(
    opinion_id: str,
    body: FollowupRequest,
    request: Request,
    store: Store = Depends(get_store),
    budget: HourlyBudgetGuard = Depends(get_budget),
):
    ip = request.client.host if request.client else "unknown"
    ok, retry = FOLLOWUP_RATE.check(ip)
    if not ok:
        return JSONResponse(
            {"error": "rate_limited"},
            status_code=429,
            headers={"Retry-After": f"{int(retry) + 1}"},
        )

    op = store.get_event_opinion(opinion_id)
    if op is None:
        raise HTTPException(status_code=404, detail="not found")
    event = store.get_current_event(op.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    ua = request.headers.get("user-agent", "")
    fp = compute_client_fingerprint(ip, ua, _now())
    try:
        session = get_or_create_session(store, opinion=op, client_fingerprint=fp)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"session_create_failed:{type(e).__name__}",
        )

    async def gen():
        yield format_sse("meta", {"session_id": session.id, "opinion_id": op.id})
        try:
            async for chunk in answer_followup(
                store,
                session=session,
                event=event,
                opinion=op,
                user_question=body.question,
                budget=budget,
            ):
                if chunk.done:
                    for c in chunk.citations or []:
                        yield format_sse("citation", _citation_to_public_dict(c))
                    yield format_sse(
                        "done",
                        {
                            "refused": bool(chunk.refused),
                            "refusal_reason": chunk.refusal_reason,
                        },
                    )
                elif chunk.text:
                    yield format_sse("token", chunk.text)
        except RateLimitExceeded as e:
            yield format_sse(
                "error",
                {"error": "rate_limit", "reason": str(e)},
            )
        except Exception as e:  # noqa: BLE001
            yield format_sse("error", {"error": type(e).__name__})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/currents/{opinion_id}/follow-up/{session_id}/messages",
    response_model=list[PublicFollowupMessage],
)
def list_messages(
    opinion_id: str,
    session_id: str,
    store: Store = Depends(get_store),
):
    sess = store.get_followup_session(session_id)
    if sess is None or sess.opinion_id != opinion_id:
        raise HTTPException(status_code=404, detail="session not found")
    msgs = store.list_followup_messages(session_id)
    return [followup_msg_to_public(m) for m in msgs]
