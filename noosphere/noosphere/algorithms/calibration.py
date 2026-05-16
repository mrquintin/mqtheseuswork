"""Calibration metrics for the LogicalAlgorithm layer.

An algorithm earns its life. Every ACTIVE algorithm fires, eventually
resolves, and the resolution updates a track record. This module is
the pure-function half of that loop: given a list of
:class:`AlgorithmInvocation` rows, compute a
:class:`CalibrationStats` snapshot. The retirement/promotion trigger
logic in :mod:`noosphere.algorithms.retirement` consumes the result
and the scheduler persists snapshots to
:class:`AlgorithmCalibrationSnapshot`.

Metrics computed:

* ``total_invocations`` / ``resolved_invocations`` — counts.
* ``accuracy`` — fraction CORRECT among resolved, with
  PARTIALLY_CORRECT counting as 0.5. INDETERMINATE resolutions are
  excluded from the denominator (the world genuinely couldn't decide).
* ``mean_brier`` — average ``brier_equivalent`` across resolved
  invocations that carried one (probabilistic outputs).
* ``mean_horizon_error`` — for resolutions where the output included a
  predicted horizon and the actual outcome carried a realised delay,
  the absolute error in seconds.
* ``directional_accuracy`` — fraction of directional outputs whose
  declared direction matched the realised direction.
* ``confidence_calibration_drift`` — signed drift between the
  algorithm's stated coverage band and observed coverage. Positive
  means overconfident (stated bands too narrow); negative means
  underconfident.
* ``last_30d_accuracy`` — same as accuracy, restricted to invocations
  with ``invoked_at`` within the trailing 30 days.

This module deliberately does no I/O. The scheduler tick loads the
invocations, passes them in, and writes the resulting snapshot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field


# ── Module constants ────────────────────────────────────────────────


DEFAULT_ROLLING_WINDOW_DAYS = 30
# Slack on the confidence band coverage check. A 50/50 band that
# actually covers 50% of resolutions has drift 0; a 50/50 band that
# covers 30% has drift +0.20 (overconfident).
CONFIDENCE_CALIBRATION_SLACK = 0.0


# ── Schema ─────────────────────────────────────────────────────────


class CalibrationStats(BaseModel):
    """Snapshot of an algorithm's track record at one point in time.

    Every field is optional in the sense that a small-N algorithm
    may have ``None`` for metrics that need a non-empty subset of
    resolved invocations. Trigger checks downstream guard against
    insufficient sample sizes; this module just reports.
    """

    total_invocations: int = 0
    resolved_invocations: int = 0
    accuracy: Optional[float] = None
    mean_brier: Optional[float] = None
    mean_horizon_error: Optional[float] = None
    directional_accuracy: Optional[float] = None
    confidence_calibration_drift: Optional[float] = None
    last_30d_accuracy: Optional[float] = None
    last_30d_resolved: int = 0

    # Counts kept so the retirement triggers can apply per-metric
    # sample-size floors without re-walking the invocation list.
    probabilistic_resolved: int = 0
    directional_resolved: int = 0
    confidence_band_resolved: int = 0

    model_config = ConfigDict(extra="forbid")


# ── Helpers — extracting structured signals from an invocation ──────


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _correctness_value(invocation: Any) -> Optional[str]:
    c = getattr(invocation, "correctness", None)
    if c is None:
        return None
    return c.value if hasattr(c, "value") else str(c)


def _correctness_score(value: Optional[str]) -> Optional[float]:
    """CORRECT → 1.0, PARTIALLY_CORRECT → 0.5, INCORRECT → 0.0,
    INDETERMINATE / unresolved → None (excluded from accuracy)."""
    if value is None or value == "INDETERMINATE":
        return None
    if value == "CORRECT":
        return 1.0
    if value == "PARTIALLY_CORRECT":
        return 0.5
    if value == "INCORRECT":
        return 0.0
    return None


_DIRECTION_WORDS = {
    "up": +1,
    "down": -1,
    "bullish": +1,
    "bearish": -1,
    "escalating": +1,
    "escalate": +1,
    "de-escalating": -1,
    "deescalating": -1,
    "de_escalating": -1,
    "rise": +1,
    "fall": -1,
    "increase": +1,
    "decrease": -1,
    "long": +1,
    "short": -1,
}


def _direction_sign(value: Any) -> Optional[int]:
    """Coerce a value to a ±1 sign or None if direction is undefined.

    Accepts strings ("up"/"bullish"/…), numbers (sign of the number),
    or bools (True=+1, False=-1).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return +1 if value else -1
    if isinstance(value, (int, float)):
        if value > 0:
            return +1
        if value < 0:
            return -1
        return 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _DIRECTION_WORDS:
            return _DIRECTION_WORDS[v]
    return None


def _extract_directional_pair(invocation: Any) -> Optional[tuple[int, int]]:
    """Return (predicted_sign, actual_sign) when both are interpretable.

    Looks for any field in ``derived_output`` whose value parses as a
    direction, paired with the same-named field in ``actual_outcome``.
    """
    derived = getattr(invocation, "derived_output", None) or {}
    actual = getattr(invocation, "actual_outcome", None) or {}
    if not isinstance(derived, dict) or not isinstance(actual, dict):
        return None
    candidates = [
        "direction",
        "expected_direction",
        "predicted_direction",
        "trend",
        "outlook",
        "stance",
        "movement",
        "regime",
    ]
    for key in candidates:
        if key in derived and key in actual:
            p = _direction_sign(derived.get(key))
            a = _direction_sign(actual.get(key))
            if p is not None and a is not None:
                return p, a
    # Fallback: when the derived output names one numeric/scalar field
    # also present in the actual outcome, compare signs.
    for key, dval in derived.items():
        if key.startswith("_") or key not in actual:
            continue
        p = _direction_sign(dval)
        a = _direction_sign(actual.get(key))
        if p is not None and a is not None:
            return p, a
    return None


def _extract_horizon_error(invocation: Any) -> Optional[float]:
    """Absolute horizon error in seconds, when both predicted and actual exist.

    The actual delay is read from ``actual_outcome.realized_delay_s`` /
    ``actual_outcome.realized_horizon_s``, falling back to the gap
    between ``invoked_at`` and ``resolved_at`` when those are present.
    """
    predicted = getattr(invocation, "predicted_horizon", None)
    if predicted is None or float(predicted) <= 0:
        return None
    actual_outcome = getattr(invocation, "actual_outcome", None) or {}
    realised: Optional[float] = None
    if isinstance(actual_outcome, dict):
        for key in ("realized_delay_s", "realized_horizon_s", "realised_delay_s"):
            v = actual_outcome.get(key)
            if v is None:
                continue
            try:
                realised = float(v)
                break
            except (TypeError, ValueError):
                continue
    if realised is None:
        invoked_at = _as_utc(getattr(invocation, "invoked_at", None))
        resolved_at = _as_utc(getattr(invocation, "resolved_at", None))
        if invoked_at is not None and resolved_at is not None:
            realised = max(0.0, (resolved_at - invoked_at).total_seconds())
    if realised is None:
        return None
    return abs(float(predicted) - float(realised))


def _confidence_covered(invocation: Any) -> Optional[bool]:
    """Did the realised outcome fall inside the stated confidence band?

    Compares ``actual_outcome.realized_value`` (or a same-named scalar
    from ``derived_output``) against the band ``[confidence_low,
    confidence_high]``. Bands [0, 1] are treated as no information.
    """
    low = getattr(invocation, "confidence_low", None)
    high = getattr(invocation, "confidence_high", None)
    if low is None or high is None:
        return None
    if float(low) == 0.0 and float(high) == 1.0:
        return None
    actual_outcome = getattr(invocation, "actual_outcome", None) or {}
    if not isinstance(actual_outcome, dict):
        return None
    realised: Optional[float] = None
    for key in ("realized_value", "realised_value", "realized", "value"):
        v = actual_outcome.get(key)
        if v is None:
            continue
        try:
            realised = float(v)
            break
        except (TypeError, ValueError):
            continue
    if realised is None:
        derived = getattr(invocation, "derived_output", None) or {}
        if isinstance(derived, dict):
            for key in derived:
                if key.startswith("_") or key not in actual_outcome:
                    continue
                try:
                    realised = float(actual_outcome.get(key))
                    break
                except (TypeError, ValueError):
                    continue
    if realised is None:
        return None
    return float(low) <= realised <= float(high)


def _stated_band_width(invocation: Any) -> Optional[float]:
    """The algorithm's claimed coverage probability for this invocation.

    The stored band is ``[confidence_low, confidence_high]`` in the
    invocation's natural output space. ``confidence_high - confidence_low``
    is the width and — by the runtime contract documented in
    ``algorithms/runtime.py`` — represents the algorithm's *claimed
    probability* that the outcome will land inside the band.
    """
    low = getattr(invocation, "confidence_low", None)
    high = getattr(invocation, "confidence_high", None)
    if low is None or high is None:
        return None
    width = float(high) - float(low)
    if width <= 0.0 or width > 1.0:
        return None
    return width


# ── Core compute ───────────────────────────────────────────────────


def compute_stats(
    invocations: Iterable[Any],
    *,
    window_days: Optional[int] = DEFAULT_ROLLING_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> CalibrationStats:
    """Aggregate calibration metrics over a list of invocations.

    The contract: only resolved invocations contribute to metrics, and
    ``INDETERMINATE`` resolutions never appear in any denominator. The
    return value is a :class:`CalibrationStats` ready for persistence.
    """

    when = _as_utc(now) or datetime.now(timezone.utc)
    cutoff = (
        when - timedelta(days=int(window_days))
        if window_days is not None and window_days > 0
        else None
    )

    total = 0
    resolved = 0
    correct_score = 0.0
    correct_n = 0
    brier_sum = 0.0
    brier_n = 0
    horizon_err_sum = 0.0
    horizon_err_n = 0
    directional_hits = 0
    directional_n = 0
    band_covered = 0
    band_n = 0
    band_width_sum = 0.0
    last_30d_score = 0.0
    last_30d_n = 0

    for inv in invocations:
        total += 1
        correctness = _correctness_value(inv)
        if correctness is None:
            continue  # unresolved — only counts toward total_invocations
        resolved += 1
        score = _correctness_score(correctness)
        if score is not None:
            correct_score += score
            correct_n += 1
            invoked_at = _as_utc(getattr(inv, "invoked_at", None))
            if (
                cutoff is not None
                and invoked_at is not None
                and invoked_at >= cutoff
            ):
                last_30d_score += score
                last_30d_n += 1

        brier = getattr(inv, "brier_equivalent", None)
        if brier is not None:
            try:
                brier_sum += float(brier)
                brier_n += 1
            except (TypeError, ValueError):
                pass

        herr = _extract_horizon_error(inv)
        if herr is not None:
            horizon_err_sum += herr
            horizon_err_n += 1

        pair = _extract_directional_pair(inv)
        if pair is not None:
            p, a = pair
            directional_n += 1
            if p == a and p != 0:
                directional_hits += 1

        covered = _confidence_covered(inv)
        if covered is not None:
            width = _stated_band_width(inv)
            if width is not None:
                band_n += 1
                band_width_sum += width
                if covered:
                    band_covered += 1

    accuracy = correct_score / correct_n if correct_n else None
    mean_brier = brier_sum / brier_n if brier_n else None
    mean_horizon_error = horizon_err_sum / horizon_err_n if horizon_err_n else None
    directional_accuracy = (
        directional_hits / directional_n if directional_n else None
    )
    last_30d_accuracy = (
        last_30d_score / last_30d_n if last_30d_n else None
    )

    if band_n > 0:
        stated_coverage = band_width_sum / band_n
        actual_coverage = band_covered / band_n
        confidence_drift = stated_coverage - actual_coverage
    else:
        confidence_drift = None

    return CalibrationStats(
        total_invocations=total,
        resolved_invocations=resolved,
        accuracy=accuracy,
        mean_brier=mean_brier,
        mean_horizon_error=mean_horizon_error,
        directional_accuracy=directional_accuracy,
        confidence_calibration_drift=confidence_drift,
        last_30d_accuracy=last_30d_accuracy,
        last_30d_resolved=last_30d_n,
        probabilistic_resolved=brier_n,
        directional_resolved=directional_n,
        confidence_band_resolved=band_n,
    )


def compute_confidence_calibration_drift(
    invocations: Iterable[Any],
) -> Optional[float]:
    """Signed drift between stated and actual confidence-band coverage.

    Convenience wrapper over :func:`compute_stats` for callers that
    only need this one metric (e.g. unit tests pinning the sign).
    """

    return compute_stats(invocations).confidence_calibration_drift


__all__ = [
    "CalibrationStats",
    "CONFIDENCE_CALIBRATION_SLACK",
    "DEFAULT_ROLLING_WINDOW_DAYS",
    "compute_confidence_calibration_drift",
    "compute_stats",
]
