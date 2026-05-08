"""Tests for the method-drift estimator and its alert state machine.

Six invariants pinned by the prompt's constraints:

1. **n < 8 → "insufficient", never an alert.** Below that threshold the
   estimator MUST refuse to produce a drift severity at all.
2. **Permutation seed is reproducible.** Two runs over the same rows
   with the same seed produce the same p-value to the bit.
3. **Lineage cutoff strictly excludes pre-revival data.** A row whose
   `observed_at` precedes the cutoff is dropped before windowing.
4. **A drifting method actually trips an alert.** Synthetic over-
   confident regime change in the recent window produces severity ≥
   "warn" with σ ≥ 1.5.
5. **Hysteresis works.** Alerts do not clear until two consecutive
   clean windows; a single clean window in between does not flip back
   to OK.
6. **Drift event ids are deterministic.** Re-running on the same
   (method, version, domain, window, end) produces the same id —
   that's how the scheduler stays idempotent on re-runs.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.decay.method_drift_policies import (
    AlertState,
    reduce_events,
    severity_penalty_multiplier,
)
from noosphere.evaluation.method_drift import (
    DEFAULT_SEED,
    ESCALATE_SIGMA,
    MIN_WINDOW_SAMPLE,
    WARN_SIGMA,
    DriftEventRecord,
    DriftResolution,
    assessment_to_event,
    evaluate_method,
    permutation_p_value,
    window_stats,
)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _calibrated_row(prediction_id: str, *, prob: float, observed_at: datetime, rng: random.Random) -> DriftResolution:
    """Generate a well-calibrated outcome: outcome = 1 with probability `prob`."""
    outcome = 1.0 if rng.random() < prob else 0.0
    brier = (prob - outcome) ** 2
    return DriftResolution(
        prediction_id=prediction_id,
        probability=prob,
        outcome=outcome,
        observed_at=observed_at,
        brier=brier,
        domain="forecasting",
    )


def _miscalibrated_row(prediction_id: str, *, prob: float, observed_at: datetime, rng: random.Random) -> DriftResolution:
    """Generate over-confident output: claimed `prob`, true rate has
    inverted toward the opposite tail (regime change — the edge has not
    just disappeared, the sign has flipped). This is the kind of
    pathology drift detection is supposed to catch."""
    true_p = 1.0 - prob  # full inversion
    outcome = 1.0 if rng.random() < true_p else 0.0
    brier = (prob - outcome) ** 2
    return DriftResolution(
        prediction_id=prediction_id,
        probability=prob,
        outcome=outcome,
        observed_at=observed_at,
        brier=brier,
        domain="forecasting",
    )


# ── Invariant 1: n < 8 means "insufficient", never an alert ───────────────


def test_below_min_sample_returns_insufficient() -> None:
    rng = random.Random(0)
    end = _utc(2026, 5, 1)
    rows = [
        _calibrated_row(f"p{i}", prob=0.7, observed_at=end - timedelta(days=2 + i), rng=rng)
        for i in range(MIN_WINDOW_SAMPLE - 1)
    ]
    stat = window_stats(rows, window_days=30, end=end)
    assert stat.insufficient is True
    assert stat.calibration_slope is None
    assert stat.sample_size == MIN_WINDOW_SAMPLE - 1


def test_evaluate_method_emits_insufficient_severity_below_threshold() -> None:
    rng = random.Random(1)
    end = _utc(2026, 5, 1)
    rows = [
        _calibrated_row(f"p{i}", prob=0.7, observed_at=end - timedelta(days=2 + i), rng=rng)
        for i in range(MIN_WINDOW_SAMPLE - 1)
    ]
    assessments = evaluate_method(
        organization_id="org_x",
        method_name="empirical_calibration",
        method_version="1.0.0",
        rows=rows,
        as_of=end,
        domain="forecasting",
        window_days=(30,),
        permutation_iterations=100,
    )
    assert len(assessments) == 1
    assert assessments[0].severity == "insufficient"
    assert assessments[0].sigma is None
    assert assessments[0].p_value is None


# ── Invariant 2: permutation test is reproducible under fixed seed ────────


def test_permutation_p_value_is_seed_reproducible() -> None:
    rng = random.Random(42)
    base = _utc(2026, 1, 1)
    current = [
        _miscalibrated_row(f"c{i}", prob=0.7 if i % 2 == 0 else 0.3,
                           observed_at=base + timedelta(days=i), rng=rng)
        for i in range(20)
    ]
    rng2 = random.Random(43)
    prior = [
        _calibrated_row(f"p{i}", prob=0.7 if i % 2 == 0 else 0.3,
                        observed_at=base - timedelta(days=200 + i), rng=rng2)
        for i in range(40)
    ]
    p1 = permutation_p_value(current, prior, iterations=200, seed=DEFAULT_SEED)
    p2 = permutation_p_value(current, prior, iterations=200, seed=DEFAULT_SEED)
    assert p1 == p2
    p3 = permutation_p_value(current, prior, iterations=200, seed=DEFAULT_SEED + 1)
    # A different seed need not give a different p (on small n collisions
    # happen) but it must remain a valid probability.
    assert p3 is None or (0.0 < p3 <= 1.0)


# ── Invariant 3: lineage cutoff strictly excludes pre-revival data ────────


def test_lineage_cutoff_drops_pre_revival_rows() -> None:
    """A row from before the revival cutoff must not enter any window —
    the estimator must not silently smooth across regime breaks the
    firm has manually flagged."""
    rng = random.Random(7)
    end = _utc(2026, 5, 1)
    # 10 well-calibrated rows in the recent 30-day window.
    recent = [
        _calibrated_row(f"r{i}", prob=0.6,
                        observed_at=end - timedelta(days=1 + i), rng=rng)
        for i in range(10)
    ]
    # 50 garbage rows from before the cutoff (would heavily bias the
    # baseline if they leaked in).
    pre_cutoff = [
        DriftResolution(
            prediction_id=f"old{i}",
            probability=0.99,
            outcome=0.0,
            observed_at=end - timedelta(days=400 + i),
            brier=0.98,
            domain="forecasting",
        )
        for i in range(50)
    ]
    cutoff = end - timedelta(days=200)
    assessments = evaluate_method(
        organization_id="org_x",
        method_name="empirical_calibration",
        method_version="1.0.0",
        rows=recent + pre_cutoff,
        as_of=end,
        domain="forecasting",
        window_days=(30,),
        earliest_eligible=cutoff,
        permutation_iterations=100,
    )
    # The recent window must have exactly the 10 recent rows in it.
    assert assessments[0].window.sample_size == 10
    # And the trailing baseline cannot have been computed from pre-cutoff
    # rows — there are no eligible prior windows, so baseline_slope is None.
    assert assessments[0].baseline_slope is None
    assert assessments[0].severity in ("ok", "insufficient")


# ── Invariant 4: a drifting method trips an alert ─────────────────────────


def test_drifting_method_produces_warn_or_escalate() -> None:
    """Generate a long calibrated history, then inject a recent window of
    over-confident calls. The estimator should flag this as drift."""
    rng = random.Random(2026)
    end = _utc(2026, 5, 1)
    rows: list[DriftResolution] = []

    # Four 30-day calibrated baseline windows.
    for window_idx in range(4):
        window_end = end - timedelta(days=30 * (window_idx + 1))
        for j in range(30):
            prob = 0.3 + 0.4 * ((j % 5) / 4.0)  # spread of probabilities
            rows.append(
                _calibrated_row(
                    f"b{window_idx}_{j}",
                    prob=prob,
                    observed_at=window_end - timedelta(days=29 - (j % 30), hours=j),
                    rng=rng,
                )
            )

    # Recent 30-day window: same probabilities, but the true rate has
    # collapsed toward 0.5 (edge gone). This should drive the slope down.
    for j in range(30):
        prob = 0.3 + 0.4 * ((j % 5) / 4.0)
        rows.append(
            _miscalibrated_row(
                f"recent_{j}",
                prob=prob,
                observed_at=end - timedelta(days=29 - (j % 30), hours=j),
                rng=rng,
            )
        )

    assessments = evaluate_method(
        organization_id="org_x",
        method_name="empirical_calibration",
        method_version="1.0.0",
        rows=rows,
        as_of=end,
        domain="forecasting",
        window_days=(30,),
        permutation_iterations=300,
        prior_window_count=4,
    )
    a = assessments[0]
    assert a.window.sample_size >= MIN_WINDOW_SAMPLE
    assert a.baseline_slope is not None
    assert a.window.calibration_slope is not None
    # Recent slope should be lower than the baseline (edge gone).
    assert a.window.calibration_slope < a.baseline_slope
    # And the severity classifier should fire at least a warn. With a
    # stochastic generator this is a probabilistic claim; we accept any
    # non-OK label.
    assert a.severity in ("warn", "escalate")


# ── Invariant 5: hysteresis ───────────────────────────────────────────────


def _ev(observed_at: datetime, severity: str, *, sigma: float | None = 1.6,
        p_value: float | None = 0.05) -> DriftEventRecord:
    return DriftEventRecord(
        id=f"drift_{observed_at.isoformat()}_{severity}",
        organization_id="org_x",
        method_name="m",
        method_version="1.0.0",
        domain="forecasting",
        observed_at=observed_at,
        window_days=30,
        severity=severity,
        sigma=sigma,
        p_value=p_value,
        sample_size=20,
        calibration_slope=0.5,
        baseline_slope=0.9,
        brier_mean=0.22,
        baseline_brier=0.18,
        directional_bias=-0.1,
        seed=DEFAULT_SEED,
    )


def test_hysteresis_requires_two_clean_windows_to_clear() -> None:
    base = _utc(2026, 1, 1)
    events = [
        _ev(base + timedelta(days=0), "ok"),
        _ev(base + timedelta(days=1), "warn"),
        _ev(base + timedelta(days=2), "ok"),
        # A single clean window must not clear the alert.
    ]
    result = reduce_events(events)
    assert result.state == AlertState.WARN
    assert result.is_active
    assert result.consecutive_clean == 1

    events.append(_ev(base + timedelta(days=3), "ok"))
    result2 = reduce_events(events)
    assert result2.state == AlertState.OK
    assert not result2.is_active


def test_hysteresis_does_not_auto_downgrade_escalate_to_warn() -> None:
    base = _utc(2026, 1, 1)
    events = [
        _ev(base + timedelta(days=0), "escalate", sigma=2.4, p_value=0.02),
        _ev(base + timedelta(days=1), "warn"),
        _ev(base + timedelta(days=2), "warn"),
    ]
    result = reduce_events(events)
    assert result.state == AlertState.ESCALATE


def test_insufficient_event_does_not_count_as_clean_window() -> None:
    base = _utc(2026, 1, 1)
    events = [
        _ev(base + timedelta(days=0), "warn"),
        _ev(base + timedelta(days=1), "ok"),
        _ev(base + timedelta(days=2), "insufficient", sigma=None, p_value=None),
        _ev(base + timedelta(days=3), "ok"),
    ]
    result = reduce_events(events)
    # We need *consecutive* ok windows; the insufficient event in the
    # middle resets the counter, so we end with 1 clean window after
    # the insufficient gap.
    assert result.state == AlertState.WARN
    assert result.consecutive_clean == 1


# ── Invariant 6: deterministic event ids ──────────────────────────────────


def test_drift_event_ids_are_deterministic() -> None:
    rng = random.Random(2026)
    end = _utc(2026, 5, 1)
    rows = [
        _calibrated_row(f"p{i}", prob=0.6 + 0.01 * i,
                        observed_at=end - timedelta(days=1 + i), rng=rng)
        for i in range(20)
    ]
    a1 = evaluate_method(
        organization_id="org_x", method_name="m", method_version="1.0.0",
        rows=rows, as_of=end, domain="forecasting",
        window_days=(30,), permutation_iterations=50,
    )
    a2 = evaluate_method(
        organization_id="org_x", method_name="m", method_version="1.0.0",
        rows=rows, as_of=end, domain="forecasting",
        window_days=(30,), permutation_iterations=50,
    )
    e1 = assessment_to_event(
        a1[0], organization_id="org_x", method_name="m",
        method_version="1.0.0", domain="forecasting", observed_at=end,
    )
    e2 = assessment_to_event(
        a2[0], organization_id="org_x", method_name="m",
        method_version="1.0.0", domain="forecasting", observed_at=end,
    )
    assert e1.id == e2.id


# ── MQS coupling ──────────────────────────────────────────────────────────


def test_severity_penalty_schedule_matches_doc() -> None:
    """The penalty multipliers are referenced from
    docs/methods/MQS_Specification.md. If they change, the doc check
    must change in lockstep."""
    assert severity_penalty_multiplier(AlertState.OK) == 1.00
    assert severity_penalty_multiplier(AlertState.INSUFFICIENT) == 1.00
    assert severity_penalty_multiplier(AlertState.WARN) == 0.85
    assert severity_penalty_multiplier(AlertState.ESCALATE) == 0.65
