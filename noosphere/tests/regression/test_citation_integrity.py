"""Regression: citation integrity.

If the LLM fabricates a ``quoted_span`` that does not appear verbatim in the
cited source's stored body, the generator must retry, then abstain — no
opinion row is written.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from noosphere.currents import opinion_generator as og
from noosphere.currents._llm_client import LLMReply
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    Speaker,
)
from noosphere.store import Store


UTC = timezone.utc


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_sources(store: Store) -> list[EventRetrievalHit]:
    conc = Conclusion(
        id="conc-capex",
        text=(
            "AI compute demand drives chip capex across the semiconductor "
            "industry. Orders reflect expectations of sustained inference load."
        ),
    )
    claim_f = Claim(
        id="claim-F",
        text="Founders believe AI adoption accelerates compounding returns.",
        speaker=Speaker(name="Founder A"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )
    store.put_conclusion(conc)
    store.put_claim(claim_f)
    return [
        EventRetrievalHit(
            source_kind="conclusion",
            source_id="conc-capex",
            text=conc.text[:400],
            score=0.91,
        ),
        EventRetrievalHit(
            source_kind="claim",
            source_id="claim-F",
            text=claim_f.text[:300],
            score=0.55,
            origin="founder",
        ),
    ]


def _event() -> CurrentEvent:
    now = datetime.now(UTC)
    return CurrentEvent(
        id="evt-fabrication",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="Some capex news",
        dedupe_hash="hash-fab",
        embedding=None,
        topic_hint="ai",
        status=CurrentEventStatus.OBSERVED,
    )


def _fabricated_reply() -> str:
    return json.dumps(
        {
            "stance": "agrees",
            "confidence": 0.6,
            "headline": "The firm's prior conclusion on capex aligns with today's announcement news.",
            "body_markdown": "Body referencing the cited conclusion body.",
            "uncertainty_notes": [],
            "citations": [
                {
                    "source_kind": "conclusion",
                    "source_id": "conc-capex",
                    "quoted_span": "this exact span does not appear in the stored conclusion",
                    "relevance_score": 0.8,
                }
            ],
        }
    )


def test_fabricated_quote_abstains_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()
    hits = _seed_sources(store)
    ev = _event()
    store.add_current_event(ev)

    monkeypatch.setattr(og, "retrieve_for_event", lambda s, e, **kw: list(hits))

    call_log: list[dict] = []

    def _chat(*, system, user, model="claude-haiku-4-5", max_tokens=900, api_key=None, client=None):
        call_log.append({"system": system, "user": user})
        text = _fabricated_reply()
        return LLMReply(
            text=text,
            tokens_prompt=(len(system) + len(user)) // 4,
            tokens_completion=max(1, len(text) // 4),
            model=model,
        )

    monkeypatch.setattr(og, "chat_json", _chat)

    budget = HourlyBudgetGuard(
        max_prompt_tokens=10_000_000, max_completion_tokens=10_000_000
    )
    outcome = generate_opinion(store, ev, budget=budget, max_retries=2)

    assert outcome == OpinionOutcome.ABSTAINED_CITATION_FABRICATION
    # 1 initial + 2 retries = 3 calls.
    assert len(call_log) == 3
    # No opinion row written.
    assert store.list_opinions_for_event(ev.id) == []
    # Event flipped to ABSTAINED.
    ev_after = store.get_current_event(ev.id)
    assert ev_after is not None
    assert ev_after.status == CurrentEventStatus.ABSTAINED
