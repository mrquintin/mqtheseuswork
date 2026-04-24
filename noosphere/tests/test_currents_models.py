"""Tests for the Currents (Wave 1) data model: CurrentEvent, EventOpinion,
OpinionCitation, FollowUpSession, FollowUpMessage, and their Store accessors.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from noosphere.ids import (
    make_citation_id,
    make_event_id,
    make_followup_message_id,
    make_followup_session_id,
    make_opinion_id,
)
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    FollowUpMessage,
    FollowUpMessageRole,
    FollowUpSession,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_event(
    *,
    dedupe: str = "abc",
    status: CurrentEventStatus = CurrentEventStatus.OBSERVED,
    embedding=None,
    topic_hint=None,
) -> CurrentEvent:
    eid = make_event_id(dedupe)
    return CurrentEvent(
        id=eid,
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=_now(),
        ingested_at=_now(),
        raw_text="hello world",
        dedupe_hash=dedupe,
        embedding=embedding,
        topic_hint=topic_hint,
        status=status,
    )


def _make_opinion(event_id: str, *, gen_iso: str = "2026-04-20T00:00:00+00:00") -> EventOpinion:
    oid = make_opinion_id(event_id, "claude-opus", gen_iso)
    return EventOpinion(
        id=oid,
        event_id=event_id,
        generator_model="claude-opus",
        generated_at=datetime.fromisoformat(gen_iso),
        stance=OpinionStance.AGREES,
        confidence=0.75,
        headline="A headline",
        body_markdown="Body here.",
        uncertainty_notes=["note-1"],
        sources_considered=5,
        sources_cited=3,
        generator_tokens_prompt=100,
        generator_tokens_completion=250,
    )


def test_current_event_roundtrip() -> None:
    store = _store()

    # Case 1: both embedding and topic_hint null.
    ev_null = _make_event(dedupe="hash-null", embedding=None, topic_hint=None)
    store.add_current_event(ev_null)
    got_null = store.get_current_event(ev_null.id)
    assert got_null is not None
    assert got_null.id == ev_null.id
    assert got_null.source == ev_null.source
    assert got_null.source_url == ev_null.source_url
    assert got_null.source_author_handle == ev_null.source_author_handle
    assert got_null.source_captured_at == ev_null.source_captured_at
    assert got_null.ingested_at == ev_null.ingested_at
    assert got_null.raw_text == ev_null.raw_text
    assert got_null.dedupe_hash == ev_null.dedupe_hash
    assert got_null.embedding is None
    assert got_null.topic_hint is None
    assert got_null.status == ev_null.status
    assert got_null.status_reason is None

    # Case 2: both embedding and topic_hint populated.
    ev_full = _make_event(
        dedupe="hash-full",
        embedding=[0.1, 0.2, 0.3, 0.4],
        topic_hint="ai-safety",
    )
    store.add_current_event(ev_full)
    got_full = store.get_current_event(ev_full.id)
    assert got_full is not None
    assert got_full.embedding == [0.1, 0.2, 0.3, 0.4]
    assert got_full.topic_hint == "ai-safety"


def test_dedupe_lookup() -> None:
    store = _store()
    ev = _make_event(dedupe="unique-hash-123")
    store.add_current_event(ev)

    found = store.find_current_event_by_dedupe("unique-hash-123")
    assert found is not None
    assert found.id == ev.id

    missing = store.find_current_event_by_dedupe("does-not-exist")
    assert missing is None


def test_opinion_with_citations_transactional_write() -> None:
    store = _store()
    ev = _make_event(dedupe="tx-hash")
    store.add_current_event(ev)

    op = _make_opinion(ev.id)
    citations = [
        OpinionCitation(
            id=make_citation_id(op.id, i),
            opinion_id=op.id,
            conclusion_id=f"conc-{i}",
            claim_id=None,
            quoted_span=f"quote {i}",
            relevance_score=0.5 + 0.1 * i,
            ordinal=i,
        )
        for i in range(3)
    ]
    store.add_event_opinion(op, citations)

    got = store.get_event_opinion(op.id)
    assert got is not None
    assert got.id == op.id

    cites = store.list_citations_for_opinion(op.id)
    assert len(cites) == 3
    assert {c.id for c in cites} == {c.id for c in citations}
    assert all(c.opinion_id == op.id for c in cites)
    # ordinal ordering preserved
    assert [c.ordinal for c in cites] == [0, 1, 2]


def test_opinion_citation_requires_exactly_one_of_conclusion_or_claim() -> None:
    # Both set -> raises.
    with pytest.raises(ValidationError):
        OpinionCitation(
            id="cite_x",
            opinion_id="op_1",
            conclusion_id="conc_1",
            claim_id="clm_1",
            quoted_span="q",
            relevance_score=0.5,
            ordinal=0,
        )

    # Neither set -> raises.
    with pytest.raises(ValidationError):
        OpinionCitation(
            id="cite_y",
            opinion_id="op_1",
            conclusion_id=None,
            claim_id=None,
            quoted_span="q",
            relevance_score=0.5,
            ordinal=0,
        )

    # Exactly conclusion_id -> ok.
    ok_conc = OpinionCitation(
        id="cite_ok1",
        opinion_id="op_1",
        conclusion_id="conc_1",
        claim_id=None,
        quoted_span="q",
        relevance_score=0.5,
        ordinal=0,
    )
    assert ok_conc.conclusion_id == "conc_1"

    # Exactly claim_id -> ok.
    ok_claim = OpinionCitation(
        id="cite_ok2",
        opinion_id="op_1",
        conclusion_id=None,
        claim_id="clm_1",
        quoted_span="q",
        relevance_score=0.5,
        ordinal=1,
    )
    assert ok_claim.claim_id == "clm_1"


def test_followup_session_ttl_fields_persist() -> None:
    store = _store()
    now = _now()
    expires = now + timedelta(hours=24)
    sess = FollowUpSession(
        id=make_followup_session_id("op_1", "fp_abc", now.date().isoformat()),
        opinion_id="op_1",
        created_at=now,
        last_activity_at=now,
        expires_at=expires,
        client_fingerprint="fp_abc",
    )
    store.add_followup_session(sess)

    got = store.get_followup_session(sess.id)
    assert got is not None
    assert got.id == sess.id
    assert got.expires_at == expires
    assert got.created_at == now
    assert got.last_activity_at == now
    assert got.client_fingerprint == "fp_abc"
    assert got.message_count == 0


def test_revoke_opinion_sets_flag() -> None:
    store = _store()
    ev = _make_event(dedupe="rev-hash")
    store.add_current_event(ev)
    op = _make_opinion(ev.id)
    store.add_event_opinion(op, citations=[])

    pre = store.get_event_opinion(op.id)
    assert pre is not None
    assert pre.revoked is False
    assert pre.revoked_reason is None

    store.revoke_opinion(op.id, "reason")

    post = store.get_event_opinion(op.id)
    assert post is not None
    assert post.revoked is True
    assert post.revoked_reason == "reason"


def test_rate_limit_counter() -> None:
    store = _store()
    now = _now()
    fp = "fp_rate_limit"

    # Create two sessions with the same client_fingerprint.
    sessions = []
    for i in range(2):
        s = FollowUpSession(
            id=make_followup_session_id(f"op_{i}", fp, now.date().isoformat() + f"-{i}"),
            opinion_id=f"op_{i}",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(hours=24),
            client_fingerprint=fp,
        )
        store.add_followup_session(s)
        sessions.append(s)

    # Sprinkle messages across both sessions.
    N = 7
    messages_added = 0
    for session_idx, sess in enumerate(sessions):
        count = 4 if session_idx == 0 else 3
        for k in range(count):
            msg = FollowUpMessage(
                id=make_followup_message_id(sess.id, k),
                session_id=sess.id,
                role=FollowUpMessageRole.USER,
                created_at=now + timedelta(seconds=k),
                content=f"msg {session_idx}:{k}",
            )
            store.add_followup_message(msg)
            messages_added += 1
    assert messages_added == N

    # All within the last hour.
    since = now - timedelta(hours=1)
    got = store.count_followup_messages_in_window(fp, since=since)
    assert got == N

    # Messages with different fingerprint excluded.
    other = store.count_followup_messages_in_window("fp_other", since=since)
    assert other == 0
