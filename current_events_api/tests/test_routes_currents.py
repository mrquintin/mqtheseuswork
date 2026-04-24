"""Route tests for ``/health``, ``/v1/currents``, and ``/v1/currents/stream``."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.models import OpinionStance

from tests.conftest import seed_opinion_with_citations


UTC = timezone.utc


@pytest.mark.asyncio
async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_list_currents_returns_seeded(client, store):
    now = datetime.now(UTC)
    for i in range(3):
        seed_opinion_with_citations(
            store,
            opinion_id=f"op-{i}",
            event_id=f"ev-{i}",
            generated_at=now - timedelta(minutes=i),
        )

    r = await client.get("/v1/currents")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    # Descending by generated_at: op-0 is newest.
    assert body["items"][0]["id"] == "op-0"


@pytest.mark.asyncio
async def test_list_currents_filters_by_topic_and_stance(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store,
        opinion_id="op-ai-agrees",
        event_id="ev-1",
        generated_at=now,
        topic_hint="ai",
        stance=OpinionStance.AGREES,
    )
    seed_opinion_with_citations(
        store,
        opinion_id="op-politics-disagrees",
        event_id="ev-2",
        generated_at=now - timedelta(minutes=1),
        topic_hint="politics",
        stance=OpinionStance.DISAGREES,
    )
    seed_opinion_with_citations(
        store,
        opinion_id="op-ai-complicates",
        event_id="ev-3",
        generated_at=now - timedelta(minutes=2),
        topic_hint="ai",
        stance=OpinionStance.COMPLICATES,
    )

    r = await client.get("/v1/currents", params={"topic": "ai"})
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()["items"]]
    assert set(ids) == {"op-ai-agrees", "op-ai-complicates"}

    r = await client.get("/v1/currents", params={"stance": "disagrees"})
    ids = [it["id"] for it in r.json()["items"]]
    assert ids == ["op-politics-disagrees"]


@pytest.mark.asyncio
async def test_get_current_returns_citations(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store,
        opinion_id="op-a",
        event_id="ev-a",
        generated_at=now,
    )
    r = await client.get("/v1/currents/op-a")
    assert r.status_code == 200
    body = r.json()
    kinds = {c["source_kind"] for c in body["citations"]}
    assert kinds == {"conclusion", "claim"}


@pytest.mark.asyncio
async def test_get_current_404(client):
    r = await client.get("/v1/currents/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_sources_resolves_conclusions_and_claims(client, store):
    now = datetime.now(UTC)
    seed_opinion_with_citations(
        store,
        opinion_id="op-src",
        event_id="ev-src",
        generated_at=now,
    )
    r = await client.get("/v1/currents/op-src/sources")
    assert r.status_code == 200
    sources = r.json()
    assert len(sources) == 2
    by_kind = {s["source_kind"]: s for s in sources}
    assert "conclusion" in by_kind and "claim" in by_kind
    # Conclusion has neither slug nor version — permalink must be None.
    assert by_kind["conclusion"]["permalink"] is None
    assert by_kind["conclusion"]["full_text"] == "Conclusion body text."
    # Claims never have a permalink. Origin defaults to "founder".
    assert by_kind["claim"]["permalink"] is None
    assert by_kind["claim"]["full_text"] == "Claim text body."
    assert by_kind["claim"]["origin"] == "founder"


@pytest.mark.asyncio
async def test_get_sources_404_on_unknown_opinion(client):
    r = await client.get("/v1/currents/nope/sources")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_currents_pagination_cursor(client, store):
    now = datetime.now(UTC)
    for i in range(5):
        seed_opinion_with_citations(
            store,
            opinion_id=f"op-{i:02d}",
            event_id=f"ev-{i:02d}",
            generated_at=now - timedelta(minutes=i),
        )
    r = await client.get("/v1/currents", params={"limit": 2})
    first = r.json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]

    r2 = await client.get(
        "/v1/currents", params={"limit": 2, "cursor": first["next_cursor"]}
    )
    second = r2.json()
    assert len(second["items"]) == 2
    # No overlap between pages.
    ids1 = {it["id"] for it in first["items"]}
    ids2 = {it["id"] for it in second["items"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin(client):
    # Default CORS allows only http://localhost:3001. An OPTIONS from an
    # unlisted origin must not receive Access-Control-Allow-Origin.
    r = await client.options(
        "/v1/currents",
        headers={
            "origin": "http://evil.example.com",
            "access-control-request-method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {
        k.lower() for k in r.headers.keys()
    }


@pytest.mark.asyncio
async def test_stream_currents_emits_on_publish(bus):
    """Drive the stream generator directly.

    httpx ``ASGITransport`` buffers streaming responses in-process rather
    than delivering chunks asynchronously (see httpx issue tracker). That
    means an end-to-end test through ``AsyncClient.stream`` deadlocks on
    the subscribe-vs-publish handshake. Instead, drive the route's async
    generator directly — this still exercises the real code path (the
    ``stream_currents`` handler, ``OpinionBus.subscribe``, and
    ``format_sse``) without fighting the transport.
    """
    from current_events_api.routes.stream import stream_currents

    resp = await stream_currents(bus=bus)
    gen = resp.body_iterator

    frames: list[bytes] = []

    async def consume_one():
        chunk = await gen.__anext__()
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        frames.append(chunk)

    # Prime frame first (": connected\n\n"). Then publish two payloads and
    # read the two opinion frames the subscription yields.
    await consume_one()  # prime

    async def publisher():
        await asyncio.sleep(0.05)
        bus.publish({"opinion_id": "op-1"})
        await asyncio.sleep(0.05)
        bus.publish({"opinion_id": "op-2"})

    pub_task = asyncio.create_task(publisher())
    for _ in range(2):
        chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        frames.append(chunk)
    await pub_task

    await gen.aclose()

    opinion_frames = [f for f in frames if b"event: opinion" in f]
    assert len(opinion_frames) >= 2


@pytest.mark.asyncio
async def test_stream_heartbeat_emitted_when_idle(bus, monkeypatch):
    """When no payload is published, the stream emits heartbeat frames.

    We override ``HEARTBEAT_S`` to a small value so the test doesn't have
    to wait 15s.
    """
    import current_events_api.routes.stream as stream_mod

    monkeypatch.setattr(stream_mod, "HEARTBEAT_S", 0.1)

    resp = await stream_mod.stream_currents(bus=bus)
    gen = resp.body_iterator

    frames: list[bytes] = []
    # Prime + at least one heartbeat within ~1s.
    prime = await gen.__anext__()
    frames.append(prime.encode("utf-8") if isinstance(prime, str) else prime)

    async def collect_until_heartbeat():
        while True:
            chunk = await gen.__anext__()
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            frames.append(chunk)
            if b"event: heartbeat" in chunk:
                return

    await asyncio.wait_for(collect_until_heartbeat(), timeout=2.0)
    await gen.aclose()

    assert any(b"event: heartbeat" in f for f in frames)
