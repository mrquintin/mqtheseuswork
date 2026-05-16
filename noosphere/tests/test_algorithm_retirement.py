"""Tests for the algorithm retirement / promotion triggers (Round 19 prompt 05).

Pins:

* Retirement triggers fire at the documented thresholds (accuracy
  floor, Brier ceiling, directional floor, confidence drift cap,
  recent-window degradation).
* Retirement triggers DO NOT fire when sample size is insufficient
  — the round explicitly protects algorithms from premature
  retirement on small N.
* Promotion triggers fire at the documented thresholds.
* ``build_recommendation`` prefers RETIRE over PROMOTE when both
  trigger (a borderline algorithm should never be both).
* The agent NEVER auto-retires — the contract is "produce a triage
  row, never call ``set_algorithm_status(RETIRED)`` from the loop".
"""

from __future__ import annotations

import pytest

from noosphere.algorithms.calibration import CalibrationStats
from noosphere.algorithms.retirement import (
    DEFAULT_WEIGHTING_MULTIPLIER,
    MAX_WEIGHTING_MULTIPLIER,
    PROMOTION_ACCURACY_N,
    RETIREMENT_ACCURACY_N,
    RETIREMENT_BRIER_N,
    RETIREMENT_CONFIDENCE_DRIFT_N,
    RETIREMENT_DIRECTIONAL_N,
    RecommendedAction,
    TriggerReason,
    build_recommendation,
    check_promotion_triggers,
    check_retirement_triggers,
)


# ── Retirement floors fire ──────────────────────────────────────────


def test_accuracy_below_threshold_fires_with_enough_n() -> None:
    stats = CalibrationStats(
        total_invocations=RETIREMENT_ACCURACY_N + 5,
        resolved_invocations=RETIREMENT_ACCURACY_N + 5,
        accuracy=0.48,
    )
    reasons = check_retirement_triggers(stats)
    assert TriggerReason.ACCURACY_BELOW_THRESHOLD in reasons


def test_brier_above_threshold_fires_only_when_probabilistic_n_met() -> None:
    stats_low_n = CalibrationStats(
        total_invocations=30,
        resolved_invocations=30,
        mean_brier=0.40,
        probabilistic_resolved=RETIREMENT_BRIER_N - 1,
    )
    assert (
        TriggerReason.BRIER_ABOVE_THRESHOLD
        not in check_retirement_triggers(stats_low_n)
    )

    stats_ok = CalibrationStats(
        total_invocations=30,
        resolved_invocations=30,
        mean_brier=0.40,
        probabilistic_resolved=RETIREMENT_BRIER_N + 1,
    )
    assert TriggerReason.BRIER_ABOVE_THRESHOLD in check_retirement_triggers(
        stats_ok
    )


def test_directional_below_threshold_fires_when_directional_n_met() -> None:
    stats = CalibrationStats(
        total_invocations=30,
        resolved_invocations=30,
        directional_accuracy=0.40,
        directional_resolved=RETIREMENT_DIRECTIONAL_N + 1,
    )
    assert TriggerReason.DIRECTIONAL_BELOW_THRESHOLD in check_retirement_triggers(
        stats
    )


def test_confidence_drift_fires_for_overconfidence() -> None:
    stats = CalibrationStats(
        total_invocations=40,
        resolved_invocations=40,
        confidence_calibration_drift=0.35,  # +0.35 overconfident
        confidence_band_resolved=RETIREMENT_CONFIDENCE_DRIFT_N + 1,
    )
    assert TriggerReason.CONFIDENCE_DRIFT_EXCEEDED in check_retirement_triggers(
        stats
    )


def test_confidence_drift_fires_for_underconfidence() -> None:
    stats = CalibrationStats(
        total_invocations=40,
        resolved_invocations=40,
        confidence_calibration_drift=-0.35,  # -0.35 underconfident
        confidence_band_resolved=RETIREMENT_CONFIDENCE_DRIFT_N + 1,
    )
    assert TriggerReason.CONFIDENCE_DRIFT_EXCEEDED in check_retirement_triggers(
        stats
    )


def test_recent_accuracy_degradation_fires_after_lifetime_threshold() -> None:
    stats = CalibrationStats(
        total_invocations=80,
        resolved_invocations=80,
        accuracy=0.65,  # lifetime fine
        last_30d_accuracy=0.30,  # recent collapse
        last_30d_resolved=15,
    )
    assert TriggerReason.RECENT_ACCURACY_DEGRADED in check_retirement_triggers(
        stats
    )


# ── Sample-size protection ──────────────────────────────────────────


def test_no_retirement_on_small_n_accuracy() -> None:
    """An algorithm with poor accuracy but only 5 resolved invocations
    must NOT be recommended for retirement — small-N noise is not a
    death sentence."""
    stats = CalibrationStats(
        total_invocations=5,
        resolved_invocations=5,
        accuracy=0.0,
    )
    assert check_retirement_triggers(stats) == []


def test_no_retirement_on_small_n_brier() -> None:
    stats = CalibrationStats(
        total_invocations=10,
        resolved_invocations=10,
        mean_brier=0.50,
        probabilistic_resolved=5,
    )
    assert check_retirement_triggers(stats) == []


def test_no_retirement_on_small_n_directional() -> None:
    stats = CalibrationStats(
        total_invocations=10,
        resolved_invocations=10,
        directional_accuracy=0.10,
        directional_resolved=5,
    )
    assert check_retirement_triggers(stats) == []


def test_no_retirement_on_small_n_drift() -> None:
    stats = CalibrationStats(
        total_invocations=10,
        resolved_invocations=10,
        confidence_calibration_drift=0.50,
        confidence_band_resolved=5,
    )
    assert check_retirement_triggers(stats) == []


def test_recent_accuracy_does_not_fire_without_lifetime_floor() -> None:
    stats = CalibrationStats(
        total_invocations=20,  # below the lifetime gate of 50
        resolved_invocations=20,
        last_30d_accuracy=0.10,
        last_30d_resolved=10,
    )
    assert TriggerReason.RECENT_ACCURACY_DEGRADED not in check_retirement_triggers(
        stats
    )


# ── Promotion floors fire ───────────────────────────────────────────


def test_promotion_accuracy_fires_when_promotion_n_met() -> None:
    stats = CalibrationStats(
        total_invocations=PROMOTION_ACCURACY_N + 5,
        resolved_invocations=PROMOTION_ACCURACY_N + 5,
        accuracy=0.80,
    )
    assert TriggerReason.ACCURACY_PROMOTION in check_promotion_triggers(stats)


def test_promotion_brier_fires_when_promotion_n_met() -> None:
    stats = CalibrationStats(
        total_invocations=PROMOTION_ACCURACY_N + 5,
        resolved_invocations=PROMOTION_ACCURACY_N + 5,
        mean_brier=0.10,
        probabilistic_resolved=PROMOTION_ACCURACY_N + 5,
    )
    assert TriggerReason.BRIER_PROMOTION in check_promotion_triggers(stats)


def test_promotion_confidence_band_fires_when_drift_small() -> None:
    stats = CalibrationStats(
        total_invocations=40,
        resolved_invocations=40,
        confidence_calibration_drift=0.02,
        confidence_band_resolved=40,
    )
    assert TriggerReason.CONFIDENCE_BAND_PROMOTION in check_promotion_triggers(
        stats
    )


# ── Recommendation arbitration: RETIRE wins ────────────────────────


def test_retire_takes_precedence_over_promote() -> None:
    """An algorithm with great Brier and confidence calibration but
    poor accuracy should still be RETIRE — the agent never
    simultaneously promotes and retires."""
    stats = CalibrationStats(
        total_invocations=80,
        resolved_invocations=80,
        accuracy=0.48,  # below retirement floor
        mean_brier=0.10,  # below promotion ceiling
        probabilistic_resolved=80,
        confidence_calibration_drift=0.01,
        confidence_band_resolved=80,
    )
    rec = build_recommendation(algorithm_id="x", stats=stats)
    assert rec.recommended_action == RecommendedAction.RETIRE.value


def test_no_recommendation_when_nothing_fires() -> None:
    stats = CalibrationStats(
        total_invocations=5,
        resolved_invocations=5,
        accuracy=0.6,
    )
    rec = build_recommendation(algorithm_id="x", stats=stats)
    assert rec.recommended_action == RecommendedAction.NONE.value
    assert rec.reasons == []


# ── Narrative includes evidence, not just rule names ─────────────────


def test_retirement_narrative_includes_numbers() -> None:
    stats = CalibrationStats(
        total_invocations=30,
        resolved_invocations=30,
        accuracy=0.48,
    )
    rec = build_recommendation(algorithm_id="x", stats=stats)
    assert "0.48" in rec.narrative
    assert "30" in rec.narrative


def test_promotion_narrative_includes_new_multiplier() -> None:
    stats = CalibrationStats(
        total_invocations=40,
        resolved_invocations=40,
        accuracy=0.85,
        mean_brier=0.10,
        probabilistic_resolved=40,
        confidence_calibration_drift=0.02,
        confidence_band_resolved=40,
    )
    rec = build_recommendation(
        algorithm_id="x", stats=stats, current_multiplier=1.0
    )
    assert rec.recommended_action == RecommendedAction.PROMOTE.value
    assert f"{rec.recommended_multiplier:.2f}" in rec.narrative


# ── Multiplier bounds enforced by the recommender ───────────────────


def test_promotion_multiplier_never_exceeds_max() -> None:
    stats = CalibrationStats(
        total_invocations=100,
        resolved_invocations=100,
        accuracy=0.95,
        mean_brier=0.05,
        probabilistic_resolved=100,
        confidence_calibration_drift=0.0,
        confidence_band_resolved=100,
    )
    rec = build_recommendation(
        algorithm_id="x", stats=stats, current_multiplier=1.8
    )
    assert rec.recommended_multiplier <= MAX_WEIGHTING_MULTIPLIER


def test_no_multiplier_change_when_no_promotion_trigger() -> None:
    stats = CalibrationStats(
        total_invocations=10,
        resolved_invocations=10,
        accuracy=0.6,
    )
    rec = build_recommendation(
        algorithm_id="x", stats=stats, current_multiplier=1.2
    )
    assert rec.recommended_action == RecommendedAction.NONE.value
    assert rec.recommended_multiplier == pytest.approx(1.2)
