from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from noosphere.currents._x_client import XAPIError, XClient, XPost
from noosphere.currents.config import IngestorConfig
from noosphere.ids import make_event_id
from noosphere.models import CurrentEvent, CurrentEventSource, CurrentEventStatus
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_hash(text: str, url: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower()) + "|" + url.strip().lower()


def _dedupe_hash(post: XPost) -> str:
    return hashlib.sha256(_normalize_for_hash(post.text, post.url).encode("utf-8")).hexdigest()


def _to_current_event(post: XPost, now: datetime) -> CurrentEvent:
    dhash = _dedupe_hash(post)
    return CurrentEvent(
        id=make_event_id(dhash),
        source=CurrentEventSource.X_POST,
        source_url=post.url,
        source_author_handle=f"@{post.author_handle}",
        source_captured_at=post.created_at,
        ingested_at=now,
        raw_text=post.text,
        dedupe_hash=dhash,
        embedding=None,
        topic_hint=None,
        status=CurrentEventStatus.OBSERVED,
    )


def make_client(cfg: IngestorConfig) -> XClient:
    """Factory used by tests to substitute a fake client."""
    return XClient(cfg.bearer_token, cfg.base_url, cfg.request_timeout_s)


async def ingest_once(store: Store, cfg: IngestorConfig, *, now: Optional[datetime] = None) -> int:
    """Run one ingestion pass. Returns count of new events written."""
    now = now or datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=cfg.lookback_minutes)
    client = make_client(cfg)
    new_count = 0

    async with httpx.AsyncClient() as http:
        for handle in cfg.curated_accounts:
            try:
                user_id = await client.user_id_for_handle(http, handle)
                if not user_id:
                    logger.warning("x_unknown_handle handle=%s", handle)
                    continue
                posts = await client.recent_posts_by_user(
                    http, user_id,
                    max_results=cfg.max_posts_per_account,
                    start_time=start_time,
                )
                new_count += _write_posts(store, posts, now)
            except XAPIError as e:
                logger.warning("x_handle_fetch_failed handle=%s error=%s", handle, e)

        for query in cfg.topic_keywords:
            try:
                posts = await client.search_recent(
                    http, query,
                    max_results=cfg.max_posts_per_keyword_query,
                    start_time=start_time,
                )
                new_count += _write_posts(store, posts, now)
            except XAPIError as e:
                logger.warning("x_query_fetch_failed query=%s error=%s", query, e)

    logger.info("ingest_pass_complete new_events=%d", new_count)
    return new_count


def _write_posts(store: Store, posts: list[XPost], now: datetime) -> int:
    written = 0
    for post in posts:
        ev = _to_current_event(post, now)
        if store.find_current_event_by_dedupe(ev.dedupe_hash) is not None:
            continue
        store.add_current_event(ev)
        written += 1
    return written
