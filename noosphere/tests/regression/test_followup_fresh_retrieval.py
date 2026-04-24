"""Regression: follow-up fresh retrieval.

Every follow-up question triggers a NEW ``retrieve_for_event`` call. The
engine must NOT reuse the opinion's citations as the sole grounding set,
because the user's question may be about a tangent not covered by the
opinion's own citations.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest

from noosphere.currents import followup as fu
from noosphere.currents._llm_client import LLMStreamChunk
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.followup import (
    answer_followup,
    compute_client_fingerprint,
    get_or_create_session,
)
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store


UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_two_conclusions(store: Store):
    """Two topic-disjoint conclusions A and B."""
    conc_a = Conclusion(
        id="conc-A",
        text="Topic A conclusion body about monetary policy and interest rates.",
    )
    conc_b = Conclusion(
        id="conc-B",
        text="Topic B conclusion body about AI compute and semiconductor capex.",
    )
    store.put_conclusion(conc_a)
    store.put_conclusion(conc_b)
    return conc_a, conc_b


def _event() -> CurrentEvent:
    now = _now()
    return CurrentEvent(
        id="evt-fresh",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="some news",
        dedupe_hash="hash-fresh",
        embedding=None,
        topic_hint="mixed",
        status=CurrentEventStatus.OPINED,
    )


def _opinion(event_id: str) -> EventOpinion:
    return EventOpinion(
        id="op-fresh",
        event_id=event_id,
        generator_model="claude-haiku-4-5",
        generated_at=_now(),
        stance=OpinionStance.AGREES,
        confidence=0.7,
        headline="A sufficiently long headline for the fresh-retrieval regression.",
        body_markdown="Body.",
        uncertainty_notes=[],
        sources_considered=1,
        sources_cited=1,
        generator_tokens_prompt=10,
        generator_tokens_completion=10,
    )


def _citation_on_a(opinion_id: str) -> OpinionCitation:
    return OpinionCitation(
        id="cite-fresh-0",
        opinion_id=opinion_id,
        conclusion_id="conc-A",
        quoted_span="monetary policy and interest rates",
        relevance_score=0.9,
        ordinal=0,
    )


async def _consume(agen):
    return [c async for c in agen]


def _scripted_stream(monkeypatch: pytest.MonkeyPatch, text: str) -> dict:
    state: dict = {"calls": 0, "last_user": None}

    async def _agen(*, system, user, model="claude-haiku-4-5", max_tokens=600,
                    api_key=None, client=None):
        state["calls"] += 1
        state["last_user"] = user
        yield LLMStreamChunk(
            text_delta=text, tokens_prompt_so_far=1, tokens_completion_so_far=1
        )

    monkeypatch.setattr(fu, "chat_stream_text", _agen)
    return state


def test_followup_calls_retrieval_and_can_return_non_cited_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    conc_a, conc_b = _seed_two_conclusions(store)
    ev = _event()
    store.add_current_event(ev)
    op = _opinion(ev.id)
    store.add_event_opinion(op, [_citation_on_a(op.id)])
    fp = compute_client_fingerprint("1.2.3.4", "UA/1.0", _now())
    sess = get_or_create_session(store, opinion=op, client_fingerprint=fp)

    # Verify: opinion's citations reference ONLY A.
    cited_ids = {
        c.conclusion_id for c in store.list_citations_for_opinion(op.id) if c.conclusion_id
    }
    assert cited_ids == {"conc-A"}

    # Spy retrieval that returns B (and A), even though the opinion only
    # cited A. A correct follow-up engine must use the returned hit list
    # rather than the opinion's citations.
    spy_calls: list[tuple] = []

    def _retrieve(store_arg, event_arg, **kwargs):
        spy_calls.append((event_arg.id, kwargs))
        return [
            EventRetrievalHit(
                source_kind="conclusion",
                source_id="conc-B",
                text=conc_b.text[:400],
                score=0.88,
            ),
            EventRetrievalHit(
                source_kind="conclusion",
                source_id="conc-A",
                text=conc_a.text[:400],
                score=0.60,
            ),
        ]

    monkeypatch.setattr(fu, "retrieve_for_event", _retrieve)

    state = _scripted_stream(
        monkeypatch,
        text=(
            "The firm's Noosphere addresses AI compute and semiconductor capex. "
            "See prior conclusion.\n"
            "[[CITE: source_kind=conclusion source_id=conc-B "
            'quoted="AI compute and semiconductor capex"]]'
        ),
    )

    async def run():
        return await _consume(
            answer_followup(
                store,
                session=sess,
                event=ev,
                opinion=op,
                user_question="Does the firm have views on AI compute capex?",
                budget=HourlyBudgetGuard(
                    max_prompt_tokens=1_000_000, max_completion_tokens=1_000_000
                ),
            )
        )

    chunks = asyncio.run(run())

    # 1. retrieval was called for this event (fresh retrieval invariant).
    assert len(spy_calls) == 1
    assert spy_calls[0][0] == ev.id

    # 2. The retrieval returned B, which is NOT in the opinion's citations.
    #    The engine must have used it: the SOURCES block passed to the LLM
    #    contains B's id.
    assert state["calls"] == 1
    user_prompt = state["last_user"]
    assert user_prompt is not None
    assert "conc-B" in user_prompt

    # 3. The final chunk validated the B citation — proving the fresh
    #    retrieval's hit set was what citation validation ran against,
    #    not the opinion's (conc-A-only) citations.
    final = chunks[-1]
    assert final.done is True
    assert final.refused is False
    assert any(c.conclusion_id == "conc-B" for c in final.citations)
