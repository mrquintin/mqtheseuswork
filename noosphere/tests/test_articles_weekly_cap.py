from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from noosphere.articles.generator import ArticleKind
from noosphere.articles.triggers import (
    select_thematic_candidates,
    triggered_article_candidates,
)
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
    PublishedConclusion,
)
from noosphere.store import Store

ORG_ID = "org_articles_weekly"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_opinion(store: Store, idx: int) -> str:
    event_id = f"weekly_event_{idx}"
    opinion_id = f"weekly_opinion_{idx}"
    event = CurrentEvent(
        id=event_id,
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id=f"weekly_external_{idx}",
        text=f"Weekly evidence {idx} for the same topic.",
        url=f"https://x.com/weekly/status/{idx}",
        observed_at=NOW - timedelta(hours=idx),
        topic_hint="cadence::articles",
        dedupe_hash=f"weekly_hash_{idx}",
    )
    store.add_current_event(event)
    opinion = EventOpinion(
        id=opinion_id,
        organization_id=ORG_ID,
        event_id=event_id,
        stance=OpinionStance.COMPLICATES,
        confidence=0.7,
        headline=f"Weekly firm opinion {idx}",
        body_markdown=f"The firm believes Weekly evidence {idx} changes the cadence question.",
        topic_hint="cadence::articles",
        model_name="fixture",
        generated_at=NOW - timedelta(hours=idx),
    )
    with store.session() as session:
        session.add(opinion)
        session.commit()
    return opinion_id


def _seed_thematic_cluster(store: Store) -> list[str]:
    return [_seed_opinion(store, idx) for idx in range(3)]


def _seed_published_article(store: Store, when: datetime) -> None:
    payload = {
        "schema": "theseus.publicConclusion.v1",
        "conclusionText": "Already published weekly article",
        "article": {
            "kind": ArticleKind.THEMATIC.value,
            "sourceIds": ["already_published"],
            "sourceKey": "already_published",
            "status": "published",
            "bodyMarkdown": "The firm believes the weekly slot was already used.",
            "citations": [],
        },
    }
    with store.session() as session:
        session.add(
            PublishedConclusion(
                organization_id=ORG_ID,
                source_conclusion_id="article:already_published",
                slug=f"already-published-{int(when.timestamp())}",
                version=1,
                kind="ARTICLE",
                discounted_confidence=0.5,
                stated_confidence=0.5,
                payload_json=json.dumps(payload, sort_keys=True),
                doi="",
                zenodo_record_id="",
                published_at=when,
            )
        )
        session.commit()


def _seed_correction(store: Store) -> str:
    conclusion = Conclusion(
        id="weekly_revoked_conclusion",
        text="The revoked conclusion overstated the cadence evidence.",
    )
    store.put_conclusion(conclusion)
    opinion_id = _seed_opinion(store, 99)
    opinion = store.get_event_opinion(opinion_id)
    assert opinion is not None
    with store.session() as session:
        session.add(
            OpinionCitation(
                opinion_id=opinion.id,
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="overstated the cadence evidence",
                retrieval_score=0.9,
            )
        )
        session.commit()
    store.revoke_citations_for_source(
        "conclusion",
        conclusion.id,
        "source revoked inside correction window",
    )
    return opinion.id


def _article_row_count(store: Store) -> int:
    with store.session() as session:
        return len(
            list(
                session.exec(
                    select(PublishedConclusion.id).where(
                        PublishedConclusion.kind == "ARTICLE"
                    )
                ).all()
            )
        )


def test_thematic_candidates_stop_after_one_article_in_last_seven_days() -> None:
    store = _store()
    _seed_thematic_cluster(store)
    _seed_published_article(store, NOW - timedelta(days=1))

    candidates = asyncio.run(select_thematic_candidates(store, now=NOW))

    assert candidates == []
    assert _article_row_count(store) == 1


def test_thematic_candidates_return_when_weekly_window_is_empty() -> None:
    store = _store()
    source_ids = _seed_thematic_cluster(store)

    candidates = asyncio.run(select_thematic_candidates(store, now=NOW))

    assert candidates
    assert set(candidates[0]) == set(source_ids)


def test_corrections_still_trigger_inside_correction_window_when_weekly_cap_is_full() -> None:
    store = _store()
    _seed_thematic_cluster(store)
    _seed_published_article(store, NOW - timedelta(days=1))
    opinion_id = _seed_correction(store)

    candidates = asyncio.run(triggered_article_candidates(store, now=NOW))

    assert len(candidates) == 1
    assert candidates[0].kind == ArticleKind.CORRECTION
    assert candidates[0].source_ids == [opinion_id]


def test_weekly_cap_zero_disables_all_generation(monkeypatch) -> None:
    store = _store()
    _seed_thematic_cluster(store)
    opinion_id = _seed_correction(store)
    assert opinion_id
    monkeypatch.setenv("NOOSPHERE_ARTICLES_WEEKLY_CAP", "0")

    thematic = asyncio.run(select_thematic_candidates(store, now=NOW))
    candidates = asyncio.run(triggered_article_candidates(store, now=NOW))

    assert thematic == []
    assert candidates == []
