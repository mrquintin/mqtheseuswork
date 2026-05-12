"""X/Twitter Currents ingestion orchestration."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from noosphere.currents._x_client import MissingCredentials, XClient, XPost
from noosphere.currents.config import IngestorConfig
from noosphere.currents.dedupe import dedupe_hash
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    XSignificanceMetrics,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class IngestReport:
    cycle_id: str
    fetched: int
    new_event_ids: list[str]
    duplicates: int
    errors: list[str]
    significance_bypass_event_ids: list[str] = field(default_factory=list)
    rejected_below_significance: int = 0

    @property
    def dedupe_collision_rate(self) -> float:
        if self.fetched == 0:
            return 0.0
        return self.duplicates / self.fetched


def make_client(cfg: IngestorConfig) -> XClient:
    if not cfg.bearer_token:
        raise MissingCredentials("X_BEARER_TOKEN not set")
    return XClient(
        bearer_token=cfg.bearer_token,
        base_url=cfg.base_url,
        request_timeout_s=cfg.request_timeout_s,
        discovery_query=cfg.discovery_query,
    )


async def ingest_once(store: Any, cfg: IngestorConfig) -> IngestReport:
    disabled_reasons = cfg.disabled_reasons
    if disabled_reasons:
        LOGGER.warning(
            "currents.x_ingestion.disabled reason=%s",
            ",".join(disabled_reasons),
        )
        return IngestReport(
            cycle_id=uuid.uuid4().hex,
            fetched=0,
            new_event_ids=[],
            duplicates=0,
            errors=[],
        )

    client = make_client(cfg)
    new_ids: list[str] = []
    errors: list[str] = []
    fetched = 0
    duplicates = 0
    rejected_below_significance = 0
    significance_bypass_event_ids: list[str] = []
    seen_hashes: set[str] = set()
    try:
        fetch_trending = getattr(client, "fetch_trending_candidates", None)
        if (
            cfg.discovery_enabled
            and cfg.discovery_max_candidates > 0
            and callable(fetch_trending)
        ):
            try:
                posts = await fetch_trending(
                    locale=cfg.discovery_locale,
                    max_results=cfg.discovery_max_candidates,
                )
                fetched += len(posts)
                for post in _sort_posts_by_significance(posts):
                    if len(new_ids) >= cfg.max_events_per_cycle:
                        break
                    metrics = _significance_metrics(post.metrics)
                    if not _passes_significance_filters(metrics, cfg):
                        rejected_below_significance += 1
                        continue
                    if _persist_or_skip(
                        store,
                        cfg,
                        post,
                        "X_TWITTER",
                        new_ids,
                        seen_hashes=seen_hashes,
                    ):
                        continue
                    duplicates += 1
            except Exception as exc:
                errors.append(f"discovery:{type(exc).__name__}: {exc}")

        for user_id in cfg.curated_accounts:
            if len(new_ids) >= cfg.max_events_per_cycle:
                break
            try:
                posts = await client.fetch_user_tweets(user_id)
                fetched += len(posts)
                for post in posts:
                    if len(new_ids) >= cfg.max_events_per_cycle:
                        break
                    before = len(new_ids)
                    if _persist_or_skip(
                        store,
                        cfg,
                        post,
                        "X_TWITTER",
                        new_ids,
                        seen_hashes=seen_hashes,
                    ):
                        if len(new_ids) > before:
                            significance_bypass_event_ids.append(new_ids[-1])
                        continue
                    duplicates += 1
            except Exception as exc:
                errors.append(f"user:{user_id}:{type(exc).__name__}: {exc}")

        for query in cfg.search_queries:
            if len(new_ids) >= cfg.max_events_per_cycle:
                break
            try:
                LOGGER.info(
                    "currents.x_ingestion.targeted_augmentation query=%r",
                    query,
                )
                posts = await client.search_recent(query)
                fetched += len(posts)
                for post in posts:
                    if len(new_ids) >= cfg.max_events_per_cycle:
                        break
                    metrics = _significance_metrics(post.metrics)
                    if not _passes_significance_filters(metrics, cfg):
                        rejected_below_significance += 1
                        continue
                    if _persist_or_skip(
                        store,
                        cfg,
                        post,
                        "X_TWITTER",
                        new_ids,
                        seen_hashes=seen_hashes,
                    ):
                        continue
                    duplicates += 1
            except Exception as exc:
                errors.append(f"query:{query!r}:{type(exc).__name__}: {exc}")
    finally:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()

    return IngestReport(
        cycle_id=uuid.uuid4().hex,
        fetched=fetched,
        new_event_ids=new_ids,
        duplicates=duplicates,
        errors=errors,
        significance_bypass_event_ids=significance_bypass_event_ids,
        rejected_below_significance=rejected_below_significance,
    )


def _persist_or_skip(
    store: Any,
    cfg: IngestorConfig,
    post: XPost,
    source: str,
    out: list[str],
    *,
    seen_hashes: set[str] | None = None,
) -> bool:
    """Return True if the post was persisted, False if skipped as a duplicate."""

    h = dedupe_hash(post.text, post.url)
    if not h:
        raise ValueError("dedupe hash must not be empty")
    if seen_hashes is not None and h in seen_hashes:
        return False
    if store.find_current_event_by_dedupe(h):
        return False

    event = CurrentEvent(
        organization_id=cfg.organization_id,
        source=CurrentEventSource(source),
        external_id=post.id,
        author_handle=post.author_handle,
        text=post.text,
        url=post.url,
        observed_at=_parse_created_at(post.created_at),
        dedupe_hash=h,
        metrics=_significance_metrics(post.metrics),
        status=CurrentEventStatus.OBSERVED,
    )
    expected_event_id = event.id
    event_id = store.add_current_event(event)
    if event_id != expected_event_id:
        return False
    out.append(event_id)
    if seen_hashes is not None:
        seen_hashes.add(h)
    return True


def _significance_metrics(value: Any) -> XSignificanceMetrics | None:
    if value is None:
        return None
    if isinstance(value, XSignificanceMetrics):
        return value
    if isinstance(value, dict):
        try:
            return XSignificanceMetrics.model_validate(value)
        except Exception:
            return None
    return XSignificanceMetrics(
        like_count=getattr(value, "like_count", 0),
        retweet_count=getattr(value, "retweet_count", 0),
        reply_count=getattr(value, "reply_count", 0),
        quote_count=getattr(value, "quote_count", 0),
        bookmark_count=getattr(value, "bookmark_count", 0),
        impression_count=getattr(value, "impression_count", 0),
    )


def _passes_significance_filters(
    metrics: XSignificanceMetrics | None,
    cfg: IngestorConfig,
) -> bool:
    if metrics is None:
        return False
    if metrics.significance_score >= cfg.min_significance_score:
        return True
    return (
        (cfg.min_likes > 0 and metrics.like_count >= cfg.min_likes)
        or (cfg.min_retweets > 0 and metrics.retweet_count >= cfg.min_retweets)
        or (cfg.min_impressions > 0 and metrics.impression_count >= cfg.min_impressions)
    )


def _sort_posts_by_significance(posts: list[XPost]) -> list[XPost]:
    return sorted(posts, key=_significance_sort_key, reverse=True)


def _significance_sort_key(post: XPost) -> tuple[float, int, int, int]:
    metrics = _significance_metrics(post.metrics)
    if metrics is None:
        return (0.0, 0, 0, 0)
    return (
        metrics.significance_score,
        metrics.impression_count,
        metrics.retweet_count,
        metrics.like_count,
    )


def _parse_created_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
