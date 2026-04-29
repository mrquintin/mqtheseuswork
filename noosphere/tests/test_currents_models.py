"""Currents Store accessors and shared-table models."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from noosphere.models import (
    AbstentionReason,
    Claim,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    FollowUpMessage,
    FollowUpRole,
    FollowUpSession,
    OpinionCitation,
    OpinionStance,
    Speaker,
)
from noosphere.store import Store


ORG_ID = "org_currents"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_sources(st: Store) -> tuple[Conclusion, Claim]:
    conclusion = Conclusion(
        id="conclusion_currents",
        text="Theseus has strong priors about durable compounding.",
    )
    claim = Claim(
        id="claim_currents",
        text="Public markets often overreact to ambiguous news.",
        speaker=Speaker(name="Ada"),
        episode_id="episode_currents",
        episode_date=date(2026, 4, 29),
    )
    st.put_conclusion(conclusion)
    st.put_claim(claim)
    return conclusion, claim


def _event(*, dedupe_hash: str = "event_hash_1") -> CurrentEvent:
    return CurrentEvent(
        organization_id=ORG_ID,
        source=CurrentEventSource.X_TWITTER,
        external_id=f"external_{dedupe_hash}",
        author_handle="@theseus",
        text="A live market event crossed the wire.",
        url="https://example.com/events/1",
        observed_at=datetime(2026, 4, 29, 12, 0, 0),
        topic_hint="markets",
        dedupe_hash=dedupe_hash,
    )


def _opinion(event_id: str, *, opinion_id: str = "opinion_currents") -> EventOpinion:
    return EventOpinion(
        id=opinion_id,
        organization_id=ORG_ID,
        event_id=event_id,
        stance=OpinionStance.COMPLICATES,
        confidence=0.72,
        headline="Market reaction complicates the durable-compounding thesis",
        body_markdown="The event is notable, but the source-grounded view is narrower than the headline.",
        uncertainty_notes=["single-source event", "market reaction may reverse"],
        topic_hint="markets",
        model_name="claude-haiku-4-5",
        generated_at=datetime(2026, 4, 29, 12, 5, 0),
    )


def test_currents_models_round_trip_each_model() -> None:
    st = _store()
    conclusion, claim = _seed_sources(st)

    event = _event()
    expected_event_id = event.id
    dedupe_hash = event.dedupe_hash
    event_id = st.add_current_event(event)
    assert event_id == expected_event_id
    assert st.add_current_event(_event(dedupe_hash=dedupe_hash)) == event_id

    loaded_event = st.find_current_event_by_dedupe(dedupe_hash)
    assert loaded_event is not None
    assert loaded_event.id == event_id
    assert loaded_event.organization_id == ORG_ID
    assert loaded_event.dedupe_hash == dedupe_hash

    opinion = _opinion(event_id)
    expected_opinion_id = opinion.id
    opinion_id = st.add_event_opinion(
        opinion,
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="strong priors",
                retrieval_score=0.91,
            ),
            OpinionCitation(
                opinion_id="",
                source_kind="claim",
                claim_id=claim.id,
                quoted_span="overreact to ambiguous news",
                retrieval_score=0.83,
            ),
        ],
    )
    assert opinion_id == expected_opinion_id

    loaded_opinion = st.get_event_opinion(opinion_id)
    assert loaded_opinion is not None
    assert loaded_opinion.event_id == event_id
    assert loaded_opinion.organization_id == ORG_ID
    assert loaded_opinion.uncertainty_notes == [
        "single-source event",
        "market reaction may reverse",
    ]
    assert [o.id for o in st.list_recent_opinions(ORG_ID, datetime(2026, 4, 29), 10)] == [
        opinion_id
    ]

    citations = st.list_opinion_citations(opinion_id)
    assert {c.source_kind for c in citations} == {"claim", "conclusion"}
    assert {c.opinion_id for c in citations} == {opinion_id}

    session = FollowUpSession(
        opinion_id=opinion_id,
        client_fingerprint="fingerprint_2026_04_29",
    )
    session_id = st.add_followup_session(session)
    loaded_session = st.get_followup_session(session_id)
    assert loaded_session is not None
    assert loaded_session.opinion_id == opinion_id

    expected_message_citations = [
        {
            "source_kind": "conclusion",
            "source_id": conclusion.id,
            "quoted_span": "strong priors",
        }
    ]
    message = FollowUpMessage(
        session_id=session_id,
        role=FollowUpRole.USER,
        content="What source grounds that claim?",
        citations=expected_message_citations,
    )
    expected_message_created_at = message.created_at
    message_id = st.add_followup_message(message)
    loaded_message = st.get_followup_message(message_id)
    assert loaded_message is not None
    assert loaded_message.session_id == session_id
    assert loaded_message.citations == expected_message_citations
    assert st.get_followup_session(session_id).last_activity_at == expected_message_created_at  # type: ignore[union-attr]


def test_add_event_opinion_rejects_non_verbatim_conclusion_citation() -> None:
    st = _store()
    conclusion, _claim = _seed_sources(st)
    event_id = st.add_current_event(_event())
    opinion = _opinion(event_id)

    with pytest.raises(ValueError, match="verbatim substring"):
        st.add_event_opinion(
            opinion,
            [
                OpinionCitation(
                    opinion_id="",
                    source_kind="conclusion",
                    conclusion_id=conclusion.id,
                    quoted_span="this span is fabricated",
                    retrieval_score=0.25,
                )
            ],
        )

    assert st.get_event_opinion(opinion.id) is None


def test_revoke_citations_updates_only_fully_revoked_opinions() -> None:
    st = _store()
    conclusion, claim = _seed_sources(st)
    event_id = st.add_current_event(_event())

    all_revoked = _opinion(event_id, opinion_id="opinion_all_revoked")
    all_revoked_id = all_revoked.id
    st.add_event_opinion(
        all_revoked,
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="durable compounding",
                retrieval_score=0.88,
            )
        ],
    )

    partially_revoked = _opinion(event_id, opinion_id="opinion_partially_revoked")
    partially_revoked_id = partially_revoked.id
    st.add_event_opinion(
        partially_revoked,
        [
            OpinionCitation(
                opinion_id="",
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="strong priors",
                retrieval_score=0.9,
            ),
            OpinionCitation(
                opinion_id="",
                source_kind="claim",
                claim_id=claim.id,
                quoted_span="ambiguous news",
                retrieval_score=0.86,
            ),
        ],
    )

    revoked_count = st.revoke_citations_for_source(
        "conclusion",
        conclusion.id,
        "source withdrawn",
    )
    assert revoked_count == 2

    all_revoked_citations = st.list_opinion_citations(all_revoked_id)
    assert all(c.is_revoked for c in all_revoked_citations)
    assert {c.revoked_reason for c in all_revoked_citations} == {"source withdrawn"}

    partial_citations = st.list_opinion_citations(partially_revoked_id)
    revoked_by_kind = {c.source_kind: c.is_revoked for c in partial_citations}
    assert revoked_by_kind == {"claim": False, "conclusion": True}

    loaded_all_revoked = st.get_event_opinion(all_revoked_id)
    loaded_partial = st.get_event_opinion(partially_revoked_id)
    assert loaded_all_revoked is not None
    assert loaded_all_revoked.abstention_reason == AbstentionReason.REVOKED_SOURCES
    assert loaded_partial is not None
    assert loaded_partial.abstention_reason is None

    later = st.revoke_citations_for_source("claim", claim.id, "claim withdrawn")
    assert later == 1
    loaded_partial = st.get_event_opinion(partially_revoked_id)
    assert loaded_partial is not None
    assert loaded_partial.abstention_reason == AbstentionReason.REVOKED_SOURCES
