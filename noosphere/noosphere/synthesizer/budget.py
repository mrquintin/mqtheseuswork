"""Token budget guard for the synthesizer.

The synthesizer is bounded by an hourly token ceiling — like the
algorithm drafter — so an over-active operator (or a runaway
scheduler) cannot exhaust the LLM allocation the rest of the firm
relies on. Internally we reuse ``HourlyBudgetGuard`` so the budget
file format and inter-process lock semantics are identical to the
other layers; only the env-driven defaults differ.

Env vars:

* ``SYNTHESIZER_BUDGET_HOURLY_PROMPT_TOKENS`` — int (default 80_000)
* ``SYNTHESIZER_BUDGET_HOURLY_COMPLETION_TOKENS`` — int (default 30_000)
* ``SYNTHESIZER_BUDGET_PATH`` — path to the persistence JSON. Defaults
  to ``./synthesizer_budget.json``.

Per-synthesis reserve is tighter than the drafter's because a
synthesis call is a single Haiku completion plus its prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

from noosphere.currents.budget import (
    BudgetExhausted,
    HourlyBudgetGuard,
    PersistentHourlyBudgetGuard,
)


PER_SYNTHESIS_BUDGET_RESERVE_PROMPT = 3_000
PER_SYNTHESIS_BUDGET_RESERVE_COMPLETION = 1_200


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_budget_path() -> Path:
    """Filesystem location of the persistent guard."""
    return Path(
        os.environ.get("SYNTHESIZER_BUDGET_PATH", "synthesizer_budget.json")
    )


def build_guard_from_env() -> HourlyBudgetGuard:
    """In-process guard seeded from env ceilings.

    Useful for tests and the ad-hoc CLI. Long-running schedulers should
    use :func:`load_persistent_guard` so concurrent processes share one
    ledger.
    """
    return HourlyBudgetGuard(
        max_prompt_tokens=_env_int(
            "SYNTHESIZER_BUDGET_HOURLY_PROMPT_TOKENS", 80_000
        ),
        max_completion_tokens=_env_int(
            "SYNTHESIZER_BUDGET_HOURLY_COMPLETION_TOKENS", 30_000
        ),
    )


def load_persistent_guard(
    path: Path | None = None,
) -> PersistentHourlyBudgetGuard:
    """Filesystem-backed guard sharable across worker processes."""
    target = Path(path or default_budget_path())
    if not target.exists():
        seed = build_guard_from_env()
        target.parent.mkdir(parents=True, exist_ok=True)
        seed.save(target)
    return PersistentHourlyBudgetGuard(target)


def per_synthesis_reserve() -> tuple[int, int]:
    """``(prompt, completion)`` the synthesizer must reserve per call."""
    return (
        PER_SYNTHESIS_BUDGET_RESERVE_PROMPT,
        PER_SYNTHESIS_BUDGET_RESERVE_COMPLETION,
    )


__all__ = [
    "BudgetExhausted",
    "PER_SYNTHESIS_BUDGET_RESERVE_PROMPT",
    "PER_SYNTHESIS_BUDGET_RESERVE_COMPLETION",
    "build_guard_from_env",
    "default_budget_path",
    "load_persistent_guard",
    "per_synthesis_reserve",
]
