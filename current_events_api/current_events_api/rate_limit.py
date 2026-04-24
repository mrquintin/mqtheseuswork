"""Sliding-window per-key rate limiter (in-process).

Cheap, correct enough for a single-replica service. For multi-replica
deployments we'd swap this for Redis — keep the surface-area narrow so
that's a one-file change.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque


class SlidingWindowRateLimit:
    def __init__(self, limit: int, window_s: float) -> None:
        self._limit = limit
        self._window = window_s
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Attempt to record one hit for ``key``.

        Returns ``(allowed, retry_after_s)``. When ``allowed`` is False the
        caller should emit 429 and include ``retry_after_s`` (always >= 0)
        as the Retry-After header.
        """
        now = now if now is not None else time.time()
        q = self._hits[key]
        cutoff = now - self._window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self._limit:
            retry = q[0] + self._window - now
            return False, max(0.0, retry)
        q.append(now)
        return True, 0.0

    def reset(self, key: str | None = None) -> None:
        """Reset either one key or (with no arg) the whole limiter.

        Intended for use in tests only — wire rate-limit tests reset state
        via ``reset_all()`` below rather than touching this directly.
        """
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


# Module-level registry. ``reset_all`` clears every limiter and is used
# by the test fixtures so one test's hits don't bleed into the next.
LIST_RATE = SlidingWindowRateLimit(120, 60.0)       # 120 list reqs/min/IP
FOLLOWUP_RATE = SlidingWindowRateLimit(10, 60.0)    # 10 follow-up POSTs/min/IP

_REGISTRY: list[SlidingWindowRateLimit] = [LIST_RATE, FOLLOWUP_RATE]


def reset_all() -> None:
    for rl in _REGISTRY:
        rl.reset()
