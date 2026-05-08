"""Method drift estimator.

A method's track record is a *running* phenomenon. Aggregating all of its
resolved forecasts into a single calibration slope (which is what
`method_track_record.py` produces) is the right thing to publish on the
"how does this method do, in total?" panel. It is the wrong thing to
watch for the question "is the method getting worse *right now*?" — by
the time enough bad calls accumulate to drag the lifetime slope below
some threshold, a quarter of the firm's output has already shipped on a
broken instrument.

This module computes per-method, per-window calibration statistics over
rolling time windows (defaults: 30 / 90 / 180 days), compares each
window's calibration slope and Brier mean to the method's *trailing
baseline* (median of prior windows), and produces a drift p-value via
permutation test. Parametric z-tests would be wrong here: at n=8..40
resolutions per window the binary outcome distribution does not satisfy
OLS variance assumptions tightly enough to trust the analytic SE.

Three constraints the tests pin:

* **No drift alert is allowed for n < 8 resolutions in the window.** The
  estimator returns `WindowStat(insufficient=True, ...)` instead.
* **Permutation tests use a fixed seed.** The seed is recorded on the
  emitted DriftEvent so a reviewer can re-run the test bit-for-bit.
* **Lineage breaks are honored.** Callers may pass an `earliest_eligible`
  cutoff per method (Conclusion Lineage retire/revive event) and the
  estimator drops resolutions whose source predictions were observed
  before that cutoff. There is no implicit smoothing across regime
  breaks the firm has manually flagged.

This module deliberately does no I/O. The scheduler in
`scheduler_drift.py` pulls rows, calls `evaluate_method`, and persists
DriftEvents. Tests exercise this module directly with synthetic rows.
"""

from __future__ import annotations

import math
import random
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence


METHOD_DRIFT_SCHEMA = "theseus.method_drift.v1"
DEFAULT_WINDOW_DAYS: tuple[int, ...] = (30, 90, 180)
DEFAULT_PERMUTATION_ITERATIONS = 500
DEFAULT_BOOTSTRAP_ITERATIONS = 400
MIN_WINDOW_SAMPLE = 8
DEFAULT_SEED = 0xD71F70FF
WARN_SIGMA = 1.5
ESCALATE_SIGMA = 2.0
HYSTERESIS_CLEAN_WINDOWS = 2


# ── Inputs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftResolution:
    """One resolution feeding the drift estimator.

    `observed_at` is the time the prediction was *made* (or otherwise
    became active in the world), NOT the time the market settled — drift
    is about when the method made the call, not when the call paid out.
    """

    prediction_id: str
    probability: float
    outcome: float  # 0.0 or 1.0
    observed_at: datetime
    brier: Optional[float] = None
    domain: str = ""


# ── Outputs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WindowStat:
    """Calibration metrics for a single (method, window) pair."""

    window_days: int
    window_start: datetime
    window_end: datetime
    sample_size: int
    calibration_slope: Optional[float]
    brier_mean: Optional[float]
    directional_bias: Optional[float]  # mean(outcome - probability); >0 under-confident
    insufficient: bool = False


@dataclass(frozen=True)
class DriftAssessment:
    """One window's assessment relative to the method's trailing baseline."""

    window: WindowStat
    baseline_slope: Optional[float]
    baseline_brier: Optional[float]
    slope_delta: Optional[float]
    brier_delta: Optional[float]
    p_value: Optional[float]
    sigma: Optional[float]
    severity: str  # "ok" | "warn" | "escalate" | "insufficient"
    seed: int


@dataclass
class DriftEventRecord:
    """Materialized drift event ready to be persisted (DB-agnostic)."""

    id: str
    organization_id: str
    method_name: str
    method_version: str
    domain: str
    observed_at: datetime
    window_days: int
    severity: str
    sigma: Optional[float]
    p_value: Optional[float]
    sample_size: int
    calibration_slope: Optional[float]
    baseline_slope: Optional[float]
    brier_mean: Optional[float]
    baseline_brier: Optional[float]
    directional_bias: Optional[float]
    seed: int
    notes: str = ""

    def evidence(self) -> dict[str, object]:
        return {
            "schema": METHOD_DRIFT_SCHEMA,
            "method_name": self.method_name,
            "method_version": self.method_version,
            "domain": self.domain,
            "window_days": self.window_days,
            "severity": self.severity,
            "sigma": self.sigma,
            "p_value": self.p_value,
            "sample_size": self.sample_size,
            "calibration_slope": self.calibration_slope,
            "baseline_slope": self.baseline_slope,
            "brier_mean": self.brier_mean,
            "baseline_brier": self.baseline_brier,
            "directional_bias": self.directional_bias,
            "seed": self.seed,
        }


# ── Statistics ─────────────────────────────────────────────────────────────


def _ols_slope(rows: Sequence[DriftResolution]) -> Optional[float]:
    if len(rows) < 2:
        return None
    n = len(rows)
    mean_x = sum(r.probability for r in rows) / n
    mean_y = sum(r.outcome for r in rows) / n
    num = 0.0
    den = 0.0
    for r in rows:
        dx = r.probability - mean_x
        num += dx * (r.outcome - mean_y)
        den += dx * dx
    if den <= 0.0:
        return None
    return num / den


def _brier_mean(rows: Sequence[DriftResolution]) -> Optional[float]:
    vals = [r.brier if r.brier is not None else (r.probability - r.outcome) ** 2 for r in rows]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _directional_bias(rows: Sequence[DriftResolution]) -> Optional[float]:
    if not rows:
        return None
    return sum(r.outcome - r.probability for r in rows) / len(rows)


def window_stats(
    rows: Sequence[DriftResolution],
    *,
    window_days: int,
    end: datetime,
) -> WindowStat:
    """Compute statistics for one rolling window ending at `end`.

    Rows are filtered to those whose `observed_at` falls in
    [end - window_days, end). The window is inclusive on the start side
    (so a row at exactly the lower boundary is in) and exclusive on the
    end side (so two adjacent windows do not double-count the same row).
    """
    start = end - timedelta(days=window_days)
    in_window = [
        r for r in rows
        if _ensure_tz(r.observed_at) >= _ensure_tz(start)
        and _ensure_tz(r.observed_at) < _ensure_tz(end)
    ]
    n = len(in_window)
    if n < MIN_WINDOW_SAMPLE:
        return WindowStat(
            window_days=window_days,
            window_start=start,
            window_end=end,
            sample_size=n,
            calibration_slope=None,
            brier_mean=None,
            directional_bias=None,
            insufficient=True,
        )
    return WindowStat(
        window_days=window_days,
        window_start=start,
        window_end=end,
        sample_size=n,
        calibration_slope=_ols_slope(in_window),
        brier_mean=_brier_mean(in_window),
        directional_bias=_directional_bias(in_window),
        insufficient=False,
    )


def _trailing_baseline(prior: Sequence[WindowStat]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Median + MAD of prior windows' slope and Brier mean.

    Returns (median_slope, median_brier, mad_slope).
    Drops insufficient windows. Returns Nones when there are fewer than
    two usable prior windows — drift cannot be assessed against a
    trailing baseline of one point.
    """
    usable = [w for w in prior if not w.insufficient and w.calibration_slope is not None]
    if len(usable) < 2:
        return (None, None, None)
    slopes = [w.calibration_slope for w in usable if w.calibration_slope is not None]
    briers = [w.brier_mean for w in usable if w.brier_mean is not None]
    median_slope = statistics.median(slopes) if slopes else None
    median_brier = statistics.median(briers) if briers else None
    if median_slope is None:
        return (None, median_brier, None)
    abs_dev = [abs(s - median_slope) for s in slopes]
    mad = statistics.median(abs_dev) if abs_dev else 0.0
    # Convert MAD to a comparable σ (Gaussian consistency factor 1.4826).
    sigma_like = mad * 1.4826 if mad > 0 else 0.0
    return (median_slope, median_brier, sigma_like)


def permutation_p_value(
    current: Sequence[DriftResolution],
    prior: Sequence[DriftResolution],
    *,
    iterations: int = DEFAULT_PERMUTATION_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> Optional[float]:
    """Two-sided permutation test on the difference of OLS slopes between
    the current window and the union of prior windows.

    Returns None if either bucket has fewer than `MIN_WINDOW_SAMPLE`
    rows or if the slope is undefined on the observed split (zero
    variance in probabilities).
    """
    if len(current) < MIN_WINDOW_SAMPLE or len(prior) < MIN_WINDOW_SAMPLE:
        return None
    s_current = _ols_slope(current)
    s_prior = _ols_slope(prior)
    if s_current is None or s_prior is None:
        return None
    observed = abs(s_current - s_prior)
    pooled = list(current) + list(prior)
    n_current = len(current)
    rng = random.Random(seed)
    extreme = 0
    valid = 0
    for _ in range(max(1, iterations)):
        rng.shuffle(pooled)
        a = pooled[:n_current]
        b = pooled[n_current:]
        sa = _ols_slope(a)
        sb = _ols_slope(b)
        if sa is None or sb is None:
            continue
        valid += 1
        if abs(sa - sb) >= observed - 1e-12:
            extreme += 1
    if valid < iterations // 2:
        # Too many degenerate resamples — treat as undefined.
        return None
    # +1 smoothing so an exact match cannot return p=0.
    return (extreme + 1) / (valid + 1)


# ── Top-level evaluation ───────────────────────────────────────────────────


def evaluate_method(
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
    rows: Sequence[DriftResolution],
    as_of: datetime,
    domain: str = "",
    window_days: Sequence[int] = DEFAULT_WINDOW_DAYS,
    earliest_eligible: Optional[datetime] = None,
    seed: int = DEFAULT_SEED,
    permutation_iterations: int = DEFAULT_PERMUTATION_ITERATIONS,
    prior_window_count: int = 4,
) -> list[DriftAssessment]:
    """Assess drift for one (method, version, domain) at `as_of`.

    For each `window_days` in the input, compute the current window's
    statistics, build a trailing baseline of `prior_window_count`
    non-overlapping prior windows of the same length, and emit a
    `DriftAssessment`.

    Lineage handling: rows whose `observed_at` precedes
    `earliest_eligible` are dropped before any windowing. This is the
    sole hook for excluding pre-revival data from a retire-and-revive
    method; it must be passed in by the scheduler from a
    ConclusionLineage row when present.
    """
    rows = [
        r for r in rows
        if r.domain == domain
        and (earliest_eligible is None or _ensure_tz(r.observed_at) >= _ensure_tz(earliest_eligible))
    ]
    out: list[DriftAssessment] = []
    for w in window_days:
        current = window_stats(rows, window_days=w, end=as_of)
        # Build prior windows: each of `w` days, immediately preceding,
        # non-overlapping. Used both for the trailing baseline and the
        # permutation pool.
        prior_stats: list[WindowStat] = []
        prior_rows: list[DriftResolution] = []
        for k in range(1, prior_window_count + 1):
            prior_end = current.window_start - timedelta(days=w * (k - 1))
            ws = window_stats(rows, window_days=w, end=prior_end)
            prior_stats.append(ws)
            if not ws.insufficient:
                prior_rows.extend(
                    r for r in rows
                    if _ensure_tz(r.observed_at) >= _ensure_tz(ws.window_start)
                    and _ensure_tz(r.observed_at) < _ensure_tz(ws.window_end)
                )

        baseline_slope, baseline_brier, sigma_like = _trailing_baseline(prior_stats)

        if current.insufficient:
            out.append(
                DriftAssessment(
                    window=current,
                    baseline_slope=baseline_slope,
                    baseline_brier=baseline_brier,
                    slope_delta=None,
                    brier_delta=None,
                    p_value=None,
                    sigma=None,
                    severity="insufficient",
                    seed=seed,
                )
            )
            continue

        slope_delta = (
            current.calibration_slope - baseline_slope
            if (current.calibration_slope is not None and baseline_slope is not None)
            else None
        )
        brier_delta = (
            current.brier_mean - baseline_brier
            if (current.brier_mean is not None and baseline_brier is not None)
            else None
        )

        # σ score: how far from the baseline in MAD-derived units.
        # We score the *direction that is bad*: slope going DOWN, Brier
        # going UP. A baseline with zero MAD (all priors identical) is
        # treated as no σ available — we cannot scale a deviation
        # against zero spread, and forcing infinity would swamp the
        # alert policy.
        sigma: Optional[float] = None
        if slope_delta is not None and sigma_like and sigma_like > 0:
            # Negative slope_delta = degradation; flip sign so positive σ
            # means "drifting worse".
            sigma = max(0.0, -slope_delta / sigma_like)

        # Current rows for the permutation test.
        current_rows = [
            r for r in rows
            if _ensure_tz(r.observed_at) >= _ensure_tz(current.window_start)
            and _ensure_tz(r.observed_at) < _ensure_tz(current.window_end)
        ]
        p_value = permutation_p_value(
            current_rows,
            prior_rows,
            iterations=permutation_iterations,
            seed=seed,
        )

        severity = _classify(sigma, p_value)
        out.append(
            DriftAssessment(
                window=current,
                baseline_slope=baseline_slope,
                baseline_brier=baseline_brier,
                slope_delta=slope_delta,
                brier_delta=brier_delta,
                p_value=p_value,
                sigma=sigma,
                severity=severity,
                seed=seed,
            )
        )
    return out


def _classify(sigma: Optional[float], p_value: Optional[float]) -> str:
    """Map (σ, p) → severity label.

    Rules:
    * σ ≥ ESCALATE_SIGMA AND p ≤ 0.05 → "escalate"
    * σ ≥ WARN_SIGMA  AND p ≤ 0.10 → "warn"
    * otherwise → "ok"
    σ alone or p alone is not enough; both have to fire so a thin
    baseline (small MAD) cannot escalate by itself.
    """
    if sigma is None or p_value is None:
        return "ok"
    if sigma >= ESCALATE_SIGMA and p_value <= 0.05:
        return "escalate"
    if sigma >= WARN_SIGMA and p_value <= 0.10:
        return "warn"
    return "ok"


def assessment_to_event(
    assessment: DriftAssessment,
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
    domain: str,
    observed_at: Optional[datetime] = None,
) -> DriftEventRecord:
    """Materialize an assessment as a DriftEventRecord ready to persist.

    The id is deterministic on (organization, method, version, domain,
    window, window_end) so re-running the scheduler over the same
    window does not create a duplicate row — the scheduler upserts on
    this id."""
    obs = observed_at or assessment.window.window_end
    deterministic_seed = "|".join(
        [
            organization_id,
            method_name,
            method_version,
            domain,
            str(assessment.window.window_days),
            assessment.window.window_end.isoformat(),
        ]
    )
    event_id = "drift_" + uuid.uuid5(uuid.NAMESPACE_URL, deterministic_seed).hex[:24]
    return DriftEventRecord(
        id=event_id,
        organization_id=organization_id,
        method_name=method_name,
        method_version=method_version,
        domain=domain,
        observed_at=obs,
        window_days=assessment.window.window_days,
        severity=assessment.severity,
        sigma=assessment.sigma,
        p_value=assessment.p_value,
        sample_size=assessment.window.sample_size,
        calibration_slope=assessment.window.calibration_slope,
        baseline_slope=assessment.baseline_slope,
        brier_mean=assessment.window.brier_mean,
        baseline_brier=assessment.baseline_brier,
        directional_bias=assessment.window.directional_bias,
        seed=assessment.seed,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = [
    "DEFAULT_BOOTSTRAP_ITERATIONS",
    "DEFAULT_PERMUTATION_ITERATIONS",
    "DEFAULT_SEED",
    "DEFAULT_WINDOW_DAYS",
    "ESCALATE_SIGMA",
    "HYSTERESIS_CLEAN_WINDOWS",
    "METHOD_DRIFT_SCHEMA",
    "MIN_WINDOW_SAMPLE",
    "WARN_SIGMA",
    "DriftAssessment",
    "DriftEventRecord",
    "DriftResolution",
    "WindowStat",
    "assessment_to_event",
    "evaluate_method",
    "permutation_p_value",
    "window_stats",
]
