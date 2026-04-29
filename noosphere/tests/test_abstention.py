from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from noosphere.currents import opinion_generator as subject
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.models import CurrentEvent, CurrentEventSource, CurrentEventStatus
from noosphere.store import Store


ORG_ID = "org_abstention"


def test_empty_noosphere_abstains_without_calling_llm(monkeypatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    event_id = store.add_current_event(
        CurrentEvent(
            id="event_abstention",
            organization_id=ORG_ID,
            source=CurrentEventSource.MANUAL,
            external_id="event_abstention",
            text="A headline with no grounded Theseus source.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            dedupe_hash="event_abstention_hash",
        )
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        subject,
        "make_client",
        lambda: pytest.fail("LLM must not be called without retrieved sources"),
    )

    outcome = asyncio.run(
        subject.generate_opinion(store, event_id, budget=object())
    )

    assert outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert store.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]
