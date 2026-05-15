"""Equity-signal hourly token budget guard.

Mirrors :mod:`noosphere.forecasts.budget` but reads its ceilings from
``EQUITIES_BUDGET_HOURLY_PROMPT_TOKENS`` /
``EQUITIES_BUDGET_HOURLY_COMPLETION_TOKENS`` and persists to its own
``equities_budget.json`` so the Equities track cannot starve the
Currents or Forecasts tracks (and vice versa).
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from noosphere.currents.budget import (
    BudgetExhausted,
    HourlyBudgetGuard as _BaseHourlyBudgetGuard,
    _interprocess_lock,
)

DEFAULT_PROMPT_TOKENS_HOUR = int(
    os.getenv("EQUITIES_BUDGET_HOURLY_PROMPT_TOKENS", "800000")
)
DEFAULT_COMPLETION_TOKENS_HOUR = int(
    os.getenv("EQUITIES_BUDGET_HOURLY_COMPLETION_TOKENS", "250000")
)
PER_SIGNAL_RESERVE_PROMPT = 12_000
PER_SIGNAL_RESERVE_COMPLETION = 3_000
DEFAULT_BUDGET_PATH = Path("/var/lib/theseus/equities_budget.json")


class HourlyBudgetGuard(_BaseHourlyBudgetGuard):
    """HourlyBudgetGuard with Equities ceilings and per-call reserve."""

    def __init__(
        self,
        max_prompt_tokens: int = DEFAULT_PROMPT_TOKENS_HOUR,
        max_completion_tokens: int = DEFAULT_COMPLETION_TOKENS_HOUR,
        window_start_iso: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        super().__init__(
            max_prompt_tokens=max_prompt_tokens,
            max_completion_tokens=max_completion_tokens,
            window_start_iso=window_start_iso,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        self._reset_if_hour_rolled()
        prompt_after = self.prompt_tokens + max(0, int(est_prompt))
        completion_after = self.completion_tokens + max(0, int(est_completion))
        prompt_remaining = self.max_prompt_tokens - prompt_after
        completion_remaining = self.max_completion_tokens - completion_after
        if (
            prompt_remaining < PER_SIGNAL_RESERVE_PROMPT
            or completion_remaining < PER_SIGNAL_RESERVE_COMPLETION
        ):
            raise BudgetExhausted("hourly Equities LLM token budget exhausted")


class PersistentHourlyBudgetGuard:
    """Filesystem-backed Equities budget guard for separate processes."""

    def __init__(self, path: Path = DEFAULT_BUDGET_PATH) -> None:
        self.path = Path(path)
        self._lock = Lock()
        self._guard = HourlyBudgetGuard.load(self.path)

    def _reload_locked(self) -> HourlyBudgetGuard:
        self._guard = HourlyBudgetGuard.load(self.path)
        return self._guard

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        with self._lock, _interprocess_lock(self.path):
            guard = self._reload_locked()
            guard.authorize(est_prompt, est_completion)
            guard.save(self.path)

    def charge(self, prompt: int, completion: int) -> None:
        with self._lock, _interprocess_lock(self.path):
            guard = self._reload_locked()
            guard.charge(prompt, completion)
            guard.save(self.path)

    def save(self) -> None:
        with self._lock, _interprocess_lock(self.path):
            self._reload_locked().save(self.path)

    @property
    def remaining_prompt_tokens(self) -> int:
        with self._lock, _interprocess_lock(self.path):
            return self._reload_locked().remaining_prompt_tokens

    @property
    def remaining_completion_tokens(self) -> int:
        with self._lock, _interprocess_lock(self.path):
            return self._reload_locked().remaining_completion_tokens


def make_budget_guard(path: Path = DEFAULT_BUDGET_PATH) -> PersistentHourlyBudgetGuard:
    return PersistentHourlyBudgetGuard(path)
