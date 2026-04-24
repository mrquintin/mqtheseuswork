"""OpinionTailer tests (prompt 15).

The tailer polls the Store for new EventOpinion rows and pushes a dict
payload onto the bus. We use a real SQLite-in-memory store and a fake bus
that records published payloads.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from noosphere.currents.publisher import OpinionTailer
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store


UTC = timezone.utc


class FakeBus:
    def __init__(self):
        self.payloads: list[dict] = []

    def publish(self, payload: dict) -> None:
        self.payloads.append(payload)


def _store(tmp_path) -> Store:
    # File-backed SQLite so the tailer's worker thread (via
    # asyncio.to_thread) can open its own connection and still see the
    # schema/rows created by the test thread.
    db = tmp_path / "noosphere.db"
    return Store.from_database_url(f"sqlite:///{db}")


def _event(event_id: str, now: datetime) -> CurrentEvent:
    return CurrentEvent(
        id=event_id,
        source=CurrentEventSource.X_POST,
        source_url=f"https://x.com/foo/status/{event_id}",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text=f"raw {event_id}",
        dedupe_hash=f"dedupe-{event_id}",
        topic_hint="ai",
        status=CurrentEventStatus.OPINED,
    )


def _opinion(opinion_id: str, event_id: str, generated_at: datetime) -> EventOpinion:
    return EventOpinion(
        id=opinion_id,
        event_id=event_id,
        generator_model="claude-haiku-4-5",
        generated_at=generated_at,
        stance=OpinionStance.AGREES,
        confidence=0.8,
        headline="H" * 40,
        body_markdown="Body.",
        uncertainty_notes=[],
        sources_considered=1,
        sources_cited=1,
        generator_tokens_prompt=1,
        generator_tokens_completion=1,
    )


def test_tailer_publishes_new_opinions(tmp_path):
    async def _go():
        store = _store(tmp_path)
        bus = FakeBus()
        t0 = datetime.now(UTC)
        store.add_current_event(_event("evt-1", t0))

        tailer = OpinionTailer(store, bus, interval=0.05)
        await tailer.start()
        try:
            # Insert an opinion strictly after the tailer's cursor.
            await asyncio.sleep(0.02)
            op_generated = datetime.now(UTC)
            store.add_event_opinion(_opinion("op-1", "evt-1", op_generated), [])
            # Give the tailer at least one poll cycle.
            for _ in range(40):
                await asyncio.sleep(0.05)
                if bus.payloads:
                    break
        finally:
            await tailer.stop()

        assert any(p.get("id") == "op-1" for p in bus.payloads)
        payload = next(p for p in bus.payloads if p["id"] == "op-1")
        assert payload["event_id"] == "evt-1"
        assert payload["stance"] == "agrees"
        assert payload["event_source_url"].startswith("https://x.com/")

    asyncio.run(_go())


def test_tailer_does_not_replay_pre_start_opinions(tmp_path):
    async def _go():
        store = _store(tmp_path)
        bus = FakeBus()
        t0 = datetime.now(UTC)
        store.add_current_event(_event("evt-old", t0))
        # Insert an opinion BEFORE the tailer starts — it must not appear.
        store.add_event_opinion(_opinion("op-old", "evt-old", t0), [])

        tailer = OpinionTailer(store, bus, interval=0.05)
        await tailer.start()
        try:
            for _ in range(8):
                await asyncio.sleep(0.05)
        finally:
            await tailer.stop()

        assert all(p.get("id") != "op-old" for p in bus.payloads)

    asyncio.run(_go())


def test_tailer_advances_cursor_between_polls(tmp_path):
    async def _go():
        store = _store(tmp_path)
        bus = FakeBus()
        store.add_current_event(_event("evt-a", datetime.now(UTC)))
        store.add_current_event(_event("evt-b", datetime.now(UTC)))

        tailer = OpinionTailer(store, bus, interval=0.05)
        await tailer.start()
        try:
            await asyncio.sleep(0.02)
            store.add_event_opinion(
                _opinion("op-a", "evt-a", datetime.now(UTC)), []
            )
            for _ in range(40):
                await asyncio.sleep(0.05)
                if any(p["id"] == "op-a" for p in bus.payloads):
                    break
            store.add_event_opinion(
                _opinion("op-b", "evt-b", datetime.now(UTC)), []
            )
            for _ in range(40):
                await asyncio.sleep(0.05)
                if any(p["id"] == "op-b" for p in bus.payloads):
                    break
        finally:
            await tailer.stop()

        ids = [p["id"] for p in bus.payloads]
        # At-least-once delivery: we require each id to appear at least once
        # without dropping. Duplicates would be acceptable but we do not
        # expect any given the single-cursor design.
        assert "op-a" in ids
        assert "op-b" in ids

    asyncio.run(_go())
