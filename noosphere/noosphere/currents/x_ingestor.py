"""X/Twitter Currents ingestion orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from noosphere.currents._x_client import MissingCredentials, XClient, XPost
from noosphere.currents.config import IngestorConfig
from noosphere.currents.dedupe import dedupe_hash
from noosphere.models import CurrentEvent, CurrentEventSource, CurrentEventStatus


@dataclass
class IngestReport:
    cycle_id: str
    fetched: int
    new_event_ids: list[str]
    duplicates: int
    errors: list[str]

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
    )


async def ingest_once(store: Any, cfg: IngestorConfig) -> IngestReport:
    client = make_client(cfg)
    new_ids: list[str] = []
    errors: list[str] = []
    fetched = 0
    duplicates = 0
    try:
        for user_id in cfg.curated_accounts:
            if len(new_ids) >= cfg.max_events_per_cycle:
                break
            try:
                posts = await client.fetch_user_tweets(user_id)
                fetched += len(posts)
                for post in posts:
                    if len(new_ids) >= cfg.max_events_per_cycle:
                        break
                    if _persist_or_skip(store, cfg, post, "X_TWITTER", new_ids):
                        continue
                    duplicates += 1
            except Exception as exc:
                errors.append(f"user:{user_id}:{type(exc).__name__}: {exc}")

        for query in cfg.search_queries:
            if len(new_ids) >= cfg.max_events_per_cycle:
                break
            try:
                posts = await client.search_recent(query)
                fetched += len(posts)
                for post in posts:
                    if len(new_ids) >= cfg.max_events_per_cycle:
                        break
                    if _persist_or_skip(store, cfg, post, "X_TWITTER", new_ids):
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
    )


def _persist_or_skip(
    store: Any,
    cfg: IngestorConfig,
    post: XPost,
    source: str,
    out: list[str],
) -> bool:
    """Return True if the post was persisted, False if skipped as a duplicate."""

    h = dedupe_hash(post.text, post.url)
    if not h:
        raise ValueError("dedupe hash must not be empty")
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
        status=CurrentEventStatus.OBSERVED,
    )
    expected_event_id = event.id
    event_id = store.add_current_event(event)
    if event_id != expected_event_id:
        return False
    out.append(event_id)
    return True


def _parse_created_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
