"""Prompt 17: end-to-end pipeline test.

Exercises the full chain: ingest (X fake) -> enrich -> relevance ->
generate (LLM fake) -> persist -> API response -> SSE fan-out.

Neither the real X API nor the real Anthropic API are hit. Retrieval is
monkeypatched with a deterministic hit list so we can reason about the
outcome without needing a real embedding model either.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from noosphere.currents import opinion_generator as og
from noosphere.currents import x_ingestor
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.enrich import enrich_event
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.relevance import check_relevance
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    Conclusion,
    CurrentEventStatus,
)
from noosphere.store import Store

from tests.fakes.fake_anthropic_client import FakeLLMClient, reply_with
from tests.fakes.fake_x_client import FakeTweet, FakeXClient


UTC = timezone.utc


# ── shared helpers ──────────────────────────────────────────────────


def _seeded_store(tmp_path) -> tuple[Store, Conclusion]:
    db_path = tmp_path / "e2e.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    conc = Conclusion(
        id="conc-capex",
        text=(
            "AI compute demand drives chip capex across the semiconductor "
            "industry. Orders reflect expectations of sustained inference load."
        ),
    )
    store.put_conclusion(conc)
    return store, conc


def _cfg() -> IngestorConfig:
    return IngestorConfig(
        bearer_token="test-bearer",
        curated_accounts=["alice"],
        topic_keywords=[],
        lookback_minutes=15,
        max_posts_per_account=5,
        max_posts_per_keyword_query=5,
        request_timeout_s=15.0,
        base_url="https://api.example-x.invalid",
    )


def _install_x_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeXClient) -> None:
    monkeypatch.setattr(
        "noosphere.currents.x_ingestor.make_client",
        lambda cfg: fake,
    )


def _patch_retrieval(
    monkeypatch: pytest.MonkeyPatch, hits: list[EventRetrievalHit]
) -> list[int]:
    calls: list[int] = []

    def _fn(store, event, **kw):
        calls.append(1)
        return list(hits)

    monkeypatch.setattr(og, "retrieve_for_event", _fn)
    return calls


def _patch_enrich_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the real embedding model in the enricher."""
    from noosphere.currents import enrich as _enrich

    monkeypatch.setattr(_enrich, "embed_text", lambda text: [0.1, 0.2, 0.3, 0.4])


def _happy_reply() -> str:
    return json.dumps(
        {
            "stance": "agrees",
            "confidence": 0.72,
            "headline": (
                "The firm's prior conclusions on capex cycles align with the "
                "announcement, implying durable AI demand."
            ),
            "body_markdown": (
                "The firm's prior conclusion suggests AI compute demand drives "
                "chip capex through multi-year cycles. The announcement aligns."
            ),
            "uncertainty_notes": ["Single-quarter signal."],
            "citations": [
                {
                    "source_kind": "conclusion",
                    "source_id": "conc-capex",
                    "quoted_span": "AI compute demand drives chip capex",
                    "relevance_score": 0.88,
                },
                {
                    "source_kind": "conclusion",
                    "source_id": "conc-capex",
                    "quoted_span": "sustained inference load",
                    "relevance_score": 0.71,
                },
            ],
        }
    )


# ── tests ───────────────────────────────────────────────────────────


def test_full_pipeline_ingest_to_opinion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store, conc = _seeded_store(tmp_path)
    _patch_enrich_embedding(monkeypatch)

    # 1. Ingest via fake X client.
    now = datetime.now(UTC)
    fake_x = FakeXClient(
        tweets=[
            FakeTweet(
                id="1780000000000000001",
                text="Big chipmaker reports record AI capex guide",
                author_id="100001",
                author_handle="alice",
                created_at=now,
            ),
        ],
    )
    _install_x_fake(monkeypatch, fake_x)

    ingested = asyncio.run(x_ingestor.ingest_once(store, _cfg(), now=now))
    assert ingested == 1
    ids = store.list_current_event_ids()
    assert len(ids) == 1
    event_id = ids[0]

    # 2. Enrich.
    ev = store.get_current_event(event_id)
    assert ev is not None
    enrich_event(store, ev)
    ev = store.get_current_event(event_id)
    assert ev is not None
    assert ev.embedding is not None

    # 3. Relevance — patch retrieval and verify the gate passes.
    hits = [
        EventRetrievalHit(
            source_kind="conclusion",
            source_id="conc-capex",
            text=conc.text[:400],
            score=0.91,
        ),
        EventRetrievalHit(
            source_kind="conclusion",
            source_id="conc-capex",
            text=conc.text[:400],
            score=0.64,
        ),
    ]
    import noosphere.currents.relevance as _rel

    monkeypatch.setattr(_rel, "retrieve_for_event", lambda s, e: list(hits))
    _patch_retrieval(monkeypatch, hits)

    rel = check_relevance(store, ev)
    assert rel.passed is True

    # 4. Generate via fake LLM.
    fake_llm = FakeLLMClient(script=[reply_with(_happy_reply())])
    monkeypatch.setattr(
        "noosphere.currents._llm_client.make_client",
        lambda: fake_llm,
    )

    budget = HourlyBudgetGuard(
        max_prompt_tokens=10_000_000, max_completion_tokens=10_000_000
    )
    outcome = generate_opinion(store, ev, budget=budget)
    assert outcome == OpinionOutcome.PUBLISHED
    assert len(fake_llm.calls) == 1

    # 5. Persisted shape: exactly one opinion with citations referencing the
    #    seeded conclusion; event status flipped to OPINED.
    op_ids = store.list_opinions_for_event(ev.id)
    assert len(op_ids) == 1
    op = store.get_event_opinion(op_ids[0])
    assert op is not None
    assert op.stance.value == "agrees"
    cites = store.list_citations_for_opinion(op_ids[0])
    assert len(cites) == 2
    for c in cites:
        assert c.conclusion_id == "conc-capex"
        assert c.claim_id is None
    ev_after = store.get_current_event(ev.id)
    assert ev_after is not None
    assert ev_after.status == CurrentEventStatus.OPINED

    # 6. API response: override dependencies + hit /v1/currents.
    from current_events_api.deps import get_bus, get_store
    from current_events_api.event_bus import OpinionBus
    from current_events_api.main import create_app

    bus = OpinionBus()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_bus] = lambda: bus

    async def _hit_api():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            r = await c.get("/v1/currents")
            assert r.status_code == 200
            j = r.json()
            assert j["items"], "currents list is empty"
            # Internal-only fields stripped.
            for item in j["items"]:
                assert "generator_tokens_prompt" not in item
                assert "revoked_reason" not in item
                assert item["id"] == op.id
                assert item["stance"] == "agrees"
            r2 = await c.get(f"/v1/currents/{op.id}/sources")
            assert r2.status_code == 200
            src = r2.json()
            assert src, "sources should not be empty"
            assert any(s["source_id"] == "conc-capex" for s in src)

    asyncio.run(_hit_api())

    # 7. SSE fan-out: publish to the bus, confirm a subscriber receives it.
    async def _sse_roundtrip():
        gen = bus.subscribe()
        # Kick the subscribe generator once so its queue is registered with
        # the bus before we publish. We do this via a gather-style pattern:
        # start a consumer task, wait until the queue exists, publish, then
        # await.
        consumer = asyncio.create_task(gen.__anext__())
        # Wait for the subscribe generator to register — one yield cycle is
        # enough; the subscribe coroutine appends its queue synchronously
        # before its first ``await q.get()``.
        for _ in range(20):
            if bus.subscriber_count() >= 1:
                break
            await asyncio.sleep(0.01)
        assert bus.subscriber_count() >= 1
        bus.publish({"id": op.id, "stance": "agrees"})
        payload = await asyncio.wait_for(consumer, timeout=1.0)
        assert payload["id"] == op.id
        assert payload["stance"] == "agrees"
        await gen.aclose()

    asyncio.run(_sse_roundtrip())

    app.dependency_overrides.clear()
