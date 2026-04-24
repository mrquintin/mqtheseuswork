"""Regression: follow-up rate limiting.

Two limits must both fire BEFORE any write-side effects:
1. ``RATE_LIMIT_PER_SESSION`` (8) user messages per session.
2. ``RATE_LIMIT_PER_FINGERPRINT_PER_DAY`` (20) user messages per 24h window
   for the fingerprint.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from noosphere.currents import followup as fu
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.followup import (
    RATE_LIMIT_PER_SESSION,
    RateLimitExceeded,
    answer_followup,
    compute_client_fingerprint,
    get_or_create_session,
)
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    FollowUpMessage,
    FollowUpMessageRole,
    OpinionStance,
    Speaker,
)
from noosphere.store import Store


UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _event() -> CurrentEvent:
    now = _now()
    return CurrentEvent(
        id="evt-rl",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="some news",
        dedupe_hash="hash-rl",
        embedding=None,
        topic_hint="ai",
        status=CurrentEventStatus.OPINED,
    )


def _opinion(event_id: str) -> EventOpinion:
    return EventOpinion(
        id="op-rl",
        event_id=event_id,
        generator_model="claude-haiku-4-5",
        generated_at=_now(),
        stance=OpinionStance.AGREES,
        confidence=0.7,
        headline="A sufficiently long headline for the rate-limit regression.",
        body_markdown="Body.",
        uncertainty_notes=[],
        sources_considered=1,
        sources_cited=0,
        generator_tokens_prompt=10,
        generator_tokens_completion=10,
    )


def _seed_session(store: Store):
    ev = _event()
    store.add_current_event(ev)
    op = _opinion(ev.id)
    store.add_event_opinion(op, [])
    fp = compute_client_fingerprint("1.2.3.4", "UA/1.0", _now())
    sess = get_or_create_session(store, opinion=op, client_fingerprint=fp)
    return ev, op, sess


def _seed_sources(store: Store) -> list[EventRetrievalHit]:
    conc = Conclusion(id="conc-rl", text="Some conclusion body text.")
    claim = Claim(
        id="claim-rl",
        text="Some claim body text.",
        speaker=Speaker(name="Founder A"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )
    store.put_conclusion(conc)
    store.put_claim(claim)
    return [
        EventRetrievalHit(
            source_kind="conclusion",
            source_id="conc-rl",
            text=conc.text,
            score=0.9,
        ),
        EventRetrievalHit(
            source_kind="claim",
            source_id="claim-rl",
            text=claim.text,
            score=0.6,
            origin="founder",
        ),
    ]


async def _consume(agen):
    return [c async for c in agen]


def test_session_cap_raises_before_persisting(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    ev, op, sess = _seed_session(store)
    _seed_sources(store)

    # Make retrieval a no-op so the test fails deterministically if the rate
    # check is ever bypassed (we'd otherwise get a "no_sources" refusal).
    monkeypatch.setattr(fu, "retrieve_for_event", lambda s, e, **kw: [])

    # Pre-seed RATE_LIMIT_PER_SESSION user messages on this session.
    base = _now()
    for i in range(RATE_LIMIT_PER_SESSION):
        store.add_followup_message(
            FollowUpMessage(
                id=f"pre_u_{i}",
                session_id=sess.id,
                role=FollowUpMessageRole.USER,
                created_at=base - timedelta(minutes=10 - i),
                content=f"pre question {i}",
            )
        )
    sess = store.get_followup_session(sess.id)

    async def run():
        return await _consume(
            answer_followup(
                store,
                session=sess,
                event=ev,
                opinion=op,
                user_question="one too many?",
                budget=HourlyBudgetGuard(
                    max_prompt_tokens=1_000_000, max_completion_tokens=1_000_000
                ),
            )
        )

    with pytest.raises(RateLimitExceeded) as excinfo:
        asyncio.run(run())
    assert str(excinfo.value) == "session_message_cap"

    # No user-message row was written by the blocked call.
    msgs = store.list_followup_messages(sess.id)
    assert len(msgs) == RATE_LIMIT_PER_SESSION


def test_daily_cap_raises_before_persisting(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    ev, op, sess = _seed_session(store)

    # Force the daily window count above 2*cap (40) so ``(total + 1) // 2``
    # crosses RATE_LIMIT_PER_FINGERPRINT_PER_DAY (20).
    monkeypatch.setattr(
        store,
        "count_followup_messages_in_window",
        lambda fp, *, since: 200,
    )
    # Retrieval should never be reached — no-op so a bypass is obvious.
    monkeypatch.setattr(fu, "retrieve_for_event", lambda s, e, **kw: [])

    async def run():
        return await _consume(
            answer_followup(
                store,
                session=sess,
                event=ev,
                opinion=op,
                user_question="still more?",
                budget=HourlyBudgetGuard(
                    max_prompt_tokens=1_000_000, max_completion_tokens=1_000_000
                ),
            )
        )

    with pytest.raises(RateLimitExceeded) as excinfo:
        asyncio.run(run())
    assert str(excinfo.value) == "daily_cap"

    msgs = store.list_followup_messages(sess.id)
    assert msgs == []
