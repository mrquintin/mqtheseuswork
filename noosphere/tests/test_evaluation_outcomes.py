"""Tests for outcome resolution: binary / interval / preference."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.models import Outcome, OutcomeKind
from noosphere.evaluation.outcomes import ResolutionError, resolve


def _make_outcome(kind: OutcomeKind, value, source: str = "external_judge") -> Outcome:
    return Outcome(
        outcome_id=f"test-{kind.value}",
        kind=kind,
        event_ref="evt-1",
        resolution_source=source,
        resolved_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        value=value,
    )


# ── Binary ──────────────────────────────────────────────────────────


def test_binary_true_with_high_prob():
    outcome = _make_outcome(OutcomeKind.BINARY, True)
    result = resolve(outcome, 0.9)
    assert result.resolved is True
    assert result.kind == OutcomeKind.BINARY
    assert abs(result.score - (0.9 - 1.0) ** 2) < 1e-9


def test_binary_false_with_low_prob():
    outcome = _make_outcome(OutcomeKind.BINARY, False)
    result = resolve(outcome, 0.1)
    assert result.resolved is True
    assert abs(result.score - (0.1 - 0.0) ** 2) < 1e-9


def test_binary_from_dict():
    outcome = _make_outcome(OutcomeKind.BINARY, True)
    result = resolve(outcome, {"probability": 0.8})
    assert abs(result.score - (0.8 - 1.0) ** 2) < 1e-9


def test_binary_bool_prediction():
    outcome = _make_outcome(OutcomeKind.BINARY, True)
    result = resolve(outcome, True)
    assert result.score == 0.0


def test_binary_perfect_wrong():
    outcome = _make_outcome(OutcomeKind.BINARY, True)
    result = resolve(outcome, 0.0)
    assert abs(result.score - 1.0) < 1e-9


# ── Interval ────────────────────────────────────────────────────────


def test_interval_exact():
    outcome = _make_outcome(OutcomeKind.INTERVAL, 42.0)
    result = resolve(outcome, 42.0)
    assert result.resolved is True
    assert result.score == 0.0


def test_interval_off_by_some():
    outcome = _make_outcome(OutcomeKind.INTERVAL, 100.0)
    result = resolve(outcome, 90.0)
    assert abs(result.score - 100.0) < 1e-9


def test_interval_with_bounds():
    outcome = _make_outcome(OutcomeKind.INTERVAL, 50.0)
    result = resolve(outcome, {"point": 45.0, "lower": 40.0, "upper": 55.0})
    assert result.resolved is True
    assert "interval_hit=True" in result.detail


def test_interval_outside_bounds():
    outcome = _make_outcome(OutcomeKind.INTERVAL, 100.0)
    result = resolve(outcome, {"point": 45.0, "lower": 40.0, "upper": 55.0})
    assert "interval_hit=False" in result.detail


# ── Preference ──────────────────────────────────────────────────────


def test_preference_correct_string():
    outcome = _make_outcome(OutcomeKind.PREFERENCE, "option_a")
    result = resolve(outcome, "option_a")
    assert result.resolved is True
    assert result.score == 0.0


def test_preference_wrong_string():
    outcome = _make_outcome(OutcomeKind.PREFERENCE, "option_a")
    result = resolve(outcome, "option_b")
    assert result.score == 1.0


def test_preference_with_probs():
    outcome = _make_outcome(OutcomeKind.PREFERENCE, "option_a")
    result = resolve(outcome, {
        "choice": "option_a",
        "probabilities": {"option_a": 0.8, "option_b": 0.2},
    })
    assert abs(result.score - (1.0 - 0.8) ** 2) < 1e-9


# ── Edge cases ──────────────────────────────────────────────────────


def test_no_resolution_source_raises():
    outcome = Outcome(
        outcome_id="no-src",
        kind=OutcomeKind.BINARY,
        event_ref="evt",
        resolution_source="",
        resolved_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        value=True,
    )
    with pytest.raises(ResolutionError, match="resolution_source"):
        resolve(outcome, 0.5)


def test_bad_prediction_type_raises():
    outcome = _make_outcome(OutcomeKind.BINARY, True)
    with pytest.raises(ResolutionError, match="Cannot interpret"):
        resolve(outcome, [1, 2, 3])
