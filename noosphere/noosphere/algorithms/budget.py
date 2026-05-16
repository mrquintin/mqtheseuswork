"""Hourly token budget guard for LogicalAlgorithm drafter calls.

The algorithm drafter is bounded by an hourly token ceiling so a
runaway loop cannot exhaust the LLM budget shared with the rest of
the firm.  We reuse the same ``HourlyBudgetGuard`` shape used by
Currents / Forecasts / Equities — same filesystem persistence
contract, same interprocess lock — and only re-express the env-driven
defaults so a process can pick the algorithm-layer ceilings without
mixing them with the Currents allocation.

Env vars:

* ``ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS`` — int (default 200_000)
* ``ALGORITHMS_BUDGET_HOURLY_COMPLETION_TOKENS`` — int (default 60_000)
* ``ALGORITHMS_BUDGET_PATH`` — path to the persistence JSON.  Defaults
  to ``./algorithms_budget.json``.

Per-draft reserve (the floor that triggers ``BudgetExhausted`` before
a call is issued) is intentionally tighter than the Currents reserve
because each algorithm draft is closer to a single completion than a
multi-message dialog.
"""

from __future__ import annotations

import os
from pathlib import Path

from noosphere.currents.budget import (
    BudgetExhausted,
    HourlyBudgetGuard,
    PersistentHourlyBudgetGuard,
)


PER_DRAFT_BUDGET_RESERVE_PROMPT = 4_000
PER_DRAFT_BUDGET_RESERVE_COMPLETION = 1_500


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_budget_path() -> Path:
    """Filesystem location the persistent guard reads / writes."""
    return Path(os.environ.get("ALGORITHMS_BUDGET_PATH", "algorithms_budget.json"))


def build_guard_from_env() -> HourlyBudgetGuard:
    """Construct an in-process guard seeded from the env ceilings.

    Useful for tests and short-running CLIs that do not need
    interprocess coordination.  Long-running schedulers should use
    :func:`load_persistent_guard`.
    """
    return HourlyBudgetGuard(
        max_prompt_tokens=_env_int(
            "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS", 200_000
        ),
        max_completion_tokens=_env_int(
            "ALGORITHMS_BUDGET_HOURLY_COMPLETION_TOKENS", 60_000
        ),
    )


def load_persistent_guard(
    path: Path | None = None,
) -> PersistentHourlyBudgetGuard:
    """Filesystem-backed guard sharable across worker processes.

    The first writer of ``path`` decides the ceilings.  When the file
    does not yet exist the guard is initialised with the env-derived
    ceilings; later readers reload whatever the file holds.
    """
    target = Path(path or default_budget_path())
    if not target.exists():
        seed = build_guard_from_env()
        target.parent.mkdir(parents=True, exist_ok=True)
        seed.save(target)
    return PersistentHourlyBudgetGuard(target)


def per_draft_reserve() -> tuple[int, int]:
    """Return (prompt, completion) the drafter must reserve per call."""
    return (
        PER_DRAFT_BUDGET_RESERVE_PROMPT,
        PER_DRAFT_BUDGET_RESERVE_COMPLETION,
    )


__all__ = [
    "BudgetExhausted",
    "PER_DRAFT_BUDGET_RESERVE_PROMPT",
    "PER_DRAFT_BUDGET_RESERVE_COMPLETION",
    "build_guard_from_env",
    "default_budget_path",
    "load_persistent_guard",
    "per_draft_reserve",
]
