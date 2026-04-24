"""Follow-up route tests — covers happy-path streaming, 404s, rate limits, and history replay."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

from noosphere.currents.followup import FollowUpAnswerChunk
from noosphere.models import (
    FollowUpMessage,
    FollowUpMessageRole,
    FollowUpSession,
    OpinionCitation,
)

from current_events_api.deps import get_budget, get_bus, get_store
from current_events_api.event_bus import OpinionBus
from current_events_api.main import create_app
from noosphere.currents.budget import HourlyBudgetGuard

from tests.conftest import seed_opinion_with_citations


UTC = timezone.utc


async def _fake_answer_stream(*args, **kwargs):
    # Three token deltas then a done chunk with one citation. The citation
    # uses ``conclusion_id`` so we can round-trip through the public shape.
    yield FollowUpAnswerChunk(text="alpha ", done=False)
    yield FollowUpAnswerChunk(text="beta ", done=False)
    yield FollowUpAnswerChunk(text="gamma", done=False)
    yield FollowUpAnswerChunk(
        text="",
        done=True,
        citations=[
            OpinionCitation(
                id="cite-fake-0",
                opinion_id="op-a",
                conclusion_id="conc-1",
                quoted_span="Conclusion body",
                relevance_score=0.9,
                ordinal=0,
            )
        ],
        refused=False,
    )


async def _collect_stream(response: httpx.Response, timeout: float = 3.0) -> bytes:
    buf = bytearray()

    async def inner():
        async for chunk in response.aiter_bytes():
            buf.extend(chunk)

    try:
        await asyncio.wait_for(inner(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return bytes(buf)


@pytest.mark.asyncio
async def test_followup_stream_happy_path(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store, opinion_id="op-a", event_id="ev-a", generated_at=now
    )

    with patch(
        "current_events_api.routes.followup.answer_followup",
        side_effect=_fake_answer_stream,
    ):
        async with client.stream(
            "POST",
            "/v1/currents/op-a/follow-up",
            json={"question": "Why?"},
        ) as resp:
            assert resp.status_code == 200
            body = await _collect_stream(resp)

    text = body.decode("utf-8", errors="replace")
    assert "event: meta" in text
    # Three token frames.
    assert text.count("event: token") == 3
    assert "alpha" in text and "beta" in text and "gamma" in text
    assert "event: citation" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_followup_404_on_unknown_opinion(client):
    r = await client.post(
        "/v1/currents/nope/follow-up",
        json={"question": "Why?"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_followup_rate_limit_429(store):
    # Build a dedicated app + ASGI transport using a fixed client host so
    # the 11th POST from the same IP within the window trips the limiter.
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store, opinion_id="op-rl", event_id="ev-rl", generated_at=now
    )

    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_bus] = lambda: OpinionBus()
    app.dependency_overrides[get_budget] = lambda: HourlyBudgetGuard()
    transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 12345))

    try:
        with patch(
            "current_events_api.routes.followup.answer_followup",
            side_effect=_fake_answer_stream,
        ):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as c:
                # 10 allowed; 11th should 429.
                for i in range(10):
                    async with c.stream(
                        "POST",
                        "/v1/currents/op-rl/follow-up",
                        json={"question": f"q{i}"},
                    ) as resp:
                        assert resp.status_code == 200, i
                        # Drain to release the connection.
                        async for _ in resp.aiter_bytes():
                            pass

                r = await c.post(
                    "/v1/currents/op-rl/follow-up",
                    json={"question": "q-final"},
                )
                assert r.status_code == 429
                assert r.headers.get("retry-after")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_messages_returns_history(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store, opinion_id="op-hist", event_id="ev-hist", generated_at=now
    )
    session = FollowUpSession(
        id="sess-1",
        opinion_id="op-hist",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=24),
        client_fingerprint="fp-1",
        message_count=0,
    )
    store.add_followup_session(session)
    store.add_followup_message(
        FollowUpMessage(
            id="msg-0",
            session_id="sess-1",
            role=FollowUpMessageRole.USER,
            created_at=now,
            content="Hi",
        )
    )
    store.add_followup_message(
        FollowUpMessage(
            id="msg-1",
            session_id="sess-1",
            role=FollowUpMessageRole.ASSISTANT,
            created_at=now + timedelta(seconds=1),
            content="Hello",
        )
    )

    r = await client.get("/v1/currents/op-hist/follow-up/sess-1/messages")
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == ["msg-0", "msg-1"]
    assert body[0]["role"] == "user"
    assert body[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_messages_404_on_wrong_opinion(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store, opinion_id="op-a", event_id="ev-a", generated_at=now
    )
    seed_opinion_with_citations(
        store,
        opinion_id="op-b",
        event_id="ev-b",
        generated_at=now,
        conclusion_id="conc-b",
        claim_id="clm-b",
    )
    session = FollowUpSession(
        id="sess-x",
        opinion_id="op-a",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=24),
        client_fingerprint="fp",
        message_count=0,
    )
    store.add_followup_session(session)

    # Requesting under op-b must 404 since the session belongs to op-a.
    r = await client.get("/v1/currents/op-b/follow-up/sess-x/messages")
    assert r.status_code == 404
