"""Currents opinion tailer tests."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_EVENTS_API_SRC = REPO_ROOT / "current_events_api"
if str(CURRENT_EVENTS_API_SRC) not in sys.path:
    sys.path.insert(0, str(CURRENT_EVENTS_API_SRC))

from current_events_api.event_bus import OpinionBus  # noqa: E402
from current_events_api.metrics import Metrics  # noqa: E402
from current_events_api.publisher import OpinionTailer  # noqa: E402
from noosphere.models import (  # noqa: E402
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store  # noqa: E402


ORG_ID = "org_publisher_tail"
EVENT_ID = "event_publisher_tail"
OPINION_ID = "opinion_publisher_tail"
CONCLUSION_ID = "conclusion_publisher_tail"
SOURCE_TEXT = "Theseus says durable compounding depends on disciplined evidence."


def _seed_source_and_event(store: Store) -> None:
    store.put_conclusion(Conclusion(id=CONCLUSION_ID, text=SOURCE_TEXT))
    store.add_current_event(
        CurrentEvent(
            id=EVENT_ID,
            organization_id=ORG_ID,
            source=CurrentEventSource.MANUAL,
            external_id="external_publisher_tail",
            text="A public event raises questions about compounding.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            dedupe_hash="publisher_tail_hash",
        )
    )


def _insert_opinion(store: Store) -> None:
    store.add_event_opinion(
        EventOpinion(
            id=OPINION_ID,
            organization_id=ORG_ID,
            event_id=EVENT_ID,
            stance=OpinionStance.COMPLICATES,
            confidence=0.72,
            headline="The event complicates a compounding thesis",
            body_markdown="The source-grounded view is narrower than the headline.",
            uncertainty_notes=["single source"],
            topic_hint="markets",
            model_name="claude-haiku-4-5-test",
            prompt_tokens=123,
            completion_tokens=45,
            generated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(seconds=1),
        ),
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=CONCLUSION_ID,
                quoted_span="durable compounding",
                retrieval_score=0.91,
            )
        ],
    )


def test_opinion_tailer_publishes_inserted_opinion_within_interval(tmp_path) -> None:
    async def exercise() -> None:
        store = Store.from_database_url(f"sqlite:///{tmp_path / 'tailer.db'}")
        _seed_source_and_event(store)
        bus = OpinionBus()
        tailer = OpinionTailer(
            store=store,
            bus=bus,
            metrics=Metrics(),
            poll_seconds=0.01,
        )
        subscriber = bus.subscribe()
        next_item = asyncio.create_task(anext(subscriber))
        await asyncio.sleep(0)
        tailer.start()
        try:
            _insert_opinion(store)
            payload = await asyncio.wait_for(next_item, timeout=1.0)
        finally:
            if not next_item.done():
                next_item.cancel()
            await tailer.stop()
            await subscriber.aclose()

        assert payload["id"] == OPINION_ID
        assert payload["event_id"] == EVENT_ID
        assert payload["citations"][0]["source_id"] == CONCLUSION_ID

    asyncio.run(exercise())
