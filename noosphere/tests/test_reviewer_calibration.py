"""ReviewerCalibration: discount factor tracks accuracy."""
from __future__ import annotations

import pytest

from noosphere.peer_review.calibration import ReviewerCalibration


def test_no_history_returns_full_weight():
    cal = ReviewerCalibration()
    assert cal.discount_factor("unknown") == 1.0


def test_all_confirmed_returns_full_weight():
    cal = ReviewerCalibration()
    for _ in range(10):
        cal.track_outcome("good-reviewer", "major", "confirmed")
    assert cal.discount_factor("good-reviewer") == 1.0


def test_none_confirmed_returns_floor():
    cal = ReviewerCalibration()
    for _ in range(10):
        cal.track_outcome("bad-reviewer", "minor", "rejected")
    assert cal.discount_factor("bad-reviewer") == 0.1


def test_partial_accuracy():
    cal = ReviewerCalibration()
    for _ in range(7):
        cal.track_outcome("mixed", "major", "confirmed")
    for _ in range(3):
        cal.track_outcome("mixed", "minor", "rejected")
    factor = cal.discount_factor("mixed")
    assert factor == pytest.approx(0.7, abs=0.01)


def test_discount_never_drops_below_floor():
    cal = ReviewerCalibration()
    cal.track_outcome("single-miss", "blocker", "rejected")
    assert cal.discount_factor("single-miss") >= 0.1


def test_findings_are_never_dropped():
    cal = ReviewerCalibration()
    for _ in range(20):
        cal.track_outcome("noisy", "info", "rejected")
    factor = cal.discount_factor("noisy")
    assert factor == 0.1
    assert len(cal._history["noisy"]) == 20
