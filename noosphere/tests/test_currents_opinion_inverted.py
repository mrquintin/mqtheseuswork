"""Currents opinion generator tests for event-first inversion."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from noosphere.currents import opinion_generator as subject
from noosphere.currents._llm_client import LLMResponse
from noosphere.currents.opinion_generator import (
    MIN_CONCLUSION_SCORE,
    OpinionOutcome,
)
from noosphere.models import (
    AbstentionReason,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    OpinionStance,
    XSignificanceMetrics,
)
from noosphere.store import Store

ORG_ID = "org_currents_opinion_inverted"
EVENT_TEXT = (
    "A widely shared X post says a city pension fund shifted into AI "
    "infrastructure."
)
SOURCE_TEXTS = {
    "conclusion_inverted_1": (
        "Theseus says public capital allocation should be judged by durable "
        "institutional discipline."
    ),
    "conclusion_inverted_2": (
        "Theseus says technological enthusiasm is not a substitute for "
        "measured compounding evidence."
    ),
    "conclusion_inverted_3": (
        "Theseus says institutional claims should stay tethered to concrete "
        "operating incentives."
    ),
}


@dataclass(frozen=True)
class Hit:
    source_kind: str
    source_id: str
    text: str
    score: float
    topic_hint: str | None = None
    origin: str | None = None
    source_upload_ids: tuple[str, ...] = ()


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
    def authorize(self, _est_prompt: int, _est_completion: int) -> None:
        return None

    def charge(self, _prompt: int, _completion: int) -> None:
        return None


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _metrics() -> XSignificanceMetrics:
    return XSignificanceMetrics(
        like_count=1_200,
        retweet_count=320,
        reply_count=80,
        quote_count=25,
        bookmark_count=140,
        impression_count=88_000,
    )


def _event(
    *,
    event_id: str = "event_inverted",
    dedupe_hash: str = "event_inverted_hash",
) -> CurrentEvent:
    return CurrentEvent(
        id=event_id,
        organization_id=ORG_ID,
        source=CurrentEventSource.X_TWITTER,
        external_id="1900000000000000001",
        author_handle="civic_alpha",
        text=EVENT_TEXT,
        url="https://x.com/civic_alpha/status/1900000000000000001",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        metrics=_metrics(),
        topic_hint="public finance",
        dedupe_hash=dedupe_hash,
    )


def _seed(st: Store) -> tuple[str, list[Hit]]:
    for conclusion_id, text in SOURCE_TEXTS.items():
        st.put_conclusion(Conclusion(id=conclusion_id, text=text))
    event_id = st.add_current_event(_event())
    return event_id, [
        Hit(
            source_kind="conclusion",
            source_id=conclusion_id,
            text=text,
            score=0.93,
            topic_hint="public finance",
        )
        for conclusion_id, text in SOURCE_TEXTS.items()
    ]


def _payload() -> str:
    return json.dumps(
        {
            "stance": "COMPLICATES",
            "confidence": 0.74,
            "headline": "The post complicates the AI-infrastructure enthusiasm",
            "body_markdown": (
                "The post should be judged by durable institutional discipline "
                "[C:conclusion_inverted_1], measured compounding evidence "
                "[C:conclusion_inverted_2], and concrete operating incentives "
                "[C:conclusion_inverted_3]."
            ),
            "uncertainty_notes": [
                "The post alone does not prove fund-level causality."
            ],
            "citations": [
                {
                    "source_kind": "conclusion",
                    "source_id": "conclusion_inverted_1",
                    "quoted_span": "durable institutional discipline",
                },
                {
                    "source_kind": "conclusion",
                    "source_id": "conclusion_inverted_2",
                    "quoted_span": "measured compounding evidence",
                },
                {
                    "source_kind": "conclusion",
                    "source_id": "conclusion_inverted_3",
                    "quoted_span": "concrete operating incentives",
                },
            ],
            "topic_hint": "public finance",
        }
    )


def test_prompt_sent_to_llm_leads_with_event_metadata_and_metrics(monkeypatch) -> None:
    st = _store()
    event_id, hits = _seed(st)
    client = ScriptedClient(
        [
            LLMResponse(
                text=_payload(),
                prompt_tokens=210,
                completion_tokens=90,
                model="claude-haiku-4-5-test",
            )
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.PUBLISHED
    prompt = client.calls[0]["user"]
    assert prompt.startswith("TRENDING EVENT SUBJECT (X POST)\n")
    assert "author_handle: civic_alpha" in prompt
    assert "observed_at: 2026-05-07 12:00:00" in prompt
    assert "significance_score:" in prompt
    assert "retweet_count: 320" in prompt
    assert "post_text:" in prompt
    assert prompt.index(EVENT_TEXT) < prompt.index(
        "FIRM PRIOR CONCLUSIONS AS COMMENTARY VOICE"
    )
    assert prompt.index("significance_score:") < prompt.index("[FIRM CONCLUSION 1]")
    assert (
        "Comment on the event using the firm's prior conclusions; do not "
        "pretend the conclusions caused the event."
    ) in prompt


def test_zero_qualifying_hits_abstains_off_domain_with_reason(monkeypatch) -> None:
    st = _store()
    event_id = st.add_current_event(
        _event(event_id="event_low_hits", dedupe_hash="event_low_hits_hash")
    )
    low_hits = [
        Hit(
            source_kind="conclusion",
            source_id=f"generic_{idx}",
            text="A generic institutional comment with no concrete topical fit.",
            score=MIN_CONCLUSION_SCORE - 0.01,
        )
        for idx in range(3)
    ]
    monkeypatch.setattr(
        subject,
        "retrieve_for_event",
        lambda *_args, **_kwargs: low_hits,
    )
    monkeypatch.setattr(
        subject,
        "make_client",
        lambda: pytest.fail("LLM must not be called for off-domain KB hits"),
    )

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.ABSTAINED_OFF_DOMAIN
    event = st.get_current_event(event_id)
    assert event is not None
    assert event.status == CurrentEventStatus.ABSTAINED
    opinions = st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10)
    assert len(opinions) == 1
    assert opinions[0].stance == OpinionStance.ABSTAINED
    assert opinions[0].abstention_reason == AbstentionReason.ABSTAIN_OFF_DOMAIN


def test_persisted_citations_match_prompt_hits_and_include_metric_metadata(
    monkeypatch,
) -> None:
    st = _store()
    event_id, hits = _seed(st)
    client = ScriptedClient(
        [
            LLMResponse(
                text=_payload(),
                prompt_tokens=210,
                completion_tokens=90,
                model="claude-haiku-4-5-test",
            )
        ]
    )
    monkeypatch.setattr(subject, "retrieve_for_event", lambda *_args, **_kwargs: hits)
    monkeypatch.setattr(subject, "make_client", lambda: client)

    outcome = asyncio.run(
        subject.generate_opinion(st, event_id, budget=RecordingBudget())
    )

    assert outcome == OpinionOutcome.PUBLISHED
    prompt = client.calls[0]["user"]
    prompt_hit_ids = {
        hit.source_id
        for hit in hits
        if f"citation_token: [C:{hit.source_id}]" in prompt
    }
    opinions = st.list_recent_opinions(ORG_ID, datetime(2026, 1, 1), 10)
    assert len(opinions) == 1
    for opinion in opinions:
        citations = st.list_opinion_citations(opinion.id)
        assert citations
        assert any(citation.conclusion_id in prompt_hit_ids for citation in citations)
        assert {
            citation.conclusion_id for citation in citations
        }.issubset(prompt_hit_ids)
        for citation in citations:
            metadata = citation.justification_metadata
            assert metadata["primary_event_metric"] == "significance_score"
            assert "significance_score" in metadata["event_metrics"]
            assert metadata["event_metrics"]["retweet_count"] == 320
