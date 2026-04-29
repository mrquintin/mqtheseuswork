from __future__ import annotations

import pytest

from current_events_api.rate_limit import RateLimitExceeded, RateLimitRegistry, SlidingWindowRateLimiter


def test_sliding_window_rejects_until_oldest_hit_expires() -> None:
    now = 1000.0

    def clock() -> float:
        return now

    limiter = SlidingWindowRateLimiter(
        limit=2,
        window_seconds=10,
        clock=clock,
        reason="test_limit",
    )

    limiter.check("ip")
    limiter.check("ip")
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check("ip")
    assert exc.value.reason == "test_limit"
    assert exc.value.retry_after_s >= 1

    now = 1011.0
    limiter.check("ip")
    assert limiter.count("ip") == 1


def test_registry_has_distinct_read_followup_and_session_limits() -> None:
    now = 1000.0
    limits = RateLimitRegistry(clock=lambda: now)

    for _ in range(30):
        limits.check_read("127.0.0.1")
    with pytest.raises(RateLimitExceeded) as read_exc:
        limits.check_read("127.0.0.1")
    assert read_exc.value.reason == "read_rate_limit"

    for _ in range(20):
        limits.check_followup("fingerprint")
    with pytest.raises(RateLimitExceeded) as followup_exc:
        limits.check_followup("fingerprint")
    assert followup_exc.value.reason == "fingerprint_daily_limit"

    for _ in range(8):
        limits.check_session_message("session")
    with pytest.raises(RateLimitExceeded) as session_exc:
        limits.check_session_message("session")
    assert session_exc.value.reason == "session_message_limit"
