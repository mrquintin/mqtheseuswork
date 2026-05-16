"""Tests for the algorithm calibration loop (Round 19 prompt 05).

Covers:

* ``compute_stats`` handles probabilistic / directional / structured
  outputs correctly across a fixture invocation list.
* ``compute_confidence_calibration_drift`` returns positive drift for
  systematically overconfident algorithms and negative drift for
  systematically underconfident ones.
* The snapshot-store append-only invariant: re-running calibration
  does not overwrite an existing row; each tick produces a new one.
* The end-to-end promotion path through the store helper bumps the
  algorithm's ``weighting_multiplier`` within bounds.
* The triage round-trip — ACCEPT-PROMOTE and REJECT-with-note —
  exercises the store-side enforcement of the 20-char REJECT note.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.algorithms.calibration import (
    CalibrationStats,
    compute_confidence_calibration_drift,
    compute_stats,
)
from noosphere.algorithms.retirement import (
    DEFAULT_WEIGHTING_MULTIPLIER,
    MAX_WEIGHTING_MULTIPLIER,
    RecommendedAction,
    build_recommendation,
    recommended_multiplier_for_promotion,
)
from noosphere.algorithms.schemas import AlgorithmCorrectness
from noosphere.models import (
    AlgorithmCalibrationSnapshot,
    AlgorithmInvocation,
    AlgorithmTriageRecommendation,
    TriageRecommendationStatus,
)


_ORG_ID = "org_algorithm"
_ALGO_ID = "algorithm_calibration_fixture"


def _now() -> datetime:
    return datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


def _make_invocation(
    *,
    correctness: AlgorithmCorrectness | None,
    brier: float | None = None,
    confidence_low: float = 0.0,
    confidence_high: float = 1.0,
    predicted_horizon: float = 0.0,
    invoked_at: datetime | None = None,
    derived_output: dict | None = None,
    actual_outcome: dict | None = None,
    resolved_at: datetime | None = None,
) -> AlgorithmInvocation:
    inv = AlgorithmInvocation(
        id=str(uuid.uuid4()),
        algorithm_id=_ALGO_ID,
        organization_id=_ORG_ID,
        invoked_at=invoked_at or _now(),
        trigger_inputs={"x": 1.0},
        derived_output=derived_output or {"score": 0.5},
        reasoning_trace=["OUTPUT"],
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        predicted_horizon=predicted_horizon,
        resolved_at=resolved_at,
        actual_outcome=actual_outcome,
        correctness=correctness,
        brier_equivalent=brier,
    )
    return inv


# ── compute_stats happy paths ────────────────────────────────────────


def test_compute_stats_handles_empty_invocation_list() -> None:
    stats = compute_stats([])
    assert stats.total_invocations == 0
    assert stats.resolved_invocations == 0
    assert stats.accuracy is None
    assert stats.mean_brier is None


def test_compute_stats_excludes_unresolved_from_metrics() -> None:
    invocations = [
        _make_invocation(correctness=None),
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
        _make_invocation(correctness=AlgorithmCorrectness.INCORRECT),
    ]
    stats = compute_stats(invocations)
    assert stats.total_invocations == 3
    assert stats.resolved_invocations == 2
    # 1 correct out of 2 resolved => 0.5
    assert stats.accuracy == pytest.approx(0.5)


def test_compute_stats_excludes_indeterminate_from_accuracy() -> None:
    invocations = [
        _make_invocation(correctness=AlgorithmCorrectness.INDETERMINATE),
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
    ]
    stats = compute_stats(invocations)
    # INDETERMINATE excluded from accuracy denominator
    assert stats.accuracy == pytest.approx(1.0)
    # Resolved count still includes it
    assert stats.resolved_invocations == 3


def test_compute_stats_partially_correct_counts_as_half() -> None:
    invocations = [
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
        _make_invocation(
            correctness=AlgorithmCorrectness.PARTIALLY_CORRECT
        ),
        _make_invocation(correctness=AlgorithmCorrectness.INCORRECT),
        _make_invocation(correctness=AlgorithmCorrectness.INCORRECT),
    ]
    stats = compute_stats(invocations)
    # (1.0 + 0.5 + 0.0 + 0.0) / 4 = 0.375
    assert stats.accuracy == pytest.approx(0.375)


def test_compute_stats_mean_brier_over_probabilistic_only() -> None:
    invocations = [
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT, brier=0.10),
        _make_invocation(correctness=AlgorithmCorrectness.INCORRECT, brier=0.30),
        # No brier — excluded from probabilistic denominator
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
    ]
    stats = compute_stats(invocations)
    assert stats.probabilistic_resolved == 2
    assert stats.mean_brier == pytest.approx(0.20)


def test_compute_stats_directional_accuracy_from_structured_output() -> None:
    invocations = [
        _make_invocation(
            correctness=AlgorithmCorrectness.CORRECT,
            derived_output={"direction": "up"},
            actual_outcome={"direction": "up"},
        ),
        _make_invocation(
            correctness=AlgorithmCorrectness.INCORRECT,
            derived_output={"direction": "bullish"},
            actual_outcome={"direction": "bearish"},
        ),
        _make_invocation(
            correctness=AlgorithmCorrectness.CORRECT,
            derived_output={"direction": "escalating"},
            actual_outcome={"direction": "escalating"},
        ),
    ]
    stats = compute_stats(invocations)
    assert stats.directional_resolved == 3
    # 2 hits / 3 = ~0.667
    assert stats.directional_accuracy == pytest.approx(2 / 3)


def test_compute_stats_horizon_error_uses_realized_delay() -> None:
    invocations = [
        _make_invocation(
            correctness=AlgorithmCorrectness.CORRECT,
            predicted_horizon=86400.0,
            actual_outcome={"realized_delay_s": 90000.0},
        ),
        _make_invocation(
            correctness=AlgorithmCorrectness.CORRECT,
            predicted_horizon=3600.0,
            actual_outcome={"realized_delay_s": 1800.0},
        ),
    ]
    stats = compute_stats(invocations)
    # |86400 - 90000| = 3600; |3600 - 1800| = 1800; mean = 2700
    assert stats.mean_horizon_error == pytest.approx(2700.0)


def test_compute_stats_last_30d_window_filters_old_invocations() -> None:
    now = _now()
    old = now - timedelta(days=60)
    recent = now - timedelta(days=5)
    invocations = [
        _make_invocation(
            invoked_at=old,
            correctness=AlgorithmCorrectness.INCORRECT,
        ),
        _make_invocation(
            invoked_at=recent,
            correctness=AlgorithmCorrectness.CORRECT,
        ),
        _make_invocation(
            invoked_at=recent,
            correctness=AlgorithmCorrectness.CORRECT,
        ),
    ]
    stats = compute_stats(invocations, now=now)
    assert stats.accuracy == pytest.approx(2 / 3)
    # Only the two recent ones contribute to the 30d window
    assert stats.last_30d_resolved == 2
    assert stats.last_30d_accuracy == pytest.approx(1.0)


# ── Confidence-calibration drift sign tests ─────────────────────────


def test_confidence_drift_positive_for_overconfident_algorithm() -> None:
    """An algorithm that claims 50% bands and only covers 10% should
    show positive drift (overconfident).
    """
    invocations = []
    for i in range(20):
        covered = i < 2  # 2 / 20 = 10% actual coverage
        invocations.append(
            _make_invocation(
                correctness=AlgorithmCorrectness.CORRECT,
                confidence_low=0.4,
                confidence_high=0.9,  # stated 50% width
                derived_output={"value": 0.5},
                actual_outcome={"realized_value": 0.5 if covered else 0.05},
            )
        )
    drift = compute_confidence_calibration_drift(invocations)
    assert drift is not None
    assert drift > 0.20  # stated 0.5, actual 0.1 → drift ~ +0.4


def test_confidence_drift_negative_for_underconfident_algorithm() -> None:
    """An algorithm that claims 30% bands but actually covers 90%
    should show negative drift (underconfident).
    """
    invocations = []
    for i in range(20):
        covered = i < 18  # 18 / 20 = 90% actual coverage
        invocations.append(
            _make_invocation(
                correctness=AlgorithmCorrectness.CORRECT,
                confidence_low=0.4,
                confidence_high=0.7,  # stated 30% width
                derived_output={"value": 0.55},
                actual_outcome={"realized_value": 0.55 if covered else 0.05},
            )
        )
    drift = compute_confidence_calibration_drift(invocations)
    assert drift is not None
    assert drift < -0.20  # stated 0.3, actual 0.9 → drift ~ -0.6


def test_confidence_drift_none_when_no_band_observations() -> None:
    # Full [0,1] bands carry no information.
    invocations = [
        _make_invocation(
            correctness=AlgorithmCorrectness.CORRECT,
            confidence_low=0.0,
            confidence_high=1.0,
        )
    ]
    assert compute_confidence_calibration_drift(invocations) is None


# ── Promotion bump bounded ──────────────────────────────────────────


def test_promotion_multiplier_capped_at_max() -> None:
    stats = CalibrationStats(
        total_invocations=200,
        resolved_invocations=100,
        accuracy=0.85,
        mean_brier=0.10,
        confidence_calibration_drift=0.02,
        probabilistic_resolved=100,
        confidence_band_resolved=100,
    )
    bumped = recommended_multiplier_for_promotion(
        stats, current_multiplier=1.9
    )
    assert bumped <= MAX_WEIGHTING_MULTIPLIER


def test_promotion_no_op_when_no_trigger_fires() -> None:
    stats = CalibrationStats(
        total_invocations=10,
        resolved_invocations=5,
        accuracy=0.6,
        probabilistic_resolved=5,
        confidence_band_resolved=5,
    )
    assert (
        recommended_multiplier_for_promotion(
            stats, current_multiplier=1.0
        )
        == DEFAULT_WEIGHTING_MULTIPLIER
    )


# ── Snapshot append-only invariant + promotion end-to-end ───────────


def test_snapshot_persistence_is_append_only(algorithm_layer_seed) -> None:
    store = algorithm_layer_seed["store"]
    algo_id = algorithm_layer_seed["active_algorithm_id"]
    org_id = algorithm_layer_seed["organization_id"]

    s1 = AlgorithmCalibrationSnapshot(
        algorithm_id=algo_id,
        organization_id=org_id,
        snapshot_at=_now(),
        total_invocations=10,
        resolved_invocations=5,
        accuracy=0.6,
    )
    store.put_calibration_snapshot(s1)

    s2 = AlgorithmCalibrationSnapshot(
        algorithm_id=algo_id,
        organization_id=org_id,
        snapshot_at=_now() + timedelta(hours=1),
        total_invocations=12,
        resolved_invocations=6,
        accuracy=0.7,
    )
    store.put_calibration_snapshot(s2)

    rows = store.list_calibration_snapshots(algo_id)
    assert len(rows) == 2
    # newest first
    assert rows[0].accuracy == pytest.approx(0.7)
    assert rows[1].accuracy == pytest.approx(0.6)


def test_promotion_end_to_end_bumps_weighting(algorithm_layer_seed) -> None:
    store = algorithm_layer_seed["store"]
    algo_id = algorithm_layer_seed["active_algorithm_id"]

    # 30+ resolved with accuracy 0.8 and Brier 0.10 — three promotion
    # triggers should fire.
    stats = CalibrationStats(
        total_invocations=40,
        resolved_invocations=40,
        accuracy=0.85,
        mean_brier=0.10,
        confidence_calibration_drift=0.02,
        probabilistic_resolved=40,
        confidence_band_resolved=40,
    )
    rec = build_recommendation(
        algorithm_id=algo_id, stats=stats, current_multiplier=1.0
    )
    assert rec.recommended_action == RecommendedAction.PROMOTE.value
    assert rec.recommended_multiplier > 1.0
    assert rec.recommended_multiplier <= MAX_WEIGHTING_MULTIPLIER

    updated = store.set_algorithm_weighting_multiplier(
        algo_id, rec.recommended_multiplier
    )
    assert updated.weighting_multiplier == pytest.approx(
        rec.recommended_multiplier
    )

    # Re-read from the store to ensure persistence
    fetched = store.get_algorithm(algo_id)
    assert fetched.weighting_multiplier == pytest.approx(
        rec.recommended_multiplier
    )


def test_weighting_multiplier_bounded(algorithm_layer_seed) -> None:
    store = algorithm_layer_seed["store"]
    algo_id = algorithm_layer_seed["active_algorithm_id"]

    # Asking for 5.0 should clamp to MAX (2.0)
    updated = store.set_algorithm_weighting_multiplier(algo_id, 5.0)
    assert updated.weighting_multiplier == pytest.approx(
        MAX_WEIGHTING_MULTIPLIER
    )

    # Asking for -1.0 should clamp to 0.0
    updated = store.set_algorithm_weighting_multiplier(algo_id, -1.0)
    assert updated.weighting_multiplier == pytest.approx(0.0)


# ── Triage round-trip ───────────────────────────────────────────────


def test_triage_recommendation_round_trip_accept(algorithm_layer_seed) -> None:
    store = algorithm_layer_seed["store"]
    algo_id = algorithm_layer_seed["active_algorithm_id"]
    org_id = algorithm_layer_seed["organization_id"]

    rec = AlgorithmTriageRecommendation(
        algorithm_id=algo_id,
        organization_id=org_id,
        recommended_action="PROMOTE",
        trigger_reasons=["accuracy_promotion", "brier_promotion"],
        recommended_multiplier=1.5,
        narrative="PROMOTE recommended.",
    )
    store.put_triage_recommendation(rec)

    pending = store.list_triage_recommendations(
        organization_id=org_id,
        status=TriageRecommendationStatus.PENDING,
    )
    assert len(pending) == 1
    assert pending[0].recommended_multiplier == pytest.approx(1.5)
    assert pending[0].trigger_reasons == [
        "accuracy_promotion",
        "brier_promotion",
    ]

    resolved = store.resolve_triage_recommendation(
        rec.id,
        new_status=TriageRecommendationStatus.ACCEPTED,
        resolved_by="founder_x",
    )
    assert resolved.status == TriageRecommendationStatus.ACCEPTED.value
    assert resolved.resolved_by == "founder_x"


def test_triage_reject_requires_long_note(algorithm_layer_seed) -> None:
    store = algorithm_layer_seed["store"]
    algo_id = algorithm_layer_seed["active_algorithm_id"]
    org_id = algorithm_layer_seed["organization_id"]

    rec = AlgorithmTriageRecommendation(
        algorithm_id=algo_id,
        organization_id=org_id,
        recommended_action="RETIRE",
        trigger_reasons=["accuracy_below_threshold"],
        narrative="RETIRE recommended.",
    )
    store.put_triage_recommendation(rec)

    with pytest.raises(ValueError):
        store.resolve_triage_recommendation(
            rec.id,
            new_status=TriageRecommendationStatus.REJECTED,
            resolved_by="founder_x",
            resolution_note="too short",
        )

    # 20+ chars is accepted
    resolved = store.resolve_triage_recommendation(
        rec.id,
        new_status=TriageRecommendationStatus.REJECTED,
        resolved_by="founder_x",
        resolution_note=(
            "Domain change in the underlying market; will revisit "
            "after Q3 regime stabilises."
        ),
    )
    assert resolved.status == TriageRecommendationStatus.REJECTED.value


# ── Public chart math agrees with Python aggregator ─────────────────


def test_public_chart_math_agrees_with_aggregator() -> None:
    """The Python aggregator and the public JS renderer must agree.

    This pins the contract: the cumulative-accuracy series the
    ``calibrationSeries`` helper produces on the public detail page is
    the same numbers ``compute_stats`` reports under ``accuracy``.
    """
    invocations = [
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
        _make_invocation(correctness=AlgorithmCorrectness.INCORRECT),
        _make_invocation(
            correctness=AlgorithmCorrectness.PARTIALLY_CORRECT
        ),
        _make_invocation(correctness=AlgorithmCorrectness.INDETERMINATE),
        _make_invocation(correctness=AlgorithmCorrectness.CORRECT),
    ]
    stats = compute_stats(invocations)
    # 1 + 1 + 0 + 0.5 + 1 = 3.5 over 5 (INDETERMINATE excluded)
    assert stats.accuracy == pytest.approx(3.5 / 5)

    # The JS renderer's final point is the cumulative ratio over the
    # same denominator and treats PARTIALLY_CORRECT as 0.5. Walking
    # the same fixture by hand:
    js_scores = []
    score = 0.0
    n = 0
    for inv in invocations:
        c = inv.correctness
        c_value = c.value if hasattr(c, "value") else c
        if c_value is None or c_value == AlgorithmCorrectness.INDETERMINATE.value:
            continue
        n += 1
        if c_value == AlgorithmCorrectness.CORRECT.value:
            score += 1
        elif c_value == AlgorithmCorrectness.PARTIALLY_CORRECT.value:
            score += 0.5
        js_scores.append(score / n)
    assert js_scores[-1] == pytest.approx(stats.accuracy)
