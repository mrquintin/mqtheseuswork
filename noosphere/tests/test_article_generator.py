from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from noosphere.articles import generator as subject
from noosphere.articles.generator import ArticleKind
from noosphere.articles.triggers import (
    correction_trigger_check,
    dispatch_triggered_articles,
    postmortem_trigger_check,
    thematic_trigger_check,
)
from noosphere.currents._llm_client import LLMResponse
from noosphere.models import (
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    EventOpinion,
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    OpinionCitation,
    OpinionStance,
    PublishedConclusion,
)
from noosphere.store import Store

ORG_ID = "org_articles"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


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
            model="article-test-model",
        )


class RecordingBudget:
    def __init__(self) -> None:
        self.authorized: list[tuple[int, int]] = []
        self.charged: list[tuple[int, int]] = []

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        self.authorized.append((est_prompt, est_completion))

    def charge(self, prompt: int, completion: int) -> None:
        self.charged.append((prompt, completion))


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _article_rows(store: Store) -> list[PublishedConclusion]:
    with store.session() as session:
        return list(
            session.exec(
                select(PublishedConclusion)
                .where(PublishedConclusion.kind == "ARTICLE")
                .order_by(PublishedConclusion.published_at)
            ).all()
        )


def _seed_current(
    store: Store, idx: int, *, topic_hint: str = "ai::epistemology"
) -> str:
    event = CurrentEvent(
        id=f"current_article_{idx}",
        organization_id=ORG_ID,
        source=CurrentEventSource.MANUAL,
        external_id=f"current_article_external_{idx}",
        text=f"Topic evidence {idx} says automated research needs source discipline.",
        url=f"https://x.com/theseus_fixture/status/{idx}",
        observed_at=NOW - timedelta(days=1, minutes=idx),
        topic_hint=topic_hint,
        dedupe_hash=f"current_article_hash_{idx}",
    )
    return store.add_current_event(event)


def _seed_opinion(
    store: Store, idx: int, *, topic_hint: str = "ai::epistemology"
) -> str:
    event_id = _seed_current(store, idx, topic_hint=topic_hint)
    opinion = EventOpinion(
        id=f"opinion_article_{idx}",
        organization_id=ORG_ID,
        event_id=event_id,
        stance=OpinionStance.COMPLICATES,
        confidence=0.66,
        headline=f"Firm view {idx} on source discipline",
        body_markdown=(
            f"The firm believes Topic evidence {idx} shows automated research "
            "needs source discipline before it can be trusted in public."
        ),
        topic_hint=topic_hint,
        model_name="fixture",
        generated_at=NOW - timedelta(hours=1, minutes=idx),
    )
    opinion_id = opinion.id
    with store.session() as session:
        session.add(opinion)
        session.commit()
    return opinion_id


def _link_opinion_to_corpus_upload(
    store: Store,
    opinion_id: str,
    conclusion_id: str,
    upload_id: str,
) -> None:
    store.put_conclusion(
        Conclusion(
            id=conclusion_id,
            text=f"Corpus fixture {conclusion_id} supports the opinion.",
        )
    )
    with store.engine.begin() as conn:
        conn.execute(
            text(
                'CREATE TABLE IF NOT EXISTS "ConclusionSource" ('
                '"conclusionId" TEXT NOT NULL, '
                '"uploadId" TEXT NOT NULL, '
                '"createdAt" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'PRIMARY KEY ("conclusionId", "uploadId"))'
            )
        )
        conn.execute(
            text(
                'INSERT INTO "ConclusionSource" '
                '("conclusionId", "uploadId") VALUES (:conclusion_id, :upload_id)'
            ),
            {"conclusion_id": conclusion_id, "upload_id": upload_id},
        )
    with store.session() as session:
        session.add(
            OpinionCitation(
                opinion_id=opinion_id,
                source_kind="conclusion",
                conclusion_id=conclusion_id,
                quoted_span=f"Corpus fixture {conclusion_id}",
                retrieval_score=0.91,
            )
        )
        session.commit()


def _seed_postmortem(store: Store, idx: int, *, brier: float = 0.81) -> str:
    market = ForecastMarket(
        id=f"article_market_{idx}",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=f"article_market_external_{idx}",
        title=f"Will article fixture {idx} resolve YES?",
        raw_payload={},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id=f"article_prediction_{idx}",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.820000"),
        confidence_low=Decimal("0.710000"),
        confidence_high=Decimal("0.900000"),
        headline=f"Fixture forecast {idx} expected YES",
        reasoning="The forecast said the prior probability was materially above market.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="forecasting",
        model_name="fixture",
        live_authorized_at=NOW,
        created_at=NOW - timedelta(hours=2, minutes=idx),
    )
    store.put_forecast_prediction(prediction)
    store.put_forecast_resolution(
        ForecastResolution(
            id=f"article_resolution_{idx}",
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.NO,
            brier_score=brier,
            log_loss=1.71,
            calibration_bucket=Decimal("0.8"),
            resolved_at=NOW,
            justification="The official settlement resolved NO.",
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id=f"article_bet_{idx}",
            prediction_id=prediction.id,
            organization_id=ORG_ID,
            mode=ForecastBetMode.PAPER,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("25.00"),
            entry_price=Decimal("0.500000"),
            status=ForecastBetStatus.FILLED,
            live_authorized_at=NOW,
        )
    )
    return prediction.id


def _seed_correction(store: Store) -> str:
    conclusion = Conclusion(
        id="article_revoked_conclusion",
        text="Revoked source text said automated research was fully reliable.",
    )
    store.put_conclusion(conclusion)
    event_id = _seed_current(store, 99, topic_hint="correction::epistemology")
    opinion = EventOpinion(
        id="article_correction_opinion",
        organization_id=ORG_ID,
        event_id=event_id,
        stance=OpinionStance.AGREES,
        confidence=0.7,
        headline="Dependent opinion relied on a revoked source",
        body_markdown="The opinion depended on the revoked reliability claim.",
        topic_hint="correction",
        model_name="fixture",
    )
    opinion_id = opinion.id
    store.add_event_opinion(
        opinion,
        [
            OpinionCitation(
                opinion_id=opinion.id,
                source_kind="conclusion",
                conclusion_id=conclusion.id,
                quoted_span="automated research was fully reliable",
                retrieval_score=0.9,
            )
        ],
    )
    store.revoke_citations_for_source(
        "conclusion", conclusion.id, "source revoked after audit"
    )
    return opinion_id


def test_thematic_happy_path_persists_article_with_verbatim_citations(
    monkeypatch,
) -> None:
    store = _store()
    source_ids = [_seed_opinion(store, idx) for idx in range(3)]
    payload = {
        "headline": "Source discipline is becoming the central automation question",
        "body_markdown": (
            "The firm believes source discipline is becoming the central automation "
            "question, and it treats the retrieved events as evidence for that "
            "perspective rather than as material to recap."
        ),
        "topic_hint": "ai_epistemology",
        "confidence": 0.66,
        "citations": [
            {
                "source_kind": "event_opinion",
                "source_id": source_id,
                "quoted_span": f"Topic evidence {idx}",
            }
            for idx, source_id in enumerate(source_ids)
        ],
    }
    monkeypatch.setattr(subject, "make_client", lambda: ScriptedClient([payload]))

    clusters = asyncio.run(thematic_trigger_check(store))
    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=clusters[0],
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    assert article.slug
    rows = _article_rows(store)
    assert len(rows) == 1
    stored = json.loads(rows[0].payload_json)
    assert rows[0].kind == "ARTICLE"
    assert stored["article"]["kind"] == "THEMATIC"
    assert {c["quoted_span"] for c in stored["article"]["citations"]} == {
        f"Topic evidence {idx}" for idx in range(3)
    }
    assert {c["public_url"] for c in stored["article"]["citations"]} == {
        f"/currents/{source_id}" for source_id in source_ids
    }


def test_thematic_trigger_caps_large_opinion_cluster(monkeypatch) -> None:
    store = _store()
    monkeypatch.setenv("ARTICLES_THEMATIC_MAX_SOURCES", "4")
    for idx in range(12):
        _seed_opinion(store, idx)

    clusters = asyncio.run(thematic_trigger_check(store))

    assert len(clusters) == 1
    assert len(clusters[0]) == 4
    assert set(clusters[0]) == {
        "opinion_article_0",
        "opinion_article_1",
        "opinion_article_2",
        "opinion_article_3",
    }


def test_thematic_trigger_requires_distinct_underlying_corpus_sources() -> None:
    store = _store()
    for idx in range(4):
        opinion_id = _seed_opinion(store, idx)
        _link_opinion_to_corpus_upload(
            store,
            opinion_id,
            f"same_source_conclusion_{idx}",
            "upload_education_podcast",
        )

    assert asyncio.run(thematic_trigger_check(store)) == []


def test_thematic_trigger_balances_opinions_by_underlying_corpus_source(
    monkeypatch,
) -> None:
    store = _store()
    monkeypatch.setenv("ARTICLES_THEMATIC_MAX_SOURCES", "4")
    opinion_uploads = [
        "upload_education_podcast",
        "upload_education_podcast",
        "upload_education_podcast",
        "upload_markets_memo",
        "upload_governance_notes",
    ]
    for idx, upload_id in enumerate(opinion_uploads):
        opinion_id = _seed_opinion(store, idx)
        _link_opinion_to_corpus_upload(
            store,
            opinion_id,
            f"balanced_conclusion_{idx}",
            upload_id,
        )

    clusters = asyncio.run(thematic_trigger_check(store))

    assert len(clusters) == 1
    assert clusters[0] == [
        "opinion_article_0",
        "opinion_article_1",
        "opinion_article_3",
        "opinion_article_4",
    ]


def test_postmortem_trigger_and_generation_reference_prior_and_outcome(
    monkeypatch,
) -> None:
    store = _store()
    prediction_id = _seed_postmortem(store, 1, brier=0.67)
    payload = {
        "headline": "The high-confidence miss exposes a calibration boundary",
        "body_markdown": (
            "The firm believes the prior probability was 0.820000, but the realized "
            "outcome was NO; the principles need narrower conditions."
        ),
        "topic_hint": "forecasting",
        "confidence": 0.58,
        "citations": [
            {
                "source_kind": "forecast_postmortem",
                "source_id": prediction_id,
                "quoted_span": "Prior probability YES: 0.820000",
            },
            {
                "source_kind": "forecast_postmortem",
                "source_id": prediction_id,
                "quoted_span": "Realized outcome: NO",
            },
        ],
    }
    monkeypatch.setattr(subject, "make_client", lambda: ScriptedClient([payload]))

    assert asyncio.run(postmortem_trigger_check(store)) == [prediction_id]
    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.POSTMORTEM,
            source_ids=[prediction_id],
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    body = json.loads(_article_rows(store)[0].payload_json)["article"]["bodyMarkdown"]
    assert "prior probability was 0.820000" in body
    assert "realized outcome was NO" in body


def test_correction_trigger_cites_revocation_and_lists_affected_opinion(
    monkeypatch,
) -> None:
    store = _store()
    opinion_id = _seed_correction(store)
    payload = {
        "headline": "A revoked source narrows the dependent opinion",
        "body_markdown": (
            "The firm treats the correction as a narrowed public view because the "
            "revocation changes how the affected opinion should be read."
        ),
        "topic_hint": "correction",
        "confidence": 0.62,
        "citations": [
            {
                "source_kind": "correction",
                "source_id": opinion_id,
                "quoted_span": "Revocation reasons: source revoked after audit",
            },
            {
                "source_kind": "correction",
                "source_id": opinion_id,
                "quoted_span": "Affected opinion: Dependent opinion relied on a revoked source",
            },
        ],
    }
    monkeypatch.setattr(subject, "make_client", lambda: ScriptedClient([payload]))

    assert asyncio.run(correction_trigger_check(store)) == [opinion_id]
    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.CORRECTION,
            source_ids=[opinion_id],
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    stored = json.loads(_article_rows(store)[0].payload_json)
    quotes = {citation["quoted_span"] for citation in stored["article"]["citations"]}
    assert "Revocation reasons: source revoked after audit" in quotes
    assert "Affected opinion: Dependent opinion relied on a revoked source" in quotes
    assert stored["article"]["citations"][0]["public_url"] == f"/currents/{opinion_id}"


def test_article_generation_rejects_source_recap_until_firm_voice(monkeypatch) -> None:
    store = _store()
    source_id = _seed_current(store, 7)
    client = ScriptedClient(
        [
            {
                "headline": "Bad recap",
                "body_markdown": "## Sources\nThis source says automated research needs source discipline.",
                "topic_hint": "ai_epistemology",
                "confidence": 0.5,
                "citations": [
                    {
                        "source_kind": "current_event",
                        "source_id": source_id,
                        "quoted_span": "Topic evidence 7",
                    }
                ],
            },
            {
                "headline": "Source discipline is a methodological constraint",
                "body_markdown": (
                    "The firm believes source discipline is not a decorative citation "
                    "norm; it is a methodological constraint on automated research."
                ),
                "topic_hint": "ai_epistemology",
                "confidence": 0.61,
                "citations": [
                    {
                        "source_kind": "current_event",
                        "source_id": source_id,
                        "quoted_span": "Topic evidence 7",
                    }
                ],
            },
        ]
    )
    monkeypatch.setattr(subject, "make_client", lambda: client)

    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=[source_id],
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    assert len(client.calls) == 2
    assert "firm voice" in client.calls[1]["system"]
    assert "the firm" in article.body_markdown.lower()


def test_article_generation_filters_invalid_extra_citations(monkeypatch) -> None:
    store = _store()
    source_id = _seed_opinion(store, 8)
    payload = {
        "headline": "Source discipline remains the controlling question",
        "body_markdown": (
            "The firm believes source discipline remains the controlling question "
            "for any public automation claim."
        ),
        "topic_hint": "ai_epistemology",
        "confidence": 0.63,
        "citations": [
            {
                "source_kind": "event_opinion",
                "source_id": source_id,
                "quoted_span": "not actually present in the retrieved source",
            },
            {
                "source_kind": "event_opinion",
                "source_id": source_id,
                "quoted_span": "Topic evidence 8",
            },
        ],
    }
    monkeypatch.setattr(subject, "make_client", lambda: ScriptedClient([payload]))

    article = asyncio.run(
        subject.generate_article(
            store,
            kind=ArticleKind.THEMATIC,
            source_ids=[source_id],
            budget=RecordingBudget(),
        )
    )

    assert article is not None
    stored = json.loads(_article_rows(store)[0].payload_json)
    assert [citation["quoted_span"] for citation in stored["article"]["citations"]] == [
        "Topic evidence 8"
    ]


def test_correction_trigger_requires_recent_citation_revocation() -> None:
    store = _store()
    opinion_id = _seed_correction(store)
    old_revocation = datetime.now(timezone.utc) - timedelta(days=2)
    with store.session() as session:
        rows = list(
            session.exec(
                select(OpinionCitation).where(OpinionCitation.opinion_id == opinion_id)
            ).all()
        )
        for row in rows:
            row.revoked_at = old_revocation
            session.add(row)
        session.commit()

    assert asyncio.run(correction_trigger_check(store)) == []


def test_daily_cap_defers_trigger_candidates_to_next_day(monkeypatch) -> None:
    store = _store()
    prediction_ids = [_seed_postmortem(store, idx) for idx in range(5)]
    payloads = [
        {
            "headline": f"Postmortem article {idx}",
            "body_markdown": (
                f"The firm believes prior probability 0.820000 resolving NO for "
                f"candidate {idx} should narrow the relevant forecasting principle."
            ),
            "topic_hint": "forecasting",
            "confidence": 0.5,
            "citations": [
                {
                    "source_kind": "forecast_postmortem",
                    "source_id": prediction_id,
                    "quoted_span": "Realized outcome: NO",
                }
            ],
        }
        for idx, prediction_id in enumerate(prediction_ids)
    ]
    client = ScriptedClient(payloads)
    monkeypatch.setattr(subject, "make_client", lambda: client)
    monkeypatch.setattr(subject, "_utcnow", lambda: NOW)

    first_day = asyncio.run(
        dispatch_triggered_articles(
            store,
            budget=RecordingBudget(),
            daily_cap=4,
            now=NOW,
        )
    )
    second_day = asyncio.run(
        dispatch_triggered_articles(
            store,
            budget=RecordingBudget(),
            daily_cap=4,
            now=NOW + timedelta(days=1),
        )
    )

    assert len(first_day) == 4
    assert len(second_day) == 1
    assert len(_article_rows(store)) == 5
