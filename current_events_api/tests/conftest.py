from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
NOOSPHERE_SRC = REPO_ROOT / "noosphere"
if str(NOOSPHERE_SRC) not in sys.path:
    sys.path.insert(0, str(NOOSPHERE_SRC))

from noosphere.models import (  # noqa: E402
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store  # noqa: E402


SOURCE_TEXT = "Theseus says durable compounding depends on disciplined evidence."
ORG_ID = "org_currents_api"
EVENT_ID = "event_currents_api"
OPINION_ID = "opinion_currents_api"
CONCLUSION_ID = "conclusion_currents_api"

sys.modules.setdefault("current_events_api_tests_support", sys.modules[__name__])


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'currents.db'}")
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    from current_events_api.main import app

    with TestClient(app) as test_client:
        yield test_client


def seed_opinion(store: Store, *, opinion_id: str = OPINION_ID) -> str:
    conclusion = Conclusion(id=CONCLUSION_ID, text=SOURCE_TEXT)
    store.put_conclusion(conclusion)
    event = CurrentEvent(
        id=EVENT_ID,
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id="external_currents_api",
        author_handle="theseus",
        text="A public event raises questions about compounding.",
        url="https://example.test/event",
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="markets",
        dedupe_hash=f"{opinion_id}_dedupe",
    )
    store.add_current_event(event)
    opinion = EventOpinion(
        id=opinion_id,
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
    )
    store.add_event_opinion(
        opinion,
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="durable compounding",
                retrieval_score=0.91,
            )
        ],
    )
    return opinion_id
