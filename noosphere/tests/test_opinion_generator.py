"""Currents opinion generator tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from noosphere.currents import opinion_generator as subject
from noosphere.currents._llm_client import LLMResponse
from noosphere.currents.budget import BudgetExhausted
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    OpinionStance,
)
from noosphere.store import Store


ORG_ID = "org_opinion_generator"
SOURCE_TEXT = "Theseus says durable compounding depends on disciplined evidence."


@dataclass(frozen=True)
class Hit:
    source_kind: str
    source_id: str
    text: str
    score: float
    topic_hint: str | None
    origin: str | None


class ScriptedClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("no scripted LLM response left")
        return self.responses.pop(0)


class RecordingBudget:
    def __init__(self) -> None:
        self.authorizations: list[tuple[int, int]] = []
        self.charges: list[tuple[int, int]] = []

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        self.authorizations.append((est_prompt, est_completion))

    def charge(self, prompt: int, completion: int) -> None:
        self.charges.append((prompt, completion))


class ExhaustedBudget(RecordingBudget):
    def authorize(self, est_prompt: int, est_completion: int) -> None:
        super().authorize(est_prompt, est_completion)
        raise BudgetExhausted("test budget exhausted")


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed(st: Store) -> tuple[str, Hit]:
    conclusion = Conclusion(id="conclusion_opinion", text=SOURCE_TEXT)
    st.put_conclusion(conclusion)
    event = CurrentEvent(
        id="event_opinion",
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id="external_opinion",
        text="A public event raises questions about compounding.",
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="markets",
        dedupe_hash="event_opinion_hash",
    )
    event_id = st.add_current_event(event)
    hit = Hit(
        source_kind="conclusion",
        source_id=conclusion.id,
        text=SOURCE_TEXT,
        score=0.92,
        topic_hint="markets",
        origin=None,
    )
    return event_id, hit


def _payload(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "stance": "COMPLICATES",
        "confidence": 0.73,
        "headline": "The event complicates a compounding thesis",
        "body_markdown": "The source supports a narrower view of the event.",
        "uncertainty_notes": ["single retrieved source"],
        "citations": [
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion",
                "quoted_span": "durable compounding depends on disciplined evidence",
            }
        ],
        "topic_hint": "markets",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_generate_opinion_happy_path_writes_opinion_and_citations(monkeypatch) -> None:
    st = _store()
    event_id, hit = _seed(st)
    budget = RecordingBudget()
    client = ScriptedClient(
        [
            LLMResponse(
                text=_payload(),
                prompt_tokens=321,
                completion_tokens=123,
                model="claude-haiku-4-5-test",
            )
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(subject.generate_opinion(st, event_id, budget=budget))

    assert outcome == OpinionOutcome.PUBLISHED
    opinions = st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10)
    assert len(opinions) == 1
    opinion = opinions[0]
    assert opinion.stance == OpinionStance.COMPLICATES
    assert opinion.prompt_tokens == 321
    assert opinion.completion_tokens == 123
    citations = st.list_opinion_citations(opinion.id)
    assert len(citations) == 1
    assert citations[0].quoted_span == "durable compounding depends on disciplined evidence"
    assert st.get_current_event(event_id).status == CurrentEventStatus.OPINED  # type: ignore[union-attr]
    assert budget.charges == [(321, 123)]


def test_generate_opinion_retries_then_abstains_on_citation_fabrication(monkeypatch) -> None:
    st = _store()
    event_id, hit = _seed(st)
    budget = RecordingBudget()
    invalid = _payload(
        citations=[
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion",
                "quoted_span": "this span is not in the source",
            }
        ]
    )
    client = ScriptedClient(
        [
            LLMResponse(text=invalid, prompt_tokens=100, completion_tokens=20),
            LLMResponse(text=invalid, prompt_tokens=110, completion_tokens=21),
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(subject.generate_opinion(st, event_id, budget=budget))

    assert outcome == OpinionOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(client.calls) == 2
    assert "failed exact citation validation" in client.calls[1]["system"]
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]


def test_generate_opinion_budget_exhausted_makes_no_anthropic_call(monkeypatch) -> None:
    st = _store()
    event_id, hit = _seed(st)
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])

    def fail_make_client() -> None:
        raise AssertionError("LLM client must not be constructed when budget is exhausted")

    monkeypatch.setattr(subject, "make_client", fail_make_client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=ExhaustedBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_BUDGET
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]


def test_generate_opinion_llm_abstained_writes_no_opinion(monkeypatch) -> None:
    st = _store()
    event_id, hit = _seed(st)
    client = ScriptedClient(
        [
            LLMResponse(
                text=_payload(
                    stance="ABSTAINED",
                    confidence=0,
                    citations=[],
                    uncertainty_notes=["sources do not support a position"],
                ),
                prompt_tokens=77,
                completion_tokens=18,
            )
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: [hit])
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]
