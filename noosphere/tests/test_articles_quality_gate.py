from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select

from noosphere.articles import generator as subject
from noosphere.articles.generator import ArticleKind, MAX_TITLE_CHARS
from noosphere.currents._llm_client import LLMResponse
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    OpinionStance,
    PublishedConclusion,
)
from noosphere.store import Store

ORG_ID = "org_articles_quality"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class ScriptedClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.payloads:
            raise AssertionError("no scripted article response left")
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return LLMResponse(
            text=json.dumps(self.payloads.pop(0)),
            prompt_tokens=100,
            completion_tokens=200,
            model="article-quality-test-model",
        )


class RecordingBudget:
    def authorize(self, est_prompt: int, est_completion: int) -> None:
        assert est_prompt > 0
        assert est_completion > 0

    def charge(self, prompt: int, completion: int) -> None:
        assert prompt > 0
        assert completion > 0


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_opinion(store: Store, idx: int) -> str:
    event_id = f"quality_event_{idx}"
    opinion_id = f"quality_opinion_{idx}"
    event = CurrentEvent(
        id=event_id,
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id=f"quality_external_{idx}",
        text=f"Quality evidence {idx} tests the publication gate.",
        url=f"https://x.com/quality/status/{idx}",
        observed_at=NOW - timedelta(hours=idx),
        topic_hint="quality::articles",
        dedupe_hash=f"quality_hash_{idx}",
    )
    store.add_current_event(event)
    opinion = EventOpinion(
        id=opinion_id,
        organization_id=ORG_ID,
        event_id=event_id,
        stance=OpinionStance.COMPLICATES,
        confidence=0.72,
        headline=f"Quality firm opinion {idx}",
        body_markdown=(
            f"The firm believes Firm conclusion {idx} constrains article quality."
        ),
        topic_hint="quality::articles",
        model_name="fixture",
        generated_at=NOW - timedelta(hours=idx),
    )
    with store.session() as session:
        session.add(opinion)
        session.commit()
    return opinion_id


def _seed_sources(store: Store) -> list[str]:
    return [_seed_opinion(store, idx) for idx in range(3)]


def _citations(source_ids: list[str], count: int = 3) -> list[dict[str, str]]:
    return [
        {
            "source_kind": "event_opinion",
            "source_id": source_id,
            "quoted_span": f"Firm conclusion {idx}",
        }
        for idx, source_id in enumerate(source_ids[:count])
    ]


def _body(prefix: str = "The firm believes") -> str:
    return (
        f"{prefix} the central question is whether its recent publication "
        "practice can synthesize opinions instead of reciting them [S1]. The "
        "firm treats the first prior conclusion as a constraint on cadence, "
        "not as filler [S2]. The firm also holds that the third conclusion "
        "forces the article to make a discriminating claim [S3]."
    )


def _payload(
    *,
    headline: str = "Publication quality as editorial discipline",
    body_markdown: str | None = None,
    source_ids: list[str],
    citation_count: int = 3,
) -> dict[str, Any]:
    return {
        "headline": headline,
        "body_markdown": body_markdown if body_markdown is not None else _body(),
        "topic_hint": "quality_articles",
        "confidence": 0.66,
        "citations": _citations(source_ids, citation_count),
    }


def _article_rows(store: Store) -> list[PublishedConclusion]:
    with store.session() as session:
        return list(
            session.exec(
                select(PublishedConclusion).where(PublishedConclusion.kind == "ARTICLE")
            ).all()
        )


def test_title_over_max_reprompts_once_then_needs_review(monkeypatch) -> None:
    store = _store()
    source_ids = _seed_sources(store)
    long_headline = (
        "Publication quality as a very long editorial discipline that fails the "
        "title policy"
    )
    assert len(long_headline) > MAX_TITLE_CHARS
    client = ScriptedClient(
        [
            _payload(headline=long_headline, source_ids=source_ids),
            _payload(headline=long_headline, source_ids=source_ids),
        ]
    )
    monkeypatch.setattr(subject, "make_client", lambda: client)

    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=source_ids,
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    assert article.status == "needs_review"
    assert len(client.calls) == 2
    assert "title policy" in client.calls[1]["system"]
    assert _article_rows(store) == []
    assert any("headline exceeds" in reason for reason in article.review_reasons)
    assert store.list_open_review_items()


def test_generic_first_paragraph_reprompts_once_then_needs_review(monkeypatch) -> None:
    store = _store()
    source_ids = _seed_sources(store)
    generic_body = _body(prefix="In recent times, the firm believes")
    client = ScriptedClient(
        [
            _payload(body_markdown=generic_body, source_ids=source_ids),
            _payload(body_markdown=generic_body, source_ids=source_ids),
        ]
    )
    monkeypatch.setattr(subject, "make_client", lambda: client)

    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=source_ids,
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    assert article.status == "needs_review"
    assert len(client.calls) == 2
    assert "opening policy" in client.calls[1]["system"]
    assert _article_rows(store) == []
    assert any("generic opening" in reason for reason in article.review_reasons)


def test_thematic_body_with_fewer_than_three_citations_needs_review(
    monkeypatch,
) -> None:
    store = _store()
    source_ids = _seed_sources(store)
    client = ScriptedClient(
        [_payload(source_ids=source_ids, citation_count=2)]
    )
    monkeypatch.setattr(subject, "make_client", lambda: client)

    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=source_ids,
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    assert article.status == "needs_review"
    assert len(client.calls) == 1
    assert _article_rows(store) == []
    assert any("at least 3" in reason for reason in article.review_reasons)
