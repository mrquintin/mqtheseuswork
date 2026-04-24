from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_rate_limit(*, api_key: str, route: str, limit_per_hour: int) -> tuple[bool, int]:
    """
    Sliding window per (api_key, route). Returns (allowed, retry_after_sec).
    """
    now = time.monotonic()
    window = 3600.0
    key = (api_key, route)
    with _lock:
        q = _events[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit_per_hour:
            oldest = q[0]
            retry_after = int(max(1.0, window - (now - oldest)))
            return False, retry_after
        q.append(now)
    return True, 0
