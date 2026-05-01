from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    OpinionStance,
)
from noosphere.social.currents_bridge import create_x_draft_for_event_opinion
from noosphere.social.post_safety import SocialGateFailure, check_all_gates
from noosphere.social.post_safety import SocialGateContext
from noosphere.store import Store

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def test_currents_opinion_becomes_draft_and_requires_human_gate() -> None:
    store, event_id, opinion_id = _seed_opinion()
    post_id = asyncio.run(create_x_draft_for_event_opinion(store, event_id))
    assert post_id is not None

    post = store.get_social_post(post_id)
    assert post is not None
    assert post.source == "currents.opinion"
    assert post.source_id == opinion_id
    assert post.status == "draft"
    assert post.body.endswith("https://x.com/source/status/123")

    ctx = SocialGateContext(
        oauth_refresh_configured=True,
        posting_enabled=True,
        kill_switch_engaged=False,
        posts_last_24h=0,
        daily_max=3,
        forbidden_phrases=(),
        firm_publication_hosts=("theseuscodex.com",),
    )
    with pytest.raises(SocialGateFailure) as excinfo:
        check_all_gates(post, ctx)
    assert excinfo.value.code == "NOT_APPROVED"

    post.status = "approved"
    post.approved_by = "founder_1"
    check_all_gates(post, ctx)


def test_bridge_records_rejected_post_when_source_url_is_missing() -> None:
    store, event_id, opinion_id = _seed_opinion(source_url=None)
    post_id = asyncio.run(create_x_draft_for_event_opinion(store, event_id))

    post = store.get_social_post(post_id or "")
    assert post is not None
    assert post.source_id == opinion_id
    assert post.status == "rejected"
    assert "no https URL" in (post.failure_reason or "")


def _seed_opinion(source_url: str | None = "https://x.com/source/status/123") -> tuple[Store, str, str]:
    store = Store.from_database_url("sqlite:///:memory:")
    event = CurrentEvent(
        organization_id="org_1",
        source=CurrentEventSource.X_TWITTER,
        external_id="123",
        author_handle="@source",
        text="A current event.",
        url=source_url,
        observed_at=NOW,
        dedupe_hash=f"hash_{source_url or 'missing'}",
        status=CurrentEventStatus.OPINED,
    )
    event_id = store.add_current_event(event)
    opinion = EventOpinion(
        organization_id="org_1",
        event_id=event_id,
        stance=OpinionStance.COMPLICATES,
        confidence=0.7,
        headline="Fixture opinion",
        body_markdown="Theseus complicates the premise.",
        uncertainty_notes=[],
        model_name="fixture",
        generated_at=NOW,
    )
    opinion_id = store.add_event_opinion(opinion, [])
    return store, event_id, opinion_id
