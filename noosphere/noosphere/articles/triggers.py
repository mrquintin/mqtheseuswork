"""Article trigger heuristics for thematic, postmortem, and correction essays."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import select

from noosphere.articles.generator import (
    Article,
    ArticleKind,
    article_already_published,
    count_articles_since,
    generate_article,
)
from noosphere.models import (
    CurrentEvent,
    EventOpinion,
    ForecastBet,
    ForecastResolution,
    OpinionCitation,
)

THEMATIC_WINDOW = timedelta(days=7)
CORRECTION_WINDOW = timedelta(hours=24)
DEFAULT_DAILY_ARTICLE_CAP = 4
DEFAULT_THEMATIC_MIN_OPINIONS = 2
DEFAULT_THEMATIC_MIN_EVENTS = 5
DEFAULT_THEMATIC_MAX_SOURCES = 8


@dataclass(frozen=True)
class ArticleCandidate:
    kind: ArticleKind
    source_ids: list[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _topic_discipline_key_from_hint(topic_hint: str | None) -> tuple[str, str]:
    raw = (topic_hint or "untagged").strip().lower()
    if "::" in raw:
        topic, discipline = raw.split("::", 1)
    elif "/" in raw:
        topic, discipline = raw.split("/", 1)
    elif "|" in raw:
        topic, discipline = raw.split("|", 1)
    else:
        topic, discipline = raw, "general"
    return topic.strip() or "untagged", discipline.strip() or "general"


def _topic_discipline_key(event: CurrentEvent) -> tuple[str, str]:
    return _topic_discipline_key_from_hint(event.topic_hint)


def _opinion_topic_discipline_key(
    opinion: EventOpinion,
    event_by_id: dict[str, CurrentEvent],
) -> tuple[str, str]:
    event = event_by_id.get(opinion.event_id)
    return _topic_discipline_key_from_hint(
        opinion.topic_hint or (event.topic_hint if event else None)
    )


def _thematic_max_sources() -> int:
    return _env_int(
        "ARTICLES_THEMATIC_MAX_SOURCES",
        DEFAULT_THEMATIC_MAX_SOURCES,
        minimum=2,
    )


def _representative_opinion_ids(cluster: list[EventOpinion]) -> list[str]:
    """Pick a bounded recent slice so one article prompt cannot absorb a whole backlog."""

    max_sources = _thematic_max_sources()
    selected = sorted(
        cluster,
        key=lambda opinion: (_as_utc(opinion.generated_at), opinion.confidence),
        reverse=True,
    )[:max_sources]
    return [opinion.id for opinion in selected]


def _representative_event_ids(cluster: list[CurrentEvent]) -> list[str]:
    max_sources = _thematic_max_sources()
    selected = sorted(
        cluster,
        key=lambda event: _as_utc(event.observed_at),
        reverse=True,
    )[:max_sources]
    return [event.id for event in selected]


async def _opinion_thematic_clusters(store: Any, since: datetime) -> list[list[str]]:
    """Return recent public-firm-opinion clusters sharing topic+discipline."""

    min_opinions = _env_int(
        "ARTICLES_THEMATIC_MIN_OPINIONS",
        DEFAULT_THEMATIC_MIN_OPINIONS,
        minimum=2,
    )
    with store.session() as session:
        opinions = list(
            session.exec(
                select(EventOpinion)
                .where(EventOpinion.generated_at >= since)
                .where(EventOpinion.revoked_at.is_(None))
                .where(EventOpinion.abstention_reason.is_(None))
                .order_by(EventOpinion.generated_at)
            ).all()
        )
        event_ids = [opinion.event_id for opinion in opinions if opinion.event_id]
        events = (
            list(
                session.exec(
                    select(CurrentEvent).where(CurrentEvent.id.in_(event_ids))
                ).all()
            )
            if event_ids
            else []
        )

    event_by_id = {event.id: event for event in events}
    clusters: dict[tuple[str, str], list[EventOpinion]] = defaultdict(list)
    for opinion in opinions:
        clusters[_opinion_topic_discipline_key(opinion, event_by_id)].append(opinion)
    return [
        _representative_opinion_ids(cluster)
        for cluster in clusters.values()
        if len(cluster) >= min_opinions
    ]


async def _event_thematic_clusters(store: Any, since: datetime) -> list[list[str]]:
    if not _env_bool("ARTICLES_THEMATIC_ALLOW_RAW_EVENTS", False):
        return []
    min_events = _env_int(
        "ARTICLES_THEMATIC_MIN_EVENTS",
        DEFAULT_THEMATIC_MIN_EVENTS,
        minimum=2,
    )
    with store.session() as session:
        events = list(
            session.exec(
                select(CurrentEvent)
                .where(CurrentEvent.observed_at >= since)
                .order_by(CurrentEvent.observed_at)
            ).all()
        )

    clusters: dict[tuple[str, str], list[CurrentEvent]] = defaultdict(list)
    for event in events:
        clusters[_topic_discipline_key(event)].append(event)
    return [
        _representative_event_ids(cluster)
        for cluster in clusters.values()
        if len(cluster) >= min_events
    ]


async def thematic_trigger_check(store: Any) -> list[list[str]]:
    """
    Return recent thematic clusters.

    Firm opinions are the default source surface, because public articles should
    synthesize the firm's perspective rather than recap raw outside events.
    Raw CurrentEvent clusters remain available behind an explicit environment
    flag for one-off migrations or diagnostics.
    """

    since = _utcnow() - THEMATIC_WINDOW
    return [
        *await _opinion_thematic_clusters(store, since),
        *await _event_thematic_clusters(store, since),
    ]


def _nontrivial_stake_floor() -> Decimal:
    raw = os.environ.get("ARTICLES_POSTMORTEM_MIN_STAKE_USD", "1").strip()
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("1")


async def postmortem_trigger_check(store: Any) -> list[str]:
    """Return forecast ids with significant Brier and non-trivial paper/live stake."""

    stake_floor = _nontrivial_stake_floor()
    with store.session() as session:
        resolutions = list(session.exec(select(ForecastResolution)).all())
        bets = list(session.exec(select(ForecastBet)).all())

    stake_by_prediction: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for bet in bets:
        try:
            stake_by_prediction[bet.prediction_id] += Decimal(str(bet.stake_usd or 0))
        except Exception:
            continue

    out: list[str] = []
    for resolution in resolutions:
        if resolution.brier_score is None:
            continue
        if not (resolution.brier_score > 0.20 or resolution.brier_score < 0.04):
            continue
        if stake_by_prediction[resolution.prediction_id] < stake_floor:
            continue
        out.append(resolution.prediction_id)
    return out


async def correction_trigger_check(store: Any) -> list[str]:
    """Return opinion ids whose cited Conclusion was revoked in the last 24h."""

    since = _utcnow() - CORRECTION_WINDOW
    with store.session() as session:
        rows = list(
            session.exec(
                select(OpinionCitation, EventOpinion)
                .join(EventOpinion, EventOpinion.id == OpinionCitation.opinion_id)
                .where(OpinionCitation.is_revoked == True)  # noqa: E712
            ).all()
        )

    out: list[str] = []
    seen: set[str] = set()
    for citation, opinion in rows:
        if citation.source_kind.lower() != "conclusion":
            continue
        revoked_at = citation.revoked_at or opinion.revoked_at
        if revoked_at is None or _as_utc(revoked_at) < since:
            continue
        if opinion.id not in seen:
            out.append(opinion.id)
            seen.add(opinion.id)
    return out


async def triggered_article_candidates(store: Any) -> list[ArticleCandidate]:
    thematic, postmortem, correction = (
        await thematic_trigger_check(store),
        await postmortem_trigger_check(store),
        await correction_trigger_check(store),
    )
    candidates: list[ArticleCandidate] = []
    candidates.extend(ArticleCandidate(ArticleKind.THEMATIC, ids) for ids in thematic)
    candidates.extend(
        ArticleCandidate(ArticleKind.POSTMORTEM, [prediction_id])
        for prediction_id in postmortem
    )
    candidates.extend(
        ArticleCandidate(ArticleKind.CORRECTION, [opinion_id])
        for opinion_id in correction
    )
    return candidates


def _start_of_utc_day(now: datetime) -> datetime:
    now = _as_utc(now)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def dispatch_triggered_articles(
    store: Any,
    *,
    budget: Any,
    daily_cap: int = DEFAULT_DAILY_ARTICLE_CAP,
    now: datetime | None = None,
) -> list[Article]:
    """Dispatch trigger candidates, capped by already-published articles today."""

    if daily_cap <= 0:
        return []
    now = now or _utcnow()
    remaining = max(0, daily_cap - count_articles_since(store, _start_of_utc_day(now)))
    if remaining <= 0:
        return []

    published: list[Article] = []
    for candidate in await triggered_article_candidates(store):
        if len(published) >= remaining:
            break
        if article_already_published(
            store, kind=candidate.kind, source_ids=candidate.source_ids
        ):
            continue
        article = await generate_article(
            store,
            kind=candidate.kind,
            source_ids=candidate.source_ids,
            budget=budget,
        )
        if article is not None:
            published.append(article)
    return published
