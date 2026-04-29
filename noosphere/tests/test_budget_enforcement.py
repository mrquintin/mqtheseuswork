from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import pytest

from noosphere.currents import opinion_generator as subject
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.models import Conclusion, CurrentEvent, CurrentEventSource
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


def test_budget_exhaustion_prevents_llm_call(monkeypatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    conclusion = Conclusion(id="conclusion_budget", text=SOURCE_TEXT)
    store.put_conclusion(conclusion)
    event_id = store.add_current_event(
        CurrentEvent(
            id="event_budget",
            organization_id="org_budget",
            source=CurrentEventSource.MANUAL,
            external_id="event_budget",
            text="A headline about compounding discipline.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            dedupe_hash="event_budget_hash",
        )
    )
    hit = Hit("conclusion", conclusion.id, SOURCE_TEXT, 0.91)
    budget = HourlyBudgetGuard(max_prompt_tokens=20_000, max_completion_tokens=10_000)
    budget.charge(9_000, 6_500)
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])
    monkeypatch.setattr(
        subject,
        "make_client",
        lambda: pytest.fail("LLM must not be called once budget is exhausted"),
    )

    outcome = asyncio.run(subject.generate_opinion(store, event_id, budget=budget))

    assert outcome == OpinionOutcome.ABSTAINED_BUDGET
    assert store.list_recent_opinions("org_budget", datetime(2026, 1, 1), 10) == []
