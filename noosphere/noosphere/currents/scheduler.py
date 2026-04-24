"""Standing 5-minute scheduler loop for the currents pipeline.

Drives: ingest -> enrich -> relevance -> opine, once per cycle.

Invariants:
- Never runs inside the API process. The API tails the DB for new opinions
  and pushes them onto the in-process ``OpinionBus``. The scheduler never
  touches the bus directly.
- Budget balances are hourly and live on disk; they do not carry across
  hour boundaries (see ``HourlyBudgetGuard._roll_window``).
- Exceptions in any stage are logged and recorded on the ``CycleReport``;
  a single bad event cannot halt the loop.
- Budget exhaustion mid-cycle breaks out of the generator loop and signals
  a long backoff to the caller.

Entry points:
- ``run_cycle(store, cfg, budget)`` — one pass, returns a ``CycleReport``.
- ``loop(store, cfg, budget)`` — runs cycles on a fixed 5-minute cadence,
  with signal-driven shutdown.
- ``main(argv)`` — argparse frontend used by ``python -m noosphere.currents``.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from noosphere.currents.budget import BudgetExhausted, HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.enrich import enrich_event
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.relevance import RelevanceDecision, classify_relevance
from noosphere.currents.status import write_status
from noosphere.currents.x_ingestor import ingest_once
from noosphere.models import CurrentEventStatus
from noosphere.store import Store


logger = logging.getLogger("currents.scheduler")

CYCLE_SECONDS = 300
MAX_EVENTS_PER_CYCLE = 40
MAX_OPINIONS_PER_CYCLE = 12
SHORT_BACKOFF_SECONDS = 30
LONG_BACKOFF_SECONDS = CYCLE_SECONDS
# Window over which we consider an event "newly ingested this cycle". We key
# off source_captured_at (what list_current_event_ids filters on), so we pad
# generously — X posts can trail wall clock by tens of minutes.
SINCE_PADDING = timedelta(hours=24)


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
    errors: list[str] = field(default_factory=list)
    remaining_prompt_tokens: int = 0
    remaining_completion_tokens: int = 0


def _data_dir() -> Path:
    return Path(os.environ.get("NOOSPHERE_DATA_DIR", "./noosphere_data"))


def _open_store() -> Store:
    dd = _data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    db_path = dd.expanduser().resolve() / "noosphere.db"
    return Store.from_database_url(f"sqlite:///{db_path}")


async def _gather_candidate_event_ids(
    store: Store, *, since: datetime
) -> list[str]:
    """Return ids of events that are candidates for the opinion pipeline.

    We prefer ``status=OBSERVED`` + ``since=...`` (prompt 01 exposes both). If
    a Store variant does not support the kwarg, fall back to a broader fetch
    and filter in-process.
    """
    try:
        return store.list_current_event_ids(
            status=CurrentEventStatus.OBSERVED,
            since=since,
            limit=MAX_EVENTS_PER_CYCLE,
        )
    except TypeError:
        ids = store.list_current_event_ids(limit=MAX_EVENTS_PER_CYCLE * 2)
        out: list[str] = []
        for eid in ids:
            ev = store.get_current_event(eid)
            if ev is not None and ev.status == CurrentEventStatus.OBSERVED:
                out.append(eid)
                if len(out) >= MAX_EVENTS_PER_CYCLE:
                    break
        return out


async def run_cycle(
    store: Store,
    ingestor_cfg: IngestorConfig,
    budget: HourlyBudgetGuard,
) -> CycleReport:
    """Execute one ingest -> enrich -> relevance -> opine pass."""
    started = time.monotonic()
    started_at_dt = datetime.now(timezone.utc)
    started_at = started_at_dt.isoformat()
    cycle_id = f"cyc_{uuid4().hex[:10]}"
    errors: list[str] = []

    # 1. Ingest
    try:
        await ingest_once(store, ingestor_cfg)
    except Exception as e:  # noqa: BLE001
        logger.exception("ingest_failed cycle_id=%s", cycle_id)
        errors.append(f"ingest:{type(e).__name__}")

    # 2. Gather candidate OBSERVED events
    try:
        candidate_ids = await _gather_candidate_event_ids(
            store, since=started_at_dt - SINCE_PADDING
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("candidate_gather_failed cycle_id=%s", cycle_id)
        errors.append(f"gather:{type(e).__name__}")
        candidate_ids = []

    ingested = len(candidate_ids)
    enriched = 0
    abstained_insufficient = 0
    abstained_near_duplicate = 0
    abstained_budget = 0
    opined = 0
    budget_halted = False

    for event_id in candidate_ids:
        # 3. Enrich
        try:
            ev = store.get_current_event(event_id)
            if ev is None:
                continue
            enrich_event(store, ev)
            enriched += 1
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "enrich_failed cycle_id=%s event_id=%s", cycle_id, event_id
            )
            errors.append(f"enrich:{event_id}:{type(e).__name__}")
            continue

        if opined >= MAX_OPINIONS_PER_CYCLE:
            break

        # 4. Relevance (re-reads event; enrichment may have SUPPRESSED it)
        try:
            decision = classify_relevance(store, event_id)
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "relevance_failed cycle_id=%s event_id=%s", cycle_id, event_id
            )
            errors.append(f"relevance:{event_id}:{type(e).__name__}")
            continue

        if decision == RelevanceDecision.ABSTAIN_NEAR_DUPLICATE:
            abstained_near_duplicate += 1
            continue
        if decision == RelevanceDecision.ABSTAIN_INSUFFICIENT_SOURCES:
            abstained_insufficient += 1
            continue
        if decision == RelevanceDecision.SKIPPED:
            continue

        # 5. Generate
        try:
            ev = store.get_current_event(event_id)
            if ev is None:
                continue
            outcome = generate_opinion(store, ev, budget=budget)
        except BudgetExhausted:
            abstained_budget += 1
            budget_halted = True
            logger.warning("budget_exhausted_mid_cycle cycle_id=%s", cycle_id)
            break
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "generate_failed cycle_id=%s event_id=%s", cycle_id, event_id
            )
            errors.append(f"generate:{event_id}:{type(e).__name__}")
            continue

        if outcome is OpinionOutcome.PUBLISHED:
            opined += 1
        elif outcome is OpinionOutcome.ABSTAINED_BUDGET:
            abstained_budget += 1
            budget_halted = True
            logger.warning(
                "budget_abstained cycle_id=%s event_id=%s", cycle_id, event_id
            )
            break
        elif outcome in (
            OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES,
            OpinionOutcome.ABSTAINED_NEAR_DUPLICATE,
            OpinionOutcome.ABSTAINED_CITATION_FABRICATION,
        ):
            abstained_insufficient += 1

    duration_ms = int((time.monotonic() - started) * 1000)
    report = CycleReport(
        cycle_id=cycle_id,
        started_at=started_at,
        duration_ms=duration_ms,
        ingested=ingested,
        enriched=enriched,
        abstained_insufficient=abstained_insufficient,
        abstained_near_duplicate=abstained_near_duplicate,
        abstained_budget=abstained_budget,
        opined=opined,
        errors=errors,
        remaining_prompt_tokens=budget.remaining_prompt_tokens(),
        remaining_completion_tokens=budget.remaining_completion_tokens(),
    )
    # Stash the halt-flag on the report object as a private attribute so
    # ``loop()`` can distinguish "ran to completion" from "bailed on budget".
    report.__dict__["_budget_halted"] = budget_halted
    logger.info(
        "cycle_complete cycle_id=%s duration_ms=%d ingested=%d enriched=%d "
        "opined=%d abstained_insufficient=%d abstained_near_duplicate=%d "
        "abstained_budget=%d errors=%d",
        cycle_id,
        duration_ms,
        ingested,
        enriched,
        opined,
        abstained_insufficient,
        abstained_near_duplicate,
        abstained_budget,
        len(errors),
    )
    try:
        write_status(report)
    except Exception:  # noqa: BLE001
        logger.exception("status_write_failed cycle_id=%s", cycle_id)
    return report


async def loop(
    store: Store,
    ingestor_cfg: IngestorConfig,
    budget: HourlyBudgetGuard,
) -> None:
    """Run cycles forever with a 5-minute cadence until SIGTERM/SIGINT."""
    stop = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        logger.info("shutdown_signal_received")
        stop.set()

    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            running_loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, RuntimeError):
            # Windows / non-main-thread — fall through; Ctrl-C will still
            # interrupt ``asyncio.run`` at the top level.
            pass

    while not stop.is_set():
        t0 = time.monotonic()
        report: Optional[CycleReport] = None
        try:
            report = await run_cycle(store, ingestor_cfg, budget)
        except Exception:  # noqa: BLE001
            logger.exception("cycle_crashed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=SHORT_BACKOFF_SECONDS)
            except asyncio.TimeoutError:
                pass
            continue

        elapsed = time.monotonic() - t0
        sleep_for = max(5.0, CYCLE_SECONDS - elapsed)
        # Budget-exhaustion backoff: if the cycle bailed on budget and did
        # not publish anything, sleep a full cycle so we don't burn
        # attempts against an exhausted guard.
        if report is not None and report.__dict__.get("_budget_halted"):
            if report.opined == 0:
                sleep_for = LONG_BACKOFF_SECONDS

        try:
            await asyncio.wait_for(stop.wait(), timeout=sleep_for)
        except asyncio.TimeoutError:
            pass


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"name":"%(name)s","msg":"%(message)s"}'
        ),
    )


def _load_ingestor_config() -> IngestorConfig:
    try:
        return IngestorConfig.from_env()
    except Exception:  # noqa: BLE001
        # Missing curated/keywords files — still construct a valid config so
        # ``once`` can run and exit without crashing in dev shells.
        return IngestorConfig(
            bearer_token=os.environ.get("X_BEARER_TOKEN", ""),
            curated_accounts=[],
            topic_keywords=[],
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="noosphere.currents")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once", help="Run exactly one pipeline cycle and exit")
    sub.add_parser("loop", help="Run the standing 5-minute scheduler loop")
    args = parser.parse_args(argv)

    _configure_logging()

    store = _open_store()
    ingestor_cfg = _load_ingestor_config()
    budget_path = _data_dir() / "currents_budget.json"
    budget = HourlyBudgetGuard.load(budget_path)

    if args.cmd == "once":
        asyncio.run(run_cycle(store, ingestor_cfg, budget))
        return 0
    if args.cmd == "loop":
        asyncio.run(loop(store, ingestor_cfg, budget))
        return 0
    return 2


# Used by tests; keep asdict import available from this module
__all__ = [
    "CYCLE_SECONDS",
    "LONG_BACKOFF_SECONDS",
    "MAX_EVENTS_PER_CYCLE",
    "MAX_OPINIONS_PER_CYCLE",
    "SHORT_BACKOFF_SECONDS",
    "CycleReport",
    "asdict",
    "loop",
    "main",
    "run_cycle",
]
