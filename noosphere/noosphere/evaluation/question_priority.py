"""Priority scoring for open questions.

Each `OpenQuestion` gets a priority score derived from three signals:

  - centrality: how many of the firm's existing conclusions reference
    or depend on the question. Higher centrality means resolving the
    question would force more downstream revisions.

  - replayability: how cheaply the resolution can be obtained. A
    literature lookup is cheap; rerunning a year of forecasting is
    expensive. We score `cheap → high`, `expensive → low`, because
    cheap-to-resolve questions should jump the queue when their
    expected value of information is comparable.

  - calibration relevance: how thin the firm's track record is in the
    question's domain. A question about a domain where calibration is
    well-established is worth less than a question about a domain
    where the firm has few resolved forecasts (the latter has more
    epistemic upside).

Each component is bounded to ``[0, 1]`` and the final score is a
weighted, capped sum:

    priority = clip(
        w_central * centrality +
        w_replay  * replayability +
        w_calib   * calibration_relevance,
        0.0, 1.0,
    )

The default weights are tuned so centrality alone cannot dominate the
score: a niche question that is cheap to resolve and lands in a thin
calibration domain can outscore a maximally-central one whose
resolution costs a quarter and that lives in a domain the firm has
already calibrated. This is the constraint the prompt pins:
*"do not let centrality dominate every other input"*.

Resolution status is a hard filter, not a score input. A question with
a `resolved_at` is not eligible for prioritization at all — the caller
is expected to drop those rows before passing them in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional


QUESTION_PRIORITY_SCHEMA = "theseus.question_priority.v1"


# Bounded so no single input can run away with the score.
DEFAULT_WEIGHTS: dict[str, float] = {
    "centrality": 0.40,
    "replayability": 0.30,
    "calibration_relevance": 0.30,
}

# A linked-conclusion count beyond this saturates the centrality term.
# Picked empirically: most questions touch 0-3 conclusions; a question
# linked to 8+ is already "as central as it gets" for ranking purposes.
CENTRALITY_SATURATION = 8.0

# Calibration relevance is high when there are few resolved forecasts in
# the domain. We saturate the *low-information* signal at 30 resolved
# forecasts — beyond that, calibration is "thick enough" that another
# data point doesn't move the firm's track record meaningfully.
CALIBRATION_THICK_THRESHOLD = 30.0

# Replayability cost in dollars: we map a logarithmic cost curve into a
# [0,1] band so a $5 literature lookup is ~1.0 and a $10,000 replay is
# ~0.0. Anything below $1 saturates at 1.0 (it's free); anything above
# $10k saturates at 0.0 (we can't justify the spend on EVI alone).
REPLAY_COST_FLOOR = 1.0
REPLAY_COST_CEILING = 10_000.0


@dataclass(frozen=True)
class OpenQuestionRow:
    """Minimal projection of an OpenQuestion that the scorer reads."""

    id: str
    summary: str
    domain: str = ""
    linked_conclusion_ids: tuple[str, ...] = ()
    estimated_resolution_cost_usd: float = 100.0
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class DomainCalibrationFootprint:
    """How thick the firm's track record is in this domain."""

    domain: str
    resolved_forecast_count: int = 0
    # Optional: 0=well calibrated, 1=miscalibrated. When supplied we
    # boost relevance for domains the firm is *both* thin in AND known
    # to be miscalibrated in.
    calibration_error: float = 0.0


@dataclass(frozen=True)
class PriorityComponent:
    name: str
    raw: float
    weight: float
    contribution: float


@dataclass(frozen=True)
class PriorityScore:
    question_id: str
    score: float
    components: tuple[PriorityComponent, ...]
    schema: str = QUESTION_PRIORITY_SCHEMA
    computed_at: Optional[datetime] = None
    notes: str = ""


# ── Component scorers ────────────────────────────────────────────────────────


def _clip01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def centrality(linked_conclusion_count: int) -> float:
    """How many existing conclusions depend on this question being settled.

    Bounded saturating curve: linear up to `CENTRALITY_SATURATION`, then
    flat. Keeps a 50-link question from dominating an 8-link question.
    """
    n = max(0, int(linked_conclusion_count))
    return _clip01(n / CENTRALITY_SATURATION)


def replayability(estimated_cost_usd: float) -> float:
    """How cheaply can the answer be obtained?

    Returns 1.0 for "free" (literature lookup), 0.0 for "we'd have to
    rerun a year of forecasting". Logarithmic so the gradient is rich
    in the $10–$1000 range where most calls actually live.
    """
    cost = max(REPLAY_COST_FLOOR, float(estimated_cost_usd))
    if cost >= REPLAY_COST_CEILING:
        return 0.0
    if cost <= REPLAY_COST_FLOOR:
        return 1.0
    log_cost = math.log10(cost)
    log_floor = math.log10(REPLAY_COST_FLOOR)
    log_ceiling = math.log10(REPLAY_COST_CEILING)
    fraction = (log_cost - log_floor) / (log_ceiling - log_floor)
    return _clip01(1.0 - fraction)


def calibration_relevance(footprint: Optional[DomainCalibrationFootprint]) -> float:
    """How thin is the firm's track record in this domain?

    Higher when the firm has few resolved forecasts in the domain. A
    known calibration error in the domain bumps the relevance up — a
    domain that's both thin AND miscalibrated is the highest-EVI place
    to put effort.
    """
    if footprint is None:
        return 0.5  # unknown domain — neutral relevance
    n = max(0, int(footprint.resolved_forecast_count))
    thinness = _clip01(1.0 - (n / CALIBRATION_THICK_THRESHOLD))
    err_bump = _clip01(footprint.calibration_error) * 0.25
    return _clip01(thinness + err_bump)


# ── Top-level scorer ─────────────────────────────────────────────────────────


def score_question(
    row: OpenQuestionRow,
    *,
    domain_footprint: Optional[DomainCalibrationFootprint] = None,
    weights: Optional[dict[str, float]] = None,
    now: Optional[datetime] = None,
) -> PriorityScore:
    if row.resolved_at is not None:
        # Resolved questions are not eligible for ranking. Caller-side
        # filter is the intended path; this raise is a tripwire.
        raise ValueError(
            f"score_question called on resolved question {row.id} "
            f"(resolved_at={row.resolved_at!r})"
        )

    w = dict(DEFAULT_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in w:
                w[k] = float(v)

    # Re-normalize weights so a caller passing eg {"centrality": 0.0}
    # doesn't silently shrink the maximum reachable score.
    weight_sum = sum(w.values())
    if weight_sum <= 0.0:
        w = dict(DEFAULT_WEIGHTS)
        weight_sum = sum(w.values())
    for k in w:
        w[k] = w[k] / weight_sum

    raw_central = centrality(len(row.linked_conclusion_ids))
    raw_replay = replayability(row.estimated_resolution_cost_usd)
    raw_calib = calibration_relevance(domain_footprint)

    components = (
        PriorityComponent(
            name="centrality",
            raw=raw_central,
            weight=w["centrality"],
            contribution=raw_central * w["centrality"],
        ),
        PriorityComponent(
            name="replayability",
            raw=raw_replay,
            weight=w["replayability"],
            contribution=raw_replay * w["replayability"],
        ),
        PriorityComponent(
            name="calibration_relevance",
            raw=raw_calib,
            weight=w["calibration_relevance"],
            contribution=raw_calib * w["calibration_relevance"],
        ),
    )

    score = _clip01(sum(c.contribution for c in components))
    return PriorityScore(
        question_id=row.id,
        score=score,
        components=components,
        computed_at=now,
    )


def score_questions(
    rows: Iterable[OpenQuestionRow],
    *,
    domain_footprints: Optional[dict[str, DomainCalibrationFootprint]] = None,
    weights: Optional[dict[str, float]] = None,
    now: Optional[datetime] = None,
) -> list[PriorityScore]:
    """Score a batch of questions, dropping resolved ones silently.

    Resolved questions are filtered up front rather than raising — the
    batch caller doesn't have to pre-filter. The single-row
    `score_question` retains the strict tripwire.
    """
    footprints = domain_footprints or {}
    out: list[PriorityScore] = []
    for row in rows:
        if row.resolved_at is not None:
            continue
        footprint = footprints.get(row.domain)
        out.append(
            score_question(
                row,
                domain_footprint=footprint,
                weights=weights,
                now=now,
            )
        )
    out.sort(key=lambda s: s.score, reverse=True)
    return out


__all__ = [
    "CALIBRATION_THICK_THRESHOLD",
    "CENTRALITY_SATURATION",
    "DEFAULT_WEIGHTS",
    "DomainCalibrationFootprint",
    "OpenQuestionRow",
    "PriorityComponent",
    "PriorityScore",
    "QUESTION_PRIORITY_SCHEMA",
    "REPLAY_COST_CEILING",
    "REPLAY_COST_FLOOR",
    "calibration_relevance",
    "centrality",
    "replayability",
    "score_question",
    "score_questions",
]
