"""Hourly token-budget guard for opinion generation.

Persistent across restarts via ``load(path)`` / implicit save on mutation so
the scheduler's hourly window isn't reset when the process restarts mid-hour.
Counters reset to zero when a fresh hour starts.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


class BudgetExhausted(RuntimeError):
    """Raised by ``HourlyBudgetGuard.authorize(...)`` when the spend would
    exceed the hourly ceiling."""


@dataclass
class BudgetState:
    window_start_iso: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class HourlyBudgetGuard:
    """Hourly token ceiling that persists to disk.

    - ``load(path)`` / implicit ``_save()`` round-trip counters so the budget
      isn't reset when the scheduler restarts mid-hour.
    - Counters reset to zero when a new hour starts.
    - ``may_spend(est_prompt, est_completion)`` → bool.
    - ``record(p, c)`` after the call.
    - ``authorize(p, c)`` → raises ``BudgetExhausted`` instead of returning.
    - ``remaining_prompt_tokens()`` / ``remaining_completion_tokens()`` for
      introspection.
    """

    def __init__(
        self,
        max_prompt_tokens: int = 1_500_000,
        max_completion_tokens: int = 400_000,
        *,
        path: Optional[Path] = None,
    ) -> None:
        self.max_prompt = max_prompt_tokens
        self.max_completion = max_completion_tokens
        self._path: Optional[Path] = Path(path) if path else None
        self._state = BudgetState(
            window_start_iso=datetime.now(timezone.utc).isoformat(),
        )

    # ── constructors ────────────────────────────────────────────────

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        max_prompt_tokens: int = 1_500_000,
        max_completion_tokens: int = 400_000,
    ) -> "HourlyBudgetGuard":
        g = cls(
            max_prompt_tokens=max_prompt_tokens,
            max_completion_tokens=max_completion_tokens,
            path=path,
        )
        if path.exists():
            try:
                data = json.loads(path.read_text())
                g._state = BudgetState(
                    window_start_iso=data["window_start_iso"],
                    prompt_tokens=int(data.get("prompt_tokens", 0)),
                    completion_tokens=int(data.get("completion_tokens", 0)),
                )
                # Override ceilings from file only if present.
                g.max_prompt = int(data.get("max_prompt_tokens", max_prompt_tokens))
                g.max_completion = int(
                    data.get("max_completion_tokens", max_completion_tokens)
                )
            except Exception:
                # Corrupt file → start fresh. The next _save() will overwrite.
                pass
        g._roll_window()
        return g

    # ── core API ────────────────────────────────────────────────────

    def _roll_window(self) -> None:
        window_start = datetime.fromisoformat(self._state.window_start_iso)
        now = datetime.now(timezone.utc)
        if now - window_start >= timedelta(hours=1):
            self._state = BudgetState(window_start_iso=now.isoformat())
            self._save()

    def may_spend(self, est_prompt: int, est_completion: int) -> bool:
        self._roll_window()
        return (
            self._state.prompt_tokens + est_prompt <= self.max_prompt
            and self._state.completion_tokens + est_completion <= self.max_completion
        )

    def record(self, prompt: int, completion: int) -> None:
        self._roll_window()
        self._state.prompt_tokens += int(prompt)
        self._state.completion_tokens += int(completion)
        self._save()

    def remaining_prompt_tokens(self) -> int:
        self._roll_window()
        return max(0, self.max_prompt - self._state.prompt_tokens)

    def remaining_completion_tokens(self) -> int:
        self._roll_window()
        return max(0, self.max_completion - self._state.completion_tokens)

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        """Raise ``BudgetExhausted`` if the spend cannot be authorized."""
        if not self.may_spend(est_prompt, est_completion):
            raise BudgetExhausted(
                f"hourly budget exhausted: want prompt={est_prompt} "
                f"completion={est_completion}; "
                f"remaining prompt={self.remaining_prompt_tokens()} "
                f"completion={self.remaining_completion_tokens()}"
            )

    def snapshot(self) -> BudgetState:
        return BudgetState(
            window_start_iso=self._state.window_start_iso,
            prompt_tokens=self._state.prompt_tokens,
            completion_tokens=self._state.completion_tokens,
        )

    # ── persistence ─────────────────────────────────────────────────

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "window_start_iso": self._state.window_start_iso,
            "prompt_tokens": self._state.prompt_tokens,
            "completion_tokens": self._state.completion_tokens,
            "max_prompt_tokens": self.max_prompt,
            "max_completion_tokens": self.max_completion,
        }
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".budget_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self._path)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
