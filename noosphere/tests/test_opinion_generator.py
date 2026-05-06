"""Currents opinion generator tests."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
SOURCE_TEXTS = {
    "conclusion_opinion_1": (
        "Theseus says durable compounding depends on disciplined evidence."
    ),
    "conclusion_opinion_2": (
        "Theseus says public claims should be constrained by the firm's actual "
        "memory."
    ),
    "conclusion_opinion_3": (
        "Theseus says current events deserve comment only when recorded "
        "reasoning applies."
    ),
}


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


def _seed(st: Store) -> tuple[str, list[Hit]]:
    for conclusion_id, text in SOURCE_TEXTS.items():
        st.put_conclusion(Conclusion(id=conclusion_id, text=text))
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
    hits = [
        Hit(
            source_kind="conclusion",
            source_id=conclusion_id,
            text=text,
            score=0.92,
            topic_hint="markets",
            origin=None,
        )
        for conclusion_id, text in SOURCE_TEXTS.items()
    ]
    return event_id, hits


def test_opinion_user_prompt_frames_x_posts_as_observed_posts() -> None:
    event = CurrentEvent(
        id="event_x_prompt",
        organization_id=ORG_ID,
        source=CurrentEventSource.X_TWITTER,
        external_id="1900000000000000000",
        author_handle="policy_feed",
        text="A city council member posted that a new school plan passed.",
        url="https://x.com/policy_feed/status/1900000000000000000",
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="education",
        dedupe_hash="event_x_prompt_hash",
    )
    hits = [
        Hit(
            source_kind="conclusion",
            source_id=conclusion_id,
            text=text,
            score=0.92,
            topic_hint="education",
            origin=None,
        )
        for conclusion_id, text in SOURCE_TEXTS.items()
    ]

    prompt = subject._opinion_user_prompt(event, hits)

    assert "OBSERVED X POST" in prompt
    assert "source: X_TWITTER" in prompt
    assert "external_id: 1900000000000000000" in prompt
    assert "author_handle: policy_feed" in prompt
    assert "source_url: https://x.com/policy_feed/status/1900000000000000000" in prompt
    assert "post_text:" in prompt
    assert "event_text:" not in prompt
    assert "Do not refer to an undefined event" in prompt
    assert "Do not use 'the event'" in prompt


def _payload(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "stance": "COMPLICATES",
        "confidence": 0.73,
        "headline": "The post complicates a compounding thesis",
        "body_markdown": (
            "The post can be assessed only within durable evidence "
            "[C:conclusion_opinion_1], "
            "actual memory [C:conclusion_opinion_2], and applicable recorded reasoning "
            "[C:conclusion_opinion_3]."
        ),
        "uncertainty_notes": ["single retrieved source"],
        "citations": [
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_1",
                "quoted_span": "durable compounding depends on disciplined evidence",
            },
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_2",
                "quoted_span": "constrained by the firm's actual memory",
            },
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_3",
                "quoted_span": "recorded reasoning applies",
            },
        ],
        "topic_hint": "markets",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_generate_opinion_happy_path_writes_opinion_and_citations(monkeypatch) -> None:
    st = _store()
    event_id, hits = _seed(st)
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
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
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
    assert len(citations) == 3
    inline_ids = set(re.findall(r"\[C:([^\]\s]+)\]", opinion.body_markdown))
    assert len(inline_ids) >= 3
    assert {
        "conclusion_opinion_1",
        "conclusion_opinion_2",
        "conclusion_opinion_3",
    }.issubset(inline_ids)
    assert st.get_current_event(event_id).status == CurrentEventStatus.OPINED  # type: ignore[union-attr]
    assert budget.charges == [(321, 123)]


def test_generate_opinion_retries_x_post_copy_that_says_the_event(
    monkeypatch,
) -> None:
    st = _store()
    for conclusion_id, text in SOURCE_TEXTS.items():
        st.put_conclusion(Conclusion(id=conclusion_id, text=text))
    event = CurrentEvent(
        id="event_x_subject",
        organization_id=ORG_ID,
        source=CurrentEventSource.X_TWITTER,
        external_id="1900000000000000000",
        author_handle="@policy_feed",
        text="A policy feed reports that a new school plan passed.",
        url="https://x.com/policy_feed/status/1900000000000000000",
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="education",
        dedupe_hash="event_x_subject_hash",
    )
    event_id = st.add_current_event(event)
    hits = [
        Hit(
            source_kind="conclusion",
            source_id=conclusion_id,
            text=text,
            score=0.92,
            topic_hint="education",
            origin=None,
        )
        for conclusion_id, text in SOURCE_TEXTS.items()
    ]
    budget = RecordingBudget()
    client = ScriptedClient(
        [
            LLMResponse(
                text=_payload(
                    headline="The event complicates a school thesis",
                    body_markdown=(
                        "The event can be assessed within durable evidence "
                        "[C:conclusion_opinion_1], actual memory "
                        "[C:conclusion_opinion_2], and recorded reasoning "
                        "[C:conclusion_opinion_3]."
                    ),
                ),
                prompt_tokens=100,
                completion_tokens=50,
                model="claude-haiku-4-5-test",
            ),
            LLMResponse(
                text=_payload(
                    headline="The post complicates a school thesis",
                    body_markdown=(
                        "The post can be assessed within durable evidence "
                        "[C:conclusion_opinion_1], actual memory "
                        "[C:conclusion_opinion_2], and recorded reasoning "
                        "[C:conclusion_opinion_3]."
                    ),
                ),
                prompt_tokens=110,
                completion_tokens=55,
                model="claude-haiku-4-5-test",
            ),
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(subject.generate_opinion(st, event_id, budget=budget))

    assert outcome == OpinionOutcome.PUBLISHED
    opinion = st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10)[0]
    assert "The event" not in opinion.headline
    assert "The event" not in opinion.body_markdown
    assert "X-post opinions must refer" in client.calls[1]["system"]


def test_generate_opinion_retries_then_abstains_on_citation_fabrication(
    monkeypatch,
) -> None:
    st = _store()
    event_id, hits = _seed(st)
    budget = RecordingBudget()
    invalid = _payload(
        citations=[
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_1",
                "quoted_span": "this span is not in the source",
            },
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_2",
                "quoted_span": "constrained by the firm's actual memory",
            },
            {
                "source_kind": "conclusion",
                "source_id": "conclusion_opinion_3",
                "quoted_span": "recorded reasoning applies",
            },
        ]
    )
    client = ScriptedClient(
        [
            LLMResponse(text=invalid, prompt_tokens=100, completion_tokens=20),
            LLMResponse(text=invalid, prompt_tokens=110, completion_tokens=21),
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(subject.generate_opinion(st, event_id, budget=budget))

    assert outcome == OpinionOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(client.calls) == 2
    assert "failed exact citation validation" in client.calls[1]["system"]
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]


def test_generate_opinion_budget_exhausted_makes_no_anthropic_call(monkeypatch) -> None:
    st = _store()
    event_id, hits = _seed(st)
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)

    def fail_make_client() -> None:
        raise AssertionError(
            "LLM client must not be constructed when budget is exhausted"
        )

    monkeypatch.setattr(subject, "make_client", fail_make_client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=ExhaustedBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_BUDGET
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]


def test_generate_opinion_llm_abstained_writes_no_opinion(monkeypatch) -> None:
    st = _store()
    event_id, hits = _seed(st)
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
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]


def test_generate_opinion_refuses_fewer_than_three_relevant_conclusions(
    monkeypatch,
) -> None:
    st = _store()
    event_id, hits = _seed(st)
    monkeypatch.setattr(
        subject,
        "retrieve_for_event",
        lambda *_args, **_kwargs: hits[:2],
    )

    def fail_make_client() -> None:
        raise AssertionError("LLM client must not be constructed without 3 Conclusions")

    monkeypatch.setattr(subject, "make_client", fail_make_client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10) == []
    assert st.get_current_event(event_id).status == CurrentEventStatus.ABSTAINED  # type: ignore[union-attr]
