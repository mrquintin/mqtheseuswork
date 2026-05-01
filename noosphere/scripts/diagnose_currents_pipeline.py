#!/usr/bin/env python3
"""Non-writing operator diagnosis for the Currents X -> opinion pipeline."""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from noosphere.currents._x_client import XClient, XPost  # noqa: E402
from noosphere.currents.config import IngestorConfig  # noqa: E402
from noosphere.currents.opinion_generator import (  # noqa: E402
    OpinionDryRun,
    generate_opinion,
)
from noosphere.currents.relevance import (  # noqa: E402
    MIN_SOURCES_FOR_OPINION,
    MIN_TOP_SCORE,
    quick_retrieve_for_event,
)
from noosphere.currents.scheduler import (  # noqa: E402
    _ensure_sqlite_parent,
    database_url_from_env,
)
from noosphere.models import CurrentEvent, CurrentEventSource  # noqa: E402
from noosphere.store import Store  # noqa: E402


class NoopBudget:
    def authorize(self, _est_prompt: int, _est_completion: int) -> None:
        return None

    def charge(self, _prompt: int, _completion: int) -> None:
        return None


class ReadOnlyEventStore:
    def __init__(self, store: Store, event: CurrentEvent) -> None:
        self._store = store
        self._event = event

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def get_current_event(self, event_id: str) -> CurrentEvent | None:
        if event_id == self._event.id:
            return self._event
        return self._store.get_current_event(event_id)

    def set_event_status(self, _event_id: str, _status: object) -> None:
        return None

    def add_event_opinion(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("diagnose_currents_pipeline.py must not write opinions")


def _status(ok: bool, skipped: bool = False) -> str:
    if skipped:
        return "SKIP"
    return "OK" if ok else "BREAK"


def _row(name: str, status: str, detail: str) -> tuple[str, str, str]:
    return (name, status, detail)


def _print_table(rows: list[tuple[str, str, str]]) -> None:
    widths = [
        max(len(row[idx]) for row in [("Link", "Status", "Detail"), *rows])
        for idx in range(3)
    ]
    print(
        f"{'Link'.ljust(widths[0])}  "
        f"{'Status'.ljust(widths[1])}  "
        f"{'Detail'.ljust(widths[2])}"
    )
    print(
        f"{'-' * widths[0]}  "
        f"{'-' * widths[1]}  "
        f"{'-' * widths[2]}"
    )
    for link, status, detail in rows:
        print(
            f"{link.ljust(widths[0])}  "
            f"{status.ljust(widths[1])}  "
            f"{detail.ljust(widths[2])}"
        )


def _post_event(post: XPost, organization_id: str) -> CurrentEvent:
    observed_at = datetime.now(UTC)
    raw_created = post.created_at.strip()
    try:
        observed_at = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
    except ValueError:
        pass
    return CurrentEvent(
        id=f"diagnose_{uuid.uuid4().hex}",
        organization_id=organization_id or "diagnostic",
        source=CurrentEventSource.X_TWITTER,
        external_id=post.id,
        author_handle=post.author_handle,
        text=post.text,
        url=post.url,
        observed_at=observed_at,
        dedupe_hash=f"diagnose_{post.id}_{uuid.uuid4().hex}",
    )


def _store_from_env() -> Store:
    database_url = database_url_from_env()
    _ensure_sqlite_parent(database_url)
    return Store.from_database_url(database_url)


async def _fetch_search_posts(cfg: IngestorConfig) -> tuple[list[XPost], list[str]]:
    if not cfg.bearer_token or not cfg.search_queries:
        return [], []

    posts: list[XPost] = []
    errors: list[str] = []
    client = XClient(
        bearer_token=cfg.bearer_token,
        base_url=cfg.base_url,
        request_timeout_s=cfg.request_timeout_s,
    )
    try:
        for query in cfg.search_queries:
            try:
                posts.extend(await client.search_recent(query, max_results=25))
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        await client.aclose()
    return posts, errors


async def diagnose() -> int:
    cfg = IngestorConfig.from_env()
    rows: list[tuple[str, str, str]] = []

    rows.append(
        _row(
            "X_BEARER_TOKEN",
            _status(bool(cfg.bearer_token)),
            f"present={bool(cfg.bearer_token)}",
        )
    )
    rows.append(
        _row(
            "Curated accounts",
            _status(bool(cfg.curated_accounts)),
            f"count={len(cfg.curated_accounts)}",
        )
    )
    rows.append(
        _row(
            "Search queries",
            _status(bool(cfg.search_queries)),
            f"count={len(cfg.search_queries)}",
        )
    )

    posts, search_errors = await _fetch_search_posts(cfg)
    rows.append(
        _row(
            "X recent search",
            _status(
                bool(posts),
                skipped=not cfg.bearer_token or not cfg.search_queries,
            ),
            f"returned={len(posts)} errors={len(search_errors)}",
        )
    )

    cleared: list[tuple[XPost, CurrentEvent]] = []
    relevance_errors: list[str] = []
    if posts:
        store = _store_from_env()
        for post in posts:
            event = _post_event(post, cfg.organization_id)
            try:
                hits = quick_retrieve_for_event(store, event, top_k=10)
            except Exception as exc:
                relevance_errors.append(f"{type(exc).__name__}: {exc}")
                continue
            qualifying = [hit for hit in hits if hit.score >= MIN_TOP_SCORE]
            if len(qualifying) >= MIN_SOURCES_FOR_OPINION:
                cleared.append((post, event))

    rows.append(
        _row(
            "Relevance gate",
            _status(bool(cleared), skipped=not posts),
            (
                f"cleared={len(cleared)}/{len(posts)} "
                f"threshold={MIN_SOURCES_FOR_OPINION}@{MIN_TOP_SCORE} "
                f"errors={len(relevance_errors)}"
            ),
        )
    )

    dry_run: OpinionDryRun | None = None
    if cleared:
        store = _store_from_env()
        _, event = cleared[0]
        result = await generate_opinion(
            ReadOnlyEventStore(store, event),
            event.id,
            budget=NoopBudget(),
            dry_run=True,
        )
        if isinstance(result, OpinionDryRun):
            dry_run = result

    rows.append(
        _row(
            "Opinion prompt",
            _status(bool(dry_run and dry_run.eligible), skipped=not cleared),
            (
                "conclusion_citations="
                f"{dry_run.prompt_conclusion_citations if dry_run else 0} "
                f"eligible={dry_run.eligible if dry_run else False} "
                f"reason={dry_run.reason if dry_run else 'none'}"
            ),
        )
    )

    rows.append(
        _row(
            "Disabled reasons",
            _status(not cfg.disabled_reasons),
            ",".join(cfg.disabled_reasons) if cfg.disabled_reasons else "none",
        )
    )

    _print_table(rows)
    if search_errors:
        print(f"\nX search errors: {len(search_errors)}")
    if relevance_errors:
        print(f"Relevance errors: {len(relevance_errors)}")
    if dry_run:
        print(f"Dry run: {asdict(dry_run)}")
    return 0


def main() -> int:
    return asyncio.run(diagnose())


if __name__ == "__main__":
    raise SystemExit(main())
