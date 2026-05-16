"""Retirement / promotion triggers for the LogicalAlgorithm layer.

Given a :class:`CalibrationStats` snapshot, decide whether the
algorithm has earned retirement, promotion, or neither.

Hard rules pinned by tests:

* The agent NEVER retires an algorithm. The triggers here produce a
  :class:`RetirementRecommendation` row; the founder accepts or
  rejects via the operator triage UI.
* Sample-size floors guard against premature retirement on small N.
  Each trigger names the minimum resolved-count it needs.
* Promotion is bounded; the maximum weighting multiplier is 2.0.
* INDETERMINATE resolutions never enter any denominator; that
  contract is enforced in :mod:`noosphere.algorithms.calibration`.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from noosphere.algorithms.calibration import CalibrationStats


# ── Tunables ───────────────────────────────────────────────────────


# Retirement floors. Each is "fires when stat is *worse* than X over
# >= N resolutions of the relevant kind".
RETIREMENT_ACCURACY_MIN = 0.55
RETIREMENT_ACCURACY_N = 20
RETIREMENT_BRIER_MAX = 0.30
RETIREMENT_BRIER_N = 20
RETIREMENT_DIRECTIONAL_MIN = 0.55
RETIREMENT_DIRECTIONAL_N = 20
RETIREMENT_CONFIDENCE_DRIFT_MAX = 0.20
RETIREMENT_CONFIDENCE_DRIFT_N = 30
RETIREMENT_RECENT_ACCURACY_MIN = 0.40
RETIREMENT_RECENT_TOTAL_FLOOR = 50

# Promotion thresholds.
PROMOTION_ACCURACY_MIN = 0.75
PROMOTION_ACCURACY_N = 30
PROMOTION_BRIER_MAX = 0.15
PROMOTION_BRIER_N = 30
PROMOTION_CONFIDENCE_DRIFT_MAX = 0.05
PROMOTION_CONFIDENCE_DRIFT_N = 30

DEFAULT_WEIGHTING_MULTIPLIER = 1.0
MIN_WEIGHTING_MULTIPLIER = 0.0
MAX_WEIGHTING_MULTIPLIER = 2.0


# ── Reason / action enums ──────────────────────────────────────────


class TriggerReason(str, Enum):
    """Named retirement or promotion triggers.

    The label is also written into ``triggerReasons`` on the persisted
    triage row so the operator UI can render the rule that fired
    without re-running the math.
    """

    # Retirement
    ACCURACY_BELOW_THRESHOLD = "accuracy_below_threshold"
    BRIER_ABOVE_THRESHOLD = "brier_above_threshold"
    DIRECTIONAL_BELOW_THRESHOLD = "directional_below_threshold"
    CONFIDENCE_DRIFT_EXCEEDED = "confidence_drift_exceeded"
    RECENT_ACCURACY_DEGRADED = "recent_accuracy_degraded"

    # Promotion
    ACCURACY_PROMOTION = "accuracy_promotion"
    BRIER_PROMOTION = "brier_promotion"
    CONFIDENCE_BAND_PROMOTION = "confidence_band_promotion"


class RecommendedAction(str, Enum):
    NONE = "NONE"
    RETIRE = "RETIRE"
    PROMOTE = "PROMOTE"


# ── Trigger checks ─────────────────────────────────────────────────


def check_retirement_triggers(stats: CalibrationStats) -> list[TriggerReason]:
    """Return the named retirement triggers that fired for ``stats``.

    Returns an empty list when no trigger fired — the calibration loop
    treats that as "no retirement recommended". Order is stable so
    snapshot tests don't churn.
    """

    fired: list[TriggerReason] = []

    # Accuracy below floor over enough resolved invocations.
    if (
        stats.accuracy is not None
        and stats.resolved_invocations >= RETIREMENT_ACCURACY_N
        and stats.accuracy < RETIREMENT_ACCURACY_MIN
    ):
        fired.append(TriggerReason.ACCURACY_BELOW_THRESHOLD)

    # Mean Brier above ceiling over enough probabilistic resolutions.
    if (
        stats.mean_brier is not None
        and stats.probabilistic_resolved >= RETIREMENT_BRIER_N
        and stats.mean_brier > RETIREMENT_BRIER_MAX
    ):
        fired.append(TriggerReason.BRIER_ABOVE_THRESHOLD)

    # Directional accuracy below floor over enough directional resolutions.
    if (
        stats.directional_accuracy is not None
        and stats.directional_resolved >= RETIREMENT_DIRECTIONAL_N
        and stats.directional_accuracy < RETIREMENT_DIRECTIONAL_MIN
    ):
        fired.append(TriggerReason.DIRECTIONAL_BELOW_THRESHOLD)

    # Confidence-band drift above absolute-value cap.
    if (
        stats.confidence_calibration_drift is not None
        and stats.confidence_band_resolved >= RETIREMENT_CONFIDENCE_DRIFT_N
        and abs(stats.confidence_calibration_drift) > RETIREMENT_CONFIDENCE_DRIFT_MAX
    ):
        fired.append(TriggerReason.CONFIDENCE_DRIFT_EXCEEDED)

    # Rolling 30d accuracy degraded AND we have enough lifetime evidence
    # to take the recent dip seriously (i.e. it's not just startup noise).
    if (
        stats.last_30d_accuracy is not None
        and stats.total_invocations > RETIREMENT_RECENT_TOTAL_FLOOR
        and stats.last_30d_accuracy < RETIREMENT_RECENT_ACCURACY_MIN
    ):
        fired.append(TriggerReason.RECENT_ACCURACY_DEGRADED)

    return fired


def check_promotion_triggers(stats: CalibrationStats) -> list[TriggerReason]:
    """Return the named promotion triggers that fired."""

    fired: list[TriggerReason] = []

    if (
        stats.accuracy is not None
        and stats.resolved_invocations >= PROMOTION_ACCURACY_N
        and stats.accuracy > PROMOTION_ACCURACY_MIN
    ):
        fired.append(TriggerReason.ACCURACY_PROMOTION)

    if (
        stats.mean_brier is not None
        and stats.probabilistic_resolved >= PROMOTION_BRIER_N
        and stats.mean_brier < PROMOTION_BRIER_MAX
    ):
        fired.append(TriggerReason.BRIER_PROMOTION)

    if (
        stats.confidence_calibration_drift is not None
        and stats.confidence_band_resolved >= PROMOTION_CONFIDENCE_DRIFT_N
        and abs(stats.confidence_calibration_drift) <= PROMOTION_CONFIDENCE_DRIFT_MAX
    ):
        fired.append(TriggerReason.CONFIDENCE_BAND_PROMOTION)

    return fired


def recommended_multiplier_for_promotion(
    stats: CalibrationStats,
    *,
    current_multiplier: float = DEFAULT_WEIGHTING_MULTIPLIER,
) -> float:
    """How much weighting should this promotion buy?

    Each promotion trigger that fires bumps the multiplier by 0.25,
    capped at :data:`MAX_WEIGHTING_MULTIPLIER`. Falls back to the
    current multiplier when no promotion trigger fires.
    """

    triggers = check_promotion_triggers(stats)
    if not triggers:
        return float(max(MIN_WEIGHTING_MULTIPLIER, min(MAX_WEIGHTING_MULTIPLIER, current_multiplier)))
    bumped = float(current_multiplier) + 0.25 * len(triggers)
    return max(
        MIN_WEIGHTING_MULTIPLIER,
        min(MAX_WEIGHTING_MULTIPLIER, bumped),
    )


# ── Recommendation payload ─────────────────────────────────────────


class RetirementRecommendation(BaseModel):
    """Advisory recommendation produced by the calibration tick.

    The agent never auto-retires — the operator UI shows this row in a
    PENDING triage queue and the founder accepts / rejects / defers.
    """

    algorithm_id: str
    reasons: list[TriggerReason] = Field(default_factory=list)
    recommended_action: RecommendedAction = RecommendedAction.NONE
    recommended_multiplier: float = DEFAULT_WEIGHTING_MULTIPLIER
    narrative: str = ""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


def build_recommendation(
    *,
    algorithm_id: str,
    stats: CalibrationStats,
    current_multiplier: float = DEFAULT_WEIGHTING_MULTIPLIER,
) -> RetirementRecommendation:
    """Synthesize a :class:`RetirementRecommendation` from a stats snapshot.

    Retirement takes precedence over promotion: if any retirement
    trigger fires, we recommend RETIRE regardless of promotion
    candidacy (a borderline algorithm should never be both promoted
    and retired in the same tick).
    """

    retirement = check_retirement_triggers(stats)
    if retirement:
        return RetirementRecommendation(
            algorithm_id=algorithm_id,
            reasons=retirement,
            recommended_action=RecommendedAction.RETIRE,
            recommended_multiplier=float(current_multiplier),
            narrative=_render_retirement_narrative(retirement, stats),
        )

    promotion = check_promotion_triggers(stats)
    if promotion:
        new_multiplier = recommended_multiplier_for_promotion(
            stats, current_multiplier=current_multiplier
        )
        return RetirementRecommendation(
            algorithm_id=algorithm_id,
            reasons=promotion,
            recommended_action=RecommendedAction.PROMOTE,
            recommended_multiplier=new_multiplier,
            narrative=_render_promotion_narrative(promotion, stats, new_multiplier),
        )

    return RetirementRecommendation(
        algorithm_id=algorithm_id,
        reasons=[],
        recommended_action=RecommendedAction.NONE,
        recommended_multiplier=float(current_multiplier),
        narrative="",
    )


def _render_retirement_narrative(
    reasons: list[TriggerReason], stats: CalibrationStats
) -> str:
    """Human-readable summary the operator triage queue surfaces.

    Mirrors the structure of the methodology retirement memos so the
    founder reads the *evidence*, not the rule name.
    """
    parts: list[str] = []
    for reason in reasons:
        if reason is TriggerReason.ACCURACY_BELOW_THRESHOLD:
            parts.append(
                f"accuracy {stats.accuracy:.2f} over "
                f"{stats.resolved_invocations} resolved (floor "
                f"{RETIREMENT_ACCURACY_MIN:.2f} at N≥{RETIREMENT_ACCURACY_N})"
            )
        elif reason is TriggerReason.BRIER_ABOVE_THRESHOLD:
            parts.append(
                f"mean Brier {stats.mean_brier:.2f} over "
                f"{stats.probabilistic_resolved} probabilistic resolved (ceiling "
                f"{RETIREMENT_BRIER_MAX:.2f})"
            )
        elif reason is TriggerReason.DIRECTIONAL_BELOW_THRESHOLD:
            parts.append(
                f"directional accuracy {stats.directional_accuracy:.2f} over "
                f"{stats.directional_resolved} directional resolved (floor "
                f"{RETIREMENT_DIRECTIONAL_MIN:.2f})"
            )
        elif reason is TriggerReason.CONFIDENCE_DRIFT_EXCEEDED:
            drift = stats.confidence_calibration_drift or 0.0
            direction = "overconfident" if drift > 0 else "underconfident"
            parts.append(
                f"confidence-band drift {drift:+.2f} ({direction}) over "
                f"{stats.confidence_band_resolved} resolutions (cap "
                f"±{RETIREMENT_CONFIDENCE_DRIFT_MAX:.2f})"
            )
        elif reason is TriggerReason.RECENT_ACCURACY_DEGRADED:
            parts.append(
                f"last-30d accuracy {stats.last_30d_accuracy:.2f} over "
                f"{stats.last_30d_resolved} recent resolved (floor "
                f"{RETIREMENT_RECENT_ACCURACY_MIN:.2f}, lifetime "
                f"{stats.total_invocations} invocations)"
            )
    if not parts:
        return ""
    return "RETIRE recommended: " + "; ".join(parts) + "."


def _render_promotion_narrative(
    reasons: list[TriggerReason],
    stats: CalibrationStats,
    new_multiplier: float,
) -> str:
    parts: list[str] = []
    for reason in reasons:
        if reason is TriggerReason.ACCURACY_PROMOTION:
            parts.append(
                f"accuracy {stats.accuracy:.2f} over "
                f"{stats.resolved_invocations} resolved (≥"
                f"{PROMOTION_ACCURACY_MIN:.2f} at N≥{PROMOTION_ACCURACY_N})"
            )
        elif reason is TriggerReason.BRIER_PROMOTION:
            parts.append(
                f"mean Brier {stats.mean_brier:.2f} over "
                f"{stats.probabilistic_resolved} probabilistic resolved (≤"
                f"{PROMOTION_BRIER_MAX:.2f})"
            )
        elif reason is TriggerReason.CONFIDENCE_BAND_PROMOTION:
            drift = stats.confidence_calibration_drift or 0.0
            parts.append(
                f"confidence-band drift {drift:+.2f} within ±"
                f"{PROMOTION_CONFIDENCE_DRIFT_MAX:.2f} over "
                f"{stats.confidence_band_resolved} resolutions"
            )
    return (
        f"PROMOTE recommended (weighting → {new_multiplier:.2f}): "
        + "; ".join(parts)
        + "."
    )


__all__ = [
    "DEFAULT_WEIGHTING_MULTIPLIER",
    "MAX_WEIGHTING_MULTIPLIER",
    "MIN_WEIGHTING_MULTIPLIER",
    "PROMOTION_ACCURACY_MIN",
    "PROMOTION_ACCURACY_N",
    "PROMOTION_BRIER_MAX",
    "PROMOTION_BRIER_N",
    "PROMOTION_CONFIDENCE_DRIFT_MAX",
    "PROMOTION_CONFIDENCE_DRIFT_N",
    "RETIREMENT_ACCURACY_MIN",
    "RETIREMENT_ACCURACY_N",
    "RETIREMENT_BRIER_MAX",
    "RETIREMENT_BRIER_N",
    "RETIREMENT_CONFIDENCE_DRIFT_MAX",
    "RETIREMENT_CONFIDENCE_DRIFT_N",
    "RETIREMENT_DIRECTIONAL_MIN",
    "RETIREMENT_DIRECTIONAL_N",
    "RETIREMENT_RECENT_ACCURACY_MIN",
    "RETIREMENT_RECENT_TOTAL_FLOOR",
    "RecommendedAction",
    "RetirementRecommendation",
    "TriggerReason",
    "build_recommendation",
    "check_promotion_triggers",
    "check_retirement_triggers",
    "recommended_multiplier_for_promotion",
]
