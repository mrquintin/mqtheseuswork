"""Standing Currents scheduler loop."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy.engine import make_url

from noosphere.articles.triggers import (
    DEFAULT_WEEKLY_ARTICLE_CAP,
    dispatch_triggered_articles,
)
from noosphere.config import get_settings
from noosphere.currents.budget import BudgetExhausted, PersistentHourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.status import write_status
from noosphere.models import CurrentEventStatus
from noosphere.currents.x_ingestor import ingest_once
from noosphere.store import Store

CYCLE_SECONDS = 300
MAX_EVENTS_PER_CYCLE = 40
MAX_OPINIONS_PER_CYCLE = 12
SHORT_BACKOFF_SECONDS = 30
LONG_BACKOFF_SECONDS = CYCLE_SECONDS
EMBED_BACKFILL_INTERVAL_SECONDS = 24 * 60 * 60
ARTICLE_DISPATCH_INTERVAL_SECONDS = 60 * 60
MAX_ARTICLES_PER_WEEK = DEFAULT_WEEKLY_ARTICLE_CAP

LOGGER = logging.getLogger(__name__)

RELEVANCE_OPINE = "OPINE"
RELEVANCE_ABSTAIN_INSUFFICIENT = "ABSTAIN_INSUFFICIENT_SOURCES"
RELEVANCE_ABSTAIN_BELOW_SIGNIFICANCE = "ABSTAIN_BELOW_SIGNIFICANCE_FLOOR"
RELEVANCE_ABSTAIN_OFF_DOMAIN = "ABSTAIN_OFF_DOMAIN"
RELEVANCE_ABSTAIN_NEAR_DUPLICATE = "ABSTAIN_NEAR_DUPLICATE"
BACKLOG_STATUSES = [CurrentEventStatus.OBSERVED, CurrentEventStatus.ENRICHED]


@dataclass
class CycleReport:
    cycle_id: str
    started_at: str
    duration_ms: int
    ingested: int
    enriched: int
    abstained_insufficient: int
    abstained_below_significance: int
    abstained_off_domain: int
    abstained_near_duplicate: int
    abstained_budget: int
    opined: int
    articles_published: int
    article_errors: list[str]
    errors: list[str]
    remaining_prompt_tokens: int
    remaining_completion_tokens: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remaining_tokens(budget: object, attr: str, max_attr: str, used_attr: str) -> int:
    value = getattr(budget, attr, None)
    if isinstance(value, int):
        return value
    guard = getattr(budget, "_guard", budget)
    reset = getattr(guard, "_reset_if_hour_rolled", None)
    if callable(reset):
        reset()
    max_value = int(getattr(guard, max_attr, 0) or 0)
    used_value = int(getattr(guard, used_attr, 0) or 0)
    return max(0, max_value - used_value)


def _remaining_prompt_tokens(budget: object) -> int:
    return _remaining_tokens(
        budget,
        "remaining_prompt_tokens",
        "max_prompt_tokens",
        "prompt_tokens",
    )


def _remaining_completion_tokens(budget: object) -> int:
    return _remaining_tokens(
        budget,
        "remaining_completion_tokens",
        "max_completion_tokens",
        "completion_tokens",
    )


def _decision_value(decision: object) -> str:
    return str(getattr(decision, "value", decision))


def enrich_event(store, event_id: str):
    from noosphere.currents.enrich import enrich_event as _enrich_event

    return _enrich_event(store, event_id)


def gate_significance(store, event_id: str, *, floor: float) -> bool:
    from noosphere.currents.relevance import gate_significance as _gate_significance

    event = store.get_current_event(event_id)
    if event is None:
        raise KeyError(f"unknown current event: {event_id}")
    return _gate_significance(event, floor=floor)


def check_relevance(
    store,
    event_id: str,
    *,
    significance_floor: float = 0.0,
    require_significance: bool = True,
):
    from noosphere.currents.relevance import check_relevance as _check_relevance

    return _check_relevance(
        store,
        event_id,
        significance_floor=significance_floor,
        require_significance=require_significance,
    )


def _event_ids_for_cycle(store: Store, new_event_ids: list[str]) -> list[str]:
    """Include restartable Currents backlog after newly ingested ids."""
    backlog_limit = max(0, MAX_EVENTS_PER_CYCLE - len(new_event_ids))
    backlog_ids = (
        store.list_current_event_ids_by_status(BACKLOG_STATUSES, limit=backlog_limit)
        if backlog_limit
        else []
    )
    ordered = list(dict.fromkeys([*new_event_ids, *backlog_ids]))
    return ordered[:MAX_EVENTS_PER_CYCLE]


async def run_cycle(
    store, ingestor_cfg, budget, *, publish_articles: bool = False
) -> CycleReport:
    """Run one ingest -> enrich -> significance -> KB relevance -> opinion pass."""
    monotonic_start = time.monotonic()
    started_at = _utc_now_iso()
    cycle_id = uuid.uuid4().hex
    errors: list[str] = []
    new_event_ids: list[str] = []
    significance_bypass_event_ids: set[str] = set()
    enriched = 0
    abstained_insufficient = 0
    abstained_below_significance = 0
    abstained_off_domain = 0
    abstained_near_duplicate = 0
    abstained_budget = 0
    opined = 0
    articles_published = 0
    article_errors: list[str] = []
    opinion_attempts = 0

    try:
        capped_cfg = replace(
            ingestor_cfg,
            max_events_per_cycle=min(
                int(
                    getattr(ingestor_cfg, "max_events_per_cycle", MAX_EVENTS_PER_CYCLE)
                ),
                MAX_EVENTS_PER_CYCLE,
            ),
        )
        ingest_report = await ingest_once(store, capped_cfg)
        cycle_id = ingest_report.cycle_id or cycle_id
        errors.extend(ingest_report.errors)
        new_event_ids = list(ingest_report.new_event_ids[:MAX_EVENTS_PER_CYCLE])
        significance_bypass_event_ids = set(
            getattr(ingest_report, "significance_bypass_event_ids", [])
        )
    except Exception as exc:
        errors.append(f"ingest:{type(exc).__name__}: {exc}")

    significance_floor = float(
        getattr(ingestor_cfg, "min_significance_score", 0.0) or 0.0
    )
    for event_id in _event_ids_for_cycle(store, new_event_ids):
        if opinion_attempts >= MAX_OPINIONS_PER_CYCLE:
            errors.append(
                f"event:{event_id}:opinion_cap_reached:{MAX_OPINIONS_PER_CYCLE}"
            )
            break
        try:
            enrichment = enrich_event(store, event_id)
            enriched += 1
            if enrichment.is_near_duplicate:
                abstained_near_duplicate += 1
                continue

            requires_significance = event_id not in significance_bypass_event_ids
            if requires_significance and not gate_significance(
                store,
                event_id,
                floor=significance_floor,
            ):
                store.set_event_status(event_id, CurrentEventStatus.ABSTAINED)
                abstained_below_significance += 1
                continue

            decision = check_relevance(
                store,
                event_id,
                significance_floor=significance_floor,
                require_significance=False,
            )
            decision_value = _decision_value(decision)

            if decision_value == RELEVANCE_ABSTAIN_NEAR_DUPLICATE:
                abstained_near_duplicate += 1
                continue
            if decision_value == RELEVANCE_ABSTAIN_BELOW_SIGNIFICANCE:
                abstained_below_significance += 1
                continue
            if decision_value == RELEVANCE_ABSTAIN_OFF_DOMAIN:
                abstained_off_domain += 1
                continue
            if decision_value == RELEVANCE_ABSTAIN_INSUFFICIENT:
                abstained_insufficient += 1
                continue
            if decision_value != RELEVANCE_OPINE:
                errors.append(
                    f"event:{event_id}:unknown_relevance_decision:{decision_value}"
                )
                continue

            opinion_attempts += 1
            try:
                outcome = await generate_opinion(store, event_id, budget=budget)
            except BudgetExhausted as exc:
                abstained_budget += 1
                errors.append(f"event:{event_id}:BudgetExhausted: {exc}")
                break

            if outcome == OpinionOutcome.PUBLISHED:
                opined += 1
                try:
                    from noosphere.social.currents_bridge import (
                        create_x_draft_for_event_opinion,
                    )

                    await create_x_draft_for_event_opinion(store, event_id)
                except Exception as exc:
                    errors.append(
                        f"event:{event_id}:social_draft:{type(exc).__name__}: {exc}"
                    )
            elif outcome == OpinionOutcome.ABSTAINED_BUDGET:
                abstained_budget += 1
                break
            elif outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES:
                abstained_insufficient += 1
            elif outcome == OpinionOutcome.ABSTAINED_OFF_DOMAIN:
                abstained_off_domain += 1
            elif outcome == OpinionOutcome.ABSTAINED_NEAR_DUPLICATE:
                abstained_near_duplicate += 1
            else:
                errors.append(f"event:{event_id}:opinion_outcome:{outcome.value}")
        except Exception as exc:
            errors.append(f"event:{event_id}:{type(exc).__name__}: {exc}")

    if publish_articles:
        articles_published, article_errors = await _dispatch_articles_if_due(
            store,
            budget,
        )
        errors.extend(article_errors)

    duration_ms = int((time.monotonic() - monotonic_start) * 1000)
    return CycleReport(
        cycle_id=cycle_id,
        started_at=started_at,
        duration_ms=duration_ms,
        ingested=len(new_event_ids),
        enriched=enriched,
        abstained_insufficient=abstained_insufficient,
        abstained_below_significance=abstained_below_significance,
        abstained_off_domain=abstained_off_domain,
        abstained_near_duplicate=abstained_near_duplicate,
        abstained_budget=abstained_budget,
        opined=opined,
        articles_published=articles_published,
        article_errors=article_errors,
        errors=errors,
        remaining_prompt_tokens=_remaining_prompt_tokens(budget),
        remaining_completion_tokens=_remaining_completion_tokens(budget),
    )


def _log_cycle(report: CycleReport) -> None:
    LOGGER.info(
        "currents_cycle cycle_id=%s started_at=%s duration_ms=%d "
        "ingested=%d enriched=%d abstained_insufficient=%d "
        "abstained_below_significance=%d abstained_off_domain=%d "
        "abstained_near_duplicate=%d abstained_budget=%d opined=%d "
        "articles_published=%d remaining_prompt_tokens=%d "
        "remaining_completion_tokens=%d article_errors=%s errors=%s",
        report.cycle_id,
        report.started_at,
        report.duration_ms,
        report.ingested,
        report.enriched,
        report.abstained_insufficient,
        report.abstained_below_significance,
        report.abstained_off_domain,
        report.abstained_near_duplicate,
        report.abstained_budget,
        report.opined,
        report.articles_published,
        report.remaining_prompt_tokens,
        report.remaining_completion_tokens,
        json.dumps(report.article_errors, separators=(",", ":")),
        json.dumps(report.errors, separators=(",", ":")),
    )


async def _sleep_or_stop(seconds: float, stop_event: asyncio.Event) -> None:
    if seconds <= 0 or stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _embed_backfill_marker_path() -> Path:
    explicit = os.environ.get("EMBED_BACKFILL_MARKER_PATH", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "embed_backfill_last_run.json"
    return get_settings().data_dir / "embed_backfill_last_run.json"


def _last_embed_backfill_ts(path: Path) -> float | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("finished_at_unix")
        return float(value) if value is not None else None
    except Exception:
        return None


def _write_embed_backfill_marker(path: Path, *, ok: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finished_at_unix": time.time(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _run_embed_backfill_if_due(store: Store) -> None:
    if not _env_bool("EMBED_BACKFILL_ENABLED", True):
        return
    marker = _embed_backfill_marker_path()
    interval = max(
        60,
        _env_int("EMBED_BACKFILL_INTERVAL_SECONDS", EMBED_BACKFILL_INTERVAL_SECONDS),
    )
    last = _last_embed_backfill_ts(marker)
    now = time.time()
    if last is not None and now - last < interval:
        return
    try:
        from noosphere.cli_commands.embed_backfill import run_backfill

        report = run_backfill(store=store)
        _write_embed_backfill_marker(marker, ok=not report.errors)
    except Exception:
        LOGGER.exception("embed_backfill.scheduler_failed")
        _write_embed_backfill_marker(marker, ok=False)


def _article_dispatch_marker_path() -> Path:
    explicit = os.environ.get("ARTICLES_DISPATCH_MARKER_PATH", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "currents_articles_last_run.json"
    return get_settings().data_dir / "currents_articles_last_run.json"


def _last_article_dispatch_ts(path: Path) -> float | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("finished_at_unix")
        return float(value) if value is not None else None
    except Exception:
        return None


def _write_article_dispatch_marker(path: Path, *, ok: bool, published: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finished_at_unix": time.time(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "published": published,
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


async def _dispatch_articles_if_due(
    store: Store, budget: object
) -> tuple[int, list[str]]:
    if not _env_bool("ARTICLES_ENABLED", True):
        return 0, []
    marker = _article_dispatch_marker_path()
    interval_default = _env_int(
        "FORECASTS_ARTICLE_INTERVAL_S",
        ARTICLE_DISPATCH_INTERVAL_SECONDS,
    )
    interval = max(
        60,
        _env_int("ARTICLES_DISPATCH_INTERVAL_SECONDS", interval_default),
    )
    last = _last_article_dispatch_ts(marker)
    if last is not None and time.time() - last < interval:
        return 0, []

    weekly_cap = _env_int("NOOSPHERE_ARTICLES_WEEKLY_CAP", MAX_ARTICLES_PER_WEEK)
    if weekly_cap < 0:
        weekly_cap = MAX_ARTICLES_PER_WEEK
    if weekly_cap <= 0:
        _write_article_dispatch_marker(marker, ok=True, published=0)
        return 0, []

    try:
        articles = await dispatch_triggered_articles(
            store,
            budget=budget,
            weekly_cap=weekly_cap,
        )
    except BudgetExhausted as exc:
        _write_article_dispatch_marker(marker, ok=False, published=0)
        return 0, [f"articles:BudgetExhausted: {exc}"]
    except Exception as exc:
        LOGGER.exception("articles.dispatch_failed")
        _write_article_dispatch_marker(marker, ok=False, published=0)
        return 0, [f"articles:{type(exc).__name__}: {exc}"]

    published = len(articles)
    _write_article_dispatch_marker(marker, ok=True, published=published)
    return published, []


async def loop(store, ingestor_cfg, budget):
    """Run the standing scheduler until SIGINT/SIGTERM."""
    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            running_loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda _signum, _frame: stop_event.set())

    while not stop_event.is_set():
        cycle_started = time.monotonic()
        try:
            _run_embed_backfill_if_due(store)
            report = await run_cycle(store, ingestor_cfg, budget, publish_articles=True)
            write_status(report)
            _log_cycle(report)
            if report.abstained_budget > 0:
                await _sleep_or_stop(LONG_BACKOFF_SECONDS, stop_event)
                continue
            elapsed = time.monotonic() - cycle_started
            await _sleep_or_stop(max(0.0, CYCLE_SECONDS - elapsed), stop_event)
        except BudgetExhausted:
            LOGGER.warning("currents_scheduler_budget_exhausted")
            await _sleep_or_stop(LONG_BACKOFF_SECONDS, stop_event)
        except Exception:
            LOGGER.exception("currents_scheduler_cycle_crashed")
            await _sleep_or_stop(SHORT_BACKOFF_SECONDS, stop_event)


def database_url_from_env() -> str:
    explicit = os.environ.get("DATABASE_URL") or os.environ.get("THESEUS_DATABASE_URL")
    if explicit:
        return explicit
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return f"sqlite:///{Path(data_dir) / 'noosphere.db'}"
    return get_settings().database_url


def budget_path_from_env() -> Path:
    explicit = os.environ.get("CURRENTS_BUDGET_PATH", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "currents_budget.json"
    return get_settings().data_dir / "currents_budget.json"


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def _bootstrap_store() -> Store:
    database_url = database_url_from_env()
    _ensure_sqlite_parent(database_url)
    return Store.from_database_url(database_url)


def _configure_logging() -> None:
    level_name = (
        os.environ.get("CURRENTS_LOG_LEVEL") or os.environ.get("LOG_LEVEL") or "INFO"
    )
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.currents")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("once", help="run one Currents scheduler cycle")
    subcommands.add_parser("loop", help="run the standing Currents scheduler loop")
    args = parser.parse_args(argv)

    _configure_logging()
    store = _bootstrap_store()
    ingestor_cfg = IngestorConfig.from_env()
    budget = PersistentHourlyBudgetGuard(budget_path_from_env())

    if args.command == "once":
        report = asyncio.run(
            run_cycle(store, ingestor_cfg, budget, publish_articles=True)
        )
        write_status(report)
        _log_cycle(report)
        print(json.dumps({"last_cycle": asdict(report)}, indent=2, sort_keys=True))
        return 0

    asyncio.run(loop(store, ingestor_cfg, budget))
    return 0
