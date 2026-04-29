"""Hourly token budget guard for public Currents LLM calls."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

try:  # pragma: no cover - fallback is for non-POSIX platforms.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


PER_OPINION_BUDGET_RESERVE_PROMPT = 12_000
PER_OPINION_BUDGET_RESERVE_COMPLETION = 3_000


class BudgetExhausted(Exception):
    """Raised when the hourly token reserve would be breached."""


def _current_hour_iso() -> str:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return now.isoformat()


@dataclass
class HourlyBudgetGuard:
    max_prompt_tokens: int = 1_500_000
    max_completion_tokens: int = 400_000
    window_start_iso: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def _reset_if_hour_rolled(self) -> None:
        current_hour = _current_hour_iso()
        if self.window_start_iso != current_hour:
            self.window_start_iso = current_hour
            self.prompt_tokens = 0
            self.completion_tokens = 0

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        """Reserve capacity for another request or raise BudgetExhausted."""
        self._reset_if_hour_rolled()
        prompt_after = self.prompt_tokens + max(0, int(est_prompt))
        completion_after = self.completion_tokens + max(0, int(est_completion))
        prompt_remaining = self.max_prompt_tokens - prompt_after
        completion_remaining = self.max_completion_tokens - completion_after
        if (
            prompt_remaining < PER_OPINION_BUDGET_RESERVE_PROMPT
            or completion_remaining < PER_OPINION_BUDGET_RESERVE_COMPLETION
        ):
            raise BudgetExhausted("hourly Currents LLM token budget exhausted")

    def charge(self, prompt: int, completion: int) -> None:
        """Record actual usage in the current hourly window."""
        self._reset_if_hour_rolled()
        self.prompt_tokens += max(0, int(prompt))
        self.completion_tokens += max(0, int(completion))

    @property
    def remaining_prompt_tokens(self) -> int:
        self._reset_if_hour_rolled()
        return max(0, self.max_prompt_tokens - self.prompt_tokens)

    @property
    def remaining_completion_tokens(self) -> int:
        self._reset_if_hour_rolled()
        return max(0, self.max_completion_tokens - self.completion_tokens)

    @classmethod
    def load(cls, path: Path) -> "HourlyBudgetGuard":
        if not path.exists():
            return cls()
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field for field in cls.__dataclass_fields__}
        values = {key: raw[key] for key in allowed if key in raw}
        guard = cls(**values)
        guard._reset_if_hour_rolled()
        return guard

    def save(self, path: Path) -> None:
        self._reset_if_hour_rolled()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


@contextmanager
def _interprocess_lock(path: Path):
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class PersistentHourlyBudgetGuard:
    """Filesystem-backed HourlyBudgetGuard for separate scheduler/API processes."""

    def __init__(self, path: Path) -> None:
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
