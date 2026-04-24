"""Unit tests for ``SlidingWindowRateLimit``."""
from __future__ import annotations

from current_events_api.rate_limit import SlidingWindowRateLimit


def test_allows_up_to_limit_then_denies():
    rl = SlidingWindowRateLimit(limit=5, window_s=60.0)
    t0 = 1000.0
    for i in range(5):
        ok, retry = rl.check("ip-a", now=t0 + i * 0.01)
        assert ok, i
        assert retry == 0.0
    ok, retry = rl.check("ip-a", now=t0 + 0.1)
    assert not ok
    assert retry > 0.0


def test_window_expiry_re_enables():
    rl = SlidingWindowRateLimit(limit=3, window_s=10.0)
    for i in range(3):
        assert rl.check("k", now=100.0 + i)[0]
    # Next one in the same window → deny.
    assert rl.check("k", now=103.0)[0] is False
    # Fast-forward past the window → first three have aged out.
    ok, _ = rl.check("k", now=200.0)
    assert ok


def test_keys_are_independent():
    rl = SlidingWindowRateLimit(limit=2, window_s=60.0)
    for _ in range(2):
        assert rl.check("a", now=100.0)[0]
    assert rl.check("a", now=100.0)[0] is False
    # Key "b" has its own budget.
    assert rl.check("b", now=100.0)[0]
    assert rl.check("b", now=100.0)[0]
    assert rl.check("b", now=100.0)[0] is False


def test_reset_clears_state():
    rl = SlidingWindowRateLimit(limit=1, window_s=60.0)
    assert rl.check("k")[0]
    assert rl.check("k")[0] is False
    rl.reset()
    assert rl.check("k")[0]
