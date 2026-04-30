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

LOGGER = logging.getLogger(__name__)

RELEVANCE_OPINE = "OPINE"
RELEVANCE_ABSTAIN_INSUFFICIENT = "ABSTAIN_INSUFFICIENT_SOURCES"
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
    abstained_near_duplicate: int
    abstained_budget: int
    opined: int
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


def check_relevance(store, event_id: str):
    from noosphere.currents.relevance import check_relevance as _check_relevance

    return _check_relevance(store, event_id)


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


async def run_cycle(store, ingestor_cfg, budget) -> CycleReport:
    """Run one ingest -> enrich -> relevance -> opinion pass."""
    monotonic_start = time.monotonic()
    started_at = _utc_now_iso()
    cycle_id = uuid.uuid4().hex
    errors: list[str] = []
    new_event_ids: list[str] = []
    enriched = 0
    abstained_insufficient = 0
    abstained_near_duplicate = 0
    abstained_budget = 0
    opined = 0
    opinion_attempts = 0

    try:
        capped_cfg = replace(
            ingestor_cfg,
            max_events_per_cycle=min(
                int(getattr(ingestor_cfg, "max_events_per_cycle", MAX_EVENTS_PER_CYCLE)),
                MAX_EVENTS_PER_CYCLE,
            ),
        )
        ingest_report = await ingest_once(store, capped_cfg)
        cycle_id = ingest_report.cycle_id or cycle_id
        errors.extend(ingest_report.errors)
        new_event_ids = list(ingest_report.new_event_ids[:MAX_EVENTS_PER_CYCLE])
    except Exception as exc:
        errors.append(f"ingest:{type(exc).__name__}: {exc}")

    for event_id in _event_ids_for_cycle(store, new_event_ids):
        if opinion_attempts >= MAX_OPINIONS_PER_CYCLE:
            errors.append(
                f"event:{event_id}:opinion_cap_reached:{MAX_OPINIONS_PER_CYCLE}"
            )
            break
        try:
            enrichment = enrich_event(store, event_id)
            enriched += 1
            decision = check_relevance(store, event_id)
            decision_value = _decision_value(decision)

            if (
                enrichment.is_near_duplicate
                or decision_value == RELEVANCE_ABSTAIN_NEAR_DUPLICATE
            ):
                abstained_near_duplicate += 1
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
            elif outcome == OpinionOutcome.ABSTAINED_BUDGET:
                abstained_budget += 1
                break
            elif outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES:
                abstained_insufficient += 1
            elif outcome == OpinionOutcome.ABSTAINED_NEAR_DUPLICATE:
                abstained_near_duplicate += 1
            else:
                errors.append(f"event:{event_id}:opinion_outcome:{outcome.value}")
        except Exception as exc:
            errors.append(f"event:{event_id}:{type(exc).__name__}: {exc}")

    duration_ms = int((time.monotonic() - monotonic_start) * 1000)
    return CycleReport(
        cycle_id=cycle_id,
        started_at=started_at,
        duration_ms=duration_ms,
        ingested=len(new_event_ids),
        enriched=enriched,
        abstained_insufficient=abstained_insufficient,
        abstained_near_duplicate=abstained_near_duplicate,
        abstained_budget=abstained_budget,
        opined=opined,
        errors=errors,
        remaining_prompt_tokens=_remaining_prompt_tokens(budget),
        remaining_completion_tokens=_remaining_completion_tokens(budget),
    )


def _log_cycle(report: CycleReport) -> None:
    LOGGER.info(
        "currents_cycle cycle_id=%s started_at=%s duration_ms=%d "
        "ingested=%d enriched=%d abstained_insufficient=%d "
        "abstained_near_duplicate=%d abstained_budget=%d opined=%d "
        "remaining_prompt_tokens=%d remaining_completion_tokens=%d errors=%s",
        report.cycle_id,
        report.started_at,
        report.duration_ms,
        report.ingested,
        report.enriched,
        report.abstained_insufficient,
        report.abstained_near_duplicate,
        report.abstained_budget,
        report.opined,
        report.remaining_prompt_tokens,
        report.remaining_completion_tokens,
        json.dumps(report.errors, separators=(",", ":")),
    )


async def _sleep_or_stop(seconds: float, stop_event: asyncio.Event) -> None:
    if seconds <= 0 or stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


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
            report = await run_cycle(store, ingestor_cfg, budget)
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
        os.environ.get("CURRENTS_LOG_LEVEL")
        or os.environ.get("LOG_LEVEL")
        or "INFO"
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
        report = asyncio.run(run_cycle(store, ingestor_cfg, budget))
        write_status(report)
        _log_cycle(report)
        print(json.dumps({"last_cycle": asdict(report)}, indent=2, sort_keys=True))
        return 0

    asyncio.run(loop(store, ingestor_cfg, budget))
    return 0
