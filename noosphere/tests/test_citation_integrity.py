from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from fakes.fake_anthropic_client import FakeAnthropicClient
from noosphere.currents import opinion_generator as subject
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
)
from noosphere.store import Store


SOURCE_TEXT = "Theseus says durable compounding depends on disciplined evidence."


@dataclass(frozen=True)
class Hit:
    source_kind: str
    source_id: str
    text: str
    score: float
    topic_hint: str | None = None
    origin: str | None = None


def test_non_verbatim_citation_retries_then_abstains(monkeypatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    conclusion = Conclusion(id="conclusion_citation", text=SOURCE_TEXT)
    store.put_conclusion(conclusion)
    event_id = store.add_current_event(
        CurrentEvent(
            id="event_citation",
            organization_id="org_citation",
            source=CurrentEventSource.MANUAL,
            external_id="event_citation",
            text="A headline about compounding discipline.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            dedupe_hash="event_citation_hash",
        )
    )
    hit = Hit("conclusion", conclusion.id, SOURCE_TEXT, 0.91)
    invalid = {
        "stance": "COMPLICATES",
        "confidence": 0.7,
        "headline": "A non-verbatim citation must fail",
        "body_markdown": "This should not publish.",
        "uncertainty_notes": ["invalid citation"],
        "citations": [
            {
                "source_kind": "conclusion",
                "source_id": conclusion.id,
                "quoted_span": "this span is not in the source",
            }
        ],
        "topic_hint": "markets",
    }
    fake_llm = FakeAnthropicClient(script=[invalid, invalid])
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])
    monkeypatch.setattr(subject, "make_client", lambda: fake_llm)

    outcome = asyncio.run(subject.generate_opinion(store, event_id, budget=object()))

    assert outcome == OpinionOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(fake_llm.calls) == 2
    assert "failed exact citation validation" in fake_llm.calls[1]["system"]
    assert store.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]
    assert store.list_recent_opinions("org_citation", datetime(2026, 1, 1), 10) == []
