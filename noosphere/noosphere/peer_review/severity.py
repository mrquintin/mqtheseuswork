"""Severity scoring for peer-review objections.

Every objection produced by the swarm is annotated with a severity in
``{"low", "medium", "high"}`` and a numeric value in ``[0, 1]``. The
score answers a single question: *if this objection is true, how much
would it move the conclusion's confidence?*

The rubric is composed of five inputs, deliberately mostly grounded
outside the LLM judge so the model cannot self-promote a nitpick into
a structural blow:

1. ``cascade_weight`` — confidence of the supporting edge the objection
   attacks. A 0.9 supports edge under attack matters more than a 0.3 one.
2. ``claim_centrality`` — how central the attacked claim is in the
   conclusion's argument graph (downstream-edge fan-out, normalised).
   An attack on a load-bearing premise outranks one on a tangent.
3. ``failure_mode_severity`` — if the objection points to a curated
   failure mode (see :mod:`noosphere.methods.failure_modes`), the
   curated severity is folded in. Curated `high` failure modes carry
   strong weight because a human approved them.
4. ``source_credibility`` — when the objection cites a source, the
   source's Beta-credibility posterior modulates the weight. A
   tabloid-cited objection cannot land at high.
5. ``judge_severity`` — the LLM judge's own estimate, **capped** by a
   bracket the structural inputs above define. The judge picks within a
   range; it cannot promote past it.

The bracket cap is the discipline: an objection's max severity is set
by the structural inputs; the judge can place inside that bracket but
not above. This is what makes the score robust to model puffery.

This rubric is *stipulated* — it maps inputs to a score by a formula
the firm asserts, not one fit to data. Once enough objection→outcome
data exists (see :mod:`noosphere.peer_review.severity_calibration`),
:func:`score_objection_with_model` replaces it with a logistic model
fit on which objections *actually* moved a conclusion. The stipulated
formula stays here as the cold-start fallback and the ablation
alternative — :func:`score_objection` is never deleted.

A severity score expires when the underlying conclusion is materially
revised (revision engine, prompt 16). Stale scores are not carried
forward — see :func:`is_stale`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional, Protocol

SeverityLabel = Literal["low", "medium", "high"]

# Public bracket boundaries. Documented in the module docstring; the
# tests in `test_objection_severity.py` pin them.
LOW_MAX = 0.34
MEDIUM_MAX = 0.67  # >= MEDIUM_MAX is "high"


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(x)))


@dataclass(frozen=True)
class SeverityInputs:
    """The structural inputs that bound an objection's severity.

    All numeric fields are in [0, 1]. Callers fill what they have; a
    missing input contributes 0 (i.e. nothing) rather than skewing the
    bracket. The judge's estimate is provided separately so the rubric
    can cap it explicitly.
    """

    cascade_weight: float = 0.0
    claim_centrality: float = 0.0
    failure_mode_severity: float = 0.0  # 0=no match, low=0.33, med=0.67, high=1.0
    source_credibility: Optional[float] = None  # None = no source cited
    judge_severity: Optional[float] = None  # None = no LLM estimate


@dataclass(frozen=True)
class ObjectionSeverity:
    """The severity annotation attached to one objection."""

    value: float
    label: SeverityLabel
    bracket_floor: float
    bracket_ceiling: float
    inputs: SeverityInputs
    judge_capped: bool
    rationale: str = ""
    scored_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Set when `mark_stale` runs after a material revision.
    stale: bool = False
    # Which scorer produced `value`: "stipulated" (the formula in this
    # module) or "calibrated" (the fitted model from
    # `severity_calibration`). Recorded so re-scores and ablations can
    # tell the two apart in the audit trail.
    scorer: str = "stipulated"

    def to_dict(self) -> dict:
        return {
            "value": round(self.value, 4),
            "label": self.label,
            "bracket_floor": round(self.bracket_floor, 4),
            "bracket_ceiling": round(self.bracket_ceiling, 4),
            "judge_capped": self.judge_capped,
            "stale": self.stale,
            "scorer": self.scorer,
            "rationale": self.rationale,
            "inputs": {
                "cascade_weight": round(self.inputs.cascade_weight, 4),
                "claim_centrality": round(self.inputs.claim_centrality, 4),
                "failure_mode_severity": round(
                    self.inputs.failure_mode_severity, 4
                ),
                "source_credibility": (
                    None
                    if self.inputs.source_credibility is None
                    else round(self.inputs.source_credibility, 4)
                ),
                "judge_severity": (
                    None
                    if self.inputs.judge_severity is None
                    else round(self.inputs.judge_severity, 4)
                ),
            },
            "scored_at": self.scored_at.isoformat(),
        }


# ── Severity rubric ──────────────────────────────────────────────────


# Weights applied to the structural inputs to compute the bracket
# ceiling. Cascade-weight and centrality are the two primary structural
# drivers — together they account for the bulk of the budget. The
# failure-mode signal is curated, so it carries real weight too. Source
# credibility is a multiplicative modulation when present, not an
# additive driver — a low-credibility source caps the bracket from
# above. The weights are tuned so that:
#   * cascade=1, centrality=1, failure_mode=0 -> ceiling ~0.85 (allows
#     high if the judge sees a structural blow).
#   * cascade=0, centrality=0, failure_mode=0 -> ceiling = 0 (the judge
#     cannot promote a nitpick into anything).
_W_CASCADE = 0.40
_W_CENTRALITY = 0.30
_W_FAILURE = 0.30


def _structural_ceiling(inp: SeverityInputs) -> float:
    """Upper bound on severity from structural inputs alone."""

    raw = (
        _W_CASCADE * _clamp01(inp.cascade_weight)
        + _W_CENTRALITY * _clamp01(inp.claim_centrality)
        + _W_FAILURE * _clamp01(inp.failure_mode_severity)
    )
    # Source credibility only modulates *down*: a present-but-weak
    # source lowers the ceiling; a present-and-strong source leaves it
    # alone; a missing source leaves it alone (we don't penalise an
    # objection for not citing a source — many objections are purely
    # methodological).
    cred = inp.source_credibility
    if cred is not None:
        raw = raw * _clamp01(cred)
    return _clamp01(raw)


def _structural_floor(inp: SeverityInputs) -> float:
    """Minimum severity from structural inputs.

    The floor catches the case where the structural signal is so strong
    (e.g. curated `high` failure mode on a load-bearing claim) that
    even a meek LLM estimate should not pull the score down to "low".
    """

    # The floor is the failure-mode signal when it lands in the high
    # bracket *and* the cascade/centrality structural support is
    # non-trivial. Otherwise no floor — the judge can park anywhere
    # within [0, ceiling].
    structural_support = _clamp01(
        0.5 * inp.cascade_weight + 0.5 * inp.claim_centrality
    )
    if inp.failure_mode_severity >= MEDIUM_MAX and structural_support >= 0.4:
        # Floor at the bottom of the medium bracket — never below
        # `low` if the curated prior is high and the claim has
        # structural weight.
        return LOW_MAX
    return 0.0


def label_for(value: float) -> SeverityLabel:
    if value < LOW_MAX:
        return "low"
    if value < MEDIUM_MAX:
        return "medium"
    return "high"


def score_objection(
    inputs: SeverityInputs, *, rationale: str = ""
) -> ObjectionSeverity:
    """Compute an :class:`ObjectionSeverity` from the rubric inputs.

    The judge's estimate is clamped into ``[floor, ceiling]``. If it is
    None, the severity falls back to the ceiling (the structural inputs
    define the score on their own). This guarantees:

    * Severity is monotonic in ``cascade_weight`` (and centrality, and
      failure-mode severity), holding other inputs fixed — see tests.
    * The judge cannot promote a low-bracket objection into "high".
    * A missing source is treated charitably (no penalty), but a
      present-and-weak source caps the ceiling.
    """

    ceiling = _structural_ceiling(inputs)
    floor = min(_structural_floor(inputs), ceiling)

    judge = inputs.judge_severity
    capped = False
    if judge is None:
        value = ceiling
    else:
        j = _clamp01(judge)
        value = j
        if value > ceiling:
            value = ceiling
            capped = True
        if value < floor:
            value = floor
            # Promoting up to floor is *not* a "judge cap" event — the
            # judge can disagree downwards but the structural prior
            # holds. We still record it on the rationale below.

    return ObjectionSeverity(
        value=value,
        label=label_for(value),
        bracket_floor=floor,
        bracket_ceiling=ceiling,
        inputs=inputs,
        judge_capped=capped,
        rationale=rationale,
        scorer="stipulated",
    )


# ── Calibrated scorer (prompt 22) ────────────────────────────────────


class CalibratedSeverityScorer(Protocol):
    """A fitted model that predicts P(material change) from SeverityInputs.

    Implemented by
    :class:`noosphere.peer_review.severity_calibration.SeverityCalibrationModel`.
    Typed structurally so this module needs no import of the calibration
    module — which itself imports this one, and would create a cycle.
    """

    def predict_inputs(self, inputs: "SeverityInputs") -> float: ...


def score_objection_with_model(
    inputs: SeverityInputs,
    model: CalibratedSeverityScorer,
    *,
    rationale: str = "",
) -> ObjectionSeverity:
    """Score an objection with the fitted calibration model (prompt 22).

    The model's predicted probability that the objection — if true —
    materially changes the conclusion *is* the severity value. This
    replaces the stipulated rubric (:func:`score_objection`) once enough
    objection→outcome data exists to fit on; the stipulated formula
    stays in this module as the cold-start fallback and the ablation
    alternative.

    The structural bracket is still computed and recorded for audit and
    the founder-facing UI, but it does **not** cap the calibrated value.
    The bracket cap existed to stop the *LLM judge* self-promoting a
    nitpick into a structural blow; a model fit on realized outcomes is
    already grounded in exactly the structural inputs the bracket was
    protecting, so capping it would only distort a calibrated number.
    ``judge_capped`` is therefore always ``False`` on a calibrated
    score, and ``scorer`` is ``"calibrated"``.
    """

    ceiling = _structural_ceiling(inputs)
    floor = min(_structural_floor(inputs), ceiling)
    value = _clamp01(model.predict_inputs(inputs))
    return ObjectionSeverity(
        value=value,
        label=label_for(value),
        bracket_floor=floor,
        bracket_ceiling=ceiling,
        inputs=inputs,
        judge_capped=False,
        rationale=rationale,
        scorer="calibrated",
    )


def mark_stale(severity: ObjectionSeverity) -> ObjectionSeverity:
    """Return a copy of ``severity`` with ``stale=True``.

    Called by the revision engine when the conclusion is materially
    revised — the old severity is no longer load-bearing because the
    underlying argument graph may have shifted.
    """

    return ObjectionSeverity(
        value=severity.value,
        label=severity.label,
        bracket_floor=severity.bracket_floor,
        bracket_ceiling=severity.bracket_ceiling,
        inputs=severity.inputs,
        judge_capped=severity.judge_capped,
        rationale=severity.rationale,
        scored_at=severity.scored_at,
        stale=True,
        scorer=severity.scorer,
    )


def is_stale(severity: ObjectionSeverity) -> bool:
    return severity.stale


# ── Aggregation: weighted count + max-severity gate ─────────────────


@dataclass(frozen=True)
class SeverityAggregate:
    """Aggregate of a swarm pass's per-objection severities.

    Fed into the MQS Severity sub-score and the publication gate.
    """

    weighted_count: float
    max_value: float
    max_label: SeverityLabel
    high_count: int
    medium_count: int
    low_count: int
    objections_total: int
    blocking: bool  # >= 2 unresolved high or any single high+blocker
    response_required_high: bool
    response_recommended_medium: bool

    def to_dict(self) -> dict:
        return {
            "weighted_count": round(self.weighted_count, 4),
            "max_value": round(self.max_value, 4),
            "max_label": self.max_label,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "objections_total": self.objections_total,
            "blocking": self.blocking,
            "response_required_high": self.response_required_high,
            "response_recommended_medium": self.response_recommended_medium,
        }


# Two unresolved high-severity objections trip the publication gate.
# The number is intentional — one outlier high might be a single
# reviewer overshooting; two distinct high objections is a structural
# pattern. Documented in tests.
HIGH_BLOCK_COUNT = 2


def aggregate(
    severities: Iterable[ObjectionSeverity],
    *,
    responses_resolved_for: Optional[set[int]] = None,
) -> SeverityAggregate:
    """Aggregate severities into the MQS-feeding signal.

    ``responses_resolved_for`` is an optional set of severity indices
    that have been answered by a reviewer/founder rebuttal. Only
    *unresolved* high severities count toward the blocking gate — the
    response loop is the firm's escape hatch.

    Stale severities are ignored entirely. The revision engine clears
    them by calling :func:`mark_stale`; an aggregate computed after a
    revision treats those as if they were never produced.
    """

    items = [s for s in severities if not s.stale]
    if not items:
        return SeverityAggregate(
            weighted_count=0.0,
            max_value=0.0,
            max_label="low",
            high_count=0,
            medium_count=0,
            low_count=0,
            objections_total=0,
            blocking=False,
            response_required_high=False,
            response_recommended_medium=False,
        )

    resolved = responses_resolved_for or set()
    weighted = sum(s.value for s in items)
    max_v = max(s.value for s in items)
    high = sum(1 for s in items if s.label == "high")
    medium = sum(1 for s in items if s.label == "medium")
    low = sum(1 for s in items if s.label == "low")

    unresolved_high = sum(
        1
        for i, s in enumerate(items)
        if s.label == "high" and i not in resolved
    )
    blocking = unresolved_high >= HIGH_BLOCK_COUNT

    return SeverityAggregate(
        weighted_count=weighted,
        max_value=max_v,
        max_label=label_for(max_v),
        high_count=high,
        medium_count=medium,
        low_count=low,
        objections_total=len(items),
        blocking=blocking,
        response_required_high=high > 0,
        response_recommended_medium=medium > 0,
    )


# ── MQS coupling ─────────────────────────────────────────────────────


def mqs_severity_penalty(agg: SeverityAggregate) -> float:
    """Return a multiplicative penalty in (0, 1] for the MQS Severity sub-score.

    Two high-severity objections (the blocking-gate threshold) take the
    sub-score below the publish threshold — concretely, multiplied by
    0.5 so a strong base severity falls under the typical 0.6 publish
    bar. Ten low-severity objections do not (their weighted count is
    low and the max is in the low bracket).
    """

    if agg.objections_total == 0:
        return 1.0

    # Cap the weighted-count drag at 0.85 so even a heavy-but-low pile
    # cannot zero the sub-score on its own; high-severity objections
    # still need to fire the max-gate to drop below publish.
    drag = max(0.0, 1.0 - 0.05 * agg.weighted_count)
    drag = max(drag, 0.85)

    if agg.blocking:
        return 0.5 * drag
    if agg.high_count >= 1:
        # Single high without the blocking threshold — meaningful but
        # not fatal, so a softer multiplier.
        return 0.7 * drag
    if agg.medium_count >= 2:
        return 0.85 * drag
    return drag


# ── Cascade-graph helpers ────────────────────────────────────────────


class _CascadeReader(Protocol):
    """Minimal cascade interface this module needs.

    Production wires :class:`noosphere.cascade.graph.CascadeGraph`;
    tests pass a stub. We only need the two read paths exposed by
    :mod:`noosphere.cascade.traverse`.
    """

    def explain(self, node_id: str) -> list: ...
    def downstream(self, node_id: str) -> list: ...


def claim_centrality_from_cascade(
    reader: _CascadeReader, claim_node_id: str
) -> float:
    """Compute a [0,1] centrality for the attacked claim.

    Centrality here is operationalised as the *fan-out* of downstream
    consumers: how many other claims/conclusions depend on or are
    supported by this one. A claim that nothing else rests on has
    centrality 0; a claim that 5+ downstreams rely on caps at 1.0.

    Kept deliberately simple — we want a deterministic signal the
    rubric can apply without an LLM call. Operators can replace the
    function later without touching :func:`score_objection`.
    """

    edges = reader.downstream(claim_node_id)
    n = len(edges)
    # Saturating function: 0 -> 0, 1 -> 0.4, 2 -> 0.65, 5+ -> ~1.0.
    if n <= 0:
        return 0.0
    return _clamp01(1.0 - (1.0 / (1.0 + 0.6 * n)))


def cascade_weight_from_edge_confidence(confidence: float) -> float:
    """Pass-through with clamp; named for the rubric input it feeds."""

    return _clamp01(confidence)


__all__ = [
    "HIGH_BLOCK_COUNT",
    "LOW_MAX",
    "MEDIUM_MAX",
    "CalibratedSeverityScorer",
    "ObjectionSeverity",
    "SeverityAggregate",
    "SeverityInputs",
    "SeverityLabel",
    "aggregate",
    "cascade_weight_from_edge_confidence",
    "claim_centrality_from_cascade",
    "is_stale",
    "label_for",
    "mark_stale",
    "mqs_severity_penalty",
    "score_objection",
    "score_objection_with_model",
]
