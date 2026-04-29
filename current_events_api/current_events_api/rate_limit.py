"""Small in-memory sliding-window rate limiters."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitExceeded(Exception):
    reason: str
    retry_after_s: int


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] | None = None,
        reason: str,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.reason = reason
        self._clock = clock or time.time
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = self._clock()
        cutoff = now - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            retry = max(1, int((hits[0] + self.window_seconds) - now) + 1)
            raise RateLimitExceeded(self.reason, retry)
        hits.append(now)

    def count(self, key: str) -> int:
        now = self._clock()
        cutoff = now - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return len(hits)


class RateLimitRegistry:
    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self.reads = SlidingWindowRateLimiter(
            limit=30,
            window_seconds=60,
            clock=clock,
            reason="read_rate_limit",
        )
        self.followups = SlidingWindowRateLimiter(
            limit=20,
            window_seconds=24 * 60 * 60,
            clock=clock,
            reason="fingerprint_daily_limit",
        )
        self.session_messages = SlidingWindowRateLimiter(
            limit=8,
            window_seconds=24 * 60 * 60,
            clock=clock,
            reason="session_message_limit",
        )

    def check_read(self, ip: str) -> None:
        self.reads.check(ip)

    def check_followup(self, fingerprint: str) -> None:
        self.followups.check(fingerprint)

    def check_session_message(self, session_id: str) -> None:
        self.session_messages.check(session_id)
