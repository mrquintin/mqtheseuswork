"""Regression: revoked-source propagation.

The Store exposes ``revoke_opinion(id, reason)`` (prompt 01). The API's
``/v1/currents/{opinion_id}`` endpoint must surface ``revoked=true`` on the
response so the public UI can render a revocation badge.

This test covers opinion-level revocation (the real feature). Source-level
revocation (``revoke_conclusion``) does not exist on the Store today — the
invariant there is NOT covered by automated tests; see prompt-17 report for
the gap.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import httpx
import pytest

from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
    Speaker,
)
from noosphere.store import Store


UTC = timezone.utc


def _seed_opinion(store: Store) -> str:
    now = datetime.now(UTC)
    conc = Conclusion(id="conc-rev", text="Revocation target conclusion body.")
    claim = Claim(
        id="claim-rev",
        text="Revocation target claim body.",
        speaker=Speaker(name="Founder A"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )
    store.put_conclusion(conc)
    store.put_claim(claim)
    ev = CurrentEvent(
        id="evt-rev",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="some news",
        dedupe_hash="hash-rev",
        embedding=None,
        topic_hint="ai",
        status=CurrentEventStatus.OPINED,
    )
    store.add_current_event(ev)
    op = EventOpinion(
        id="op-rev",
        event_id=ev.id,
        generator_model="claude-haiku-4-5",
        generated_at=now,
        stance=OpinionStance.AGREES,
        confidence=0.7,
        headline="A sufficiently long headline for the revocation regression.",
        body_markdown="Body.",
        uncertainty_notes=[],
        sources_considered=2,
        sources_cited=2,
        generator_tokens_prompt=10,
        generator_tokens_completion=10,
    )
    citations = [
        OpinionCitation(
            id="cite-rev-0",
            opinion_id=op.id,
            conclusion_id="conc-rev",
            quoted_span="Revocation target conclusion body",
            relevance_score=0.9,
            ordinal=0,
        ),
        OpinionCitation(
            id="cite-rev-1",
            opinion_id=op.id,
            claim_id="claim-rev",
            quoted_span="Revocation target claim body",
            relevance_score=0.8,
            ordinal=1,
        ),
    ]
    store.add_event_opinion(op, citations)
    return op.id


def test_revoked_opinion_propagates_to_api(tmp_path) -> None:
    db_path = tmp_path / "rev.db"
    store = Store.from_database_url(f"sqlite:///{db_path}")
    op_id = _seed_opinion(store)

    # Baseline: opinion is NOT revoked.
    op_before = store.get_event_opinion(op_id)
    assert op_before is not None
    assert op_before.revoked is False

    # Revoke.
    store.revoke_opinion(op_id, reason="source withdrawn")

    op_after = store.get_event_opinion(op_id)
    assert op_after is not None
    assert op_after.revoked is True
    assert op_after.revoked_reason == "source withdrawn"

    # API: revoked=true propagates to /v1/currents/{id}.
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
            r = await c.get(f"/v1/currents/{op_id}")
            assert r.status_code == 200
            j = r.json()
            assert j["id"] == op_id
            assert j["revoked"] is True
            # Internal-only field MUST NOT leak to the public response.
            assert "revoked_reason" not in j

    asyncio.run(_hit_api())
    app.dependency_overrides.clear()
