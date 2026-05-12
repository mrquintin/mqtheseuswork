"""Decision frames — orthogonal lenses on a candidate trade.

Each frame is a small, pure function over :class:`FrameContext` that
returns a :class:`FrameResult`. A frame describes:

- the *name* of the lens it applies (e.g. "incentive_alignment");
- the *inputs* it consumes (which metrics, which context fields);
- the *assumptions* the lens rests on (and whether they look stable
  in this context);
- a verdict (:class:`FrameVerdict`) — the lens's standalone vote;
- the *failure modes* the frame is on the lookout for (purely
  descriptive — used in the trace).

The frame layer deliberately does not synthesize. It only emits
results. :func:`noosphere.decisions.synthesis.synthesize` is the only
place where multiple frames are combined into a single action — and
that combiner is itself a deterministic rule, not a model.

Why split this up at all? The architecture contract in
``docs/architecture/Algorithmized_Decision_Making.md`` (§1.2 and §2.5)
wants the trace to be *the* artifact: prose flows from the trace, not
the other way around. Multiple inspectable frames make the trace
genuinely inspectable — a reader can ask "which lenses agreed?" and
"which one blocked?" without reverse-engineering one collapsed score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


FRAMES_VERSION = "decision_frames@v1"


class FrameVerdict(str, Enum):
    """A single frame's vote on the candidate trade.

    Ordering of severity (low → high) when synthesis breaks ties:

    - ``SUPPORT``  — frame is comfortable with the trade as proposed.
    - ``WATCH``    — frame sees enough signal to surface, not stake.
    - ``ABSTAIN``  — frame's assumptions don't hold in this context.
    - ``REDUCE``   — frame is calling for less exposure (existing position).
    - ``EXIT``     — frame is calling for full closure (existing position).
    - ``HEDGE``    — frame is calling for offsetting exposure.
    - ``HARD_STOP``— frame considers the trade categorically forbidden
                     here; ``HARD_STOP`` from any frame forces
                     ``ABSTAIN`` at synthesis regardless of agreement
                     elsewhere.
    """

    SUPPORT = "SUPPORT"
    WATCH = "WATCH"
    ABSTAIN = "ABSTAIN"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    HEDGE = "HEDGE"
    HARD_STOP = "HARD_STOP"


_VERDICT_RANK = {
    FrameVerdict.SUPPORT: 0,
    FrameVerdict.WATCH: 1,
    FrameVerdict.ABSTAIN: 2,
    FrameVerdict.REDUCE: 3,
    FrameVerdict.EXIT: 4,
    FrameVerdict.HEDGE: 5,
    FrameVerdict.HARD_STOP: 6,
}


def verdict_severity(verdict: FrameVerdict) -> int:
    return _VERDICT_RANK[verdict]


# Thresholds the frames consult. Held here (not env-driven) so the
# decision trace is reproducible from its inputs alone.
CONTRADICTION_HARD_STOP = 0.5
CONTRADICTION_WATCH = 0.25
REFLEXIVITY_DECAY_WATCH = 0.5
REFLEXIVITY_EDGE_DOWNGRADE = 0.15
OPTION_VALUE_CONFIDENCE_FLOOR = 0.45
OPTION_VALUE_DECAY_CAP = 0.5
COORDINATION_EDGE_FLOOR = 0.04
COORDINATION_EDGE_CEILING = 0.30
LOW_CONFIDENCE_PENALTY = 0.4


@dataclass(frozen=True)
class FrameContext:
    """Shared input bundle the frames operate on.

    Frames pull only what they need. Keeping every shared input in
    one frozen dataclass means new frames don't need to grow new
    arguments — they just consult more fields. ``metrics`` is the
    canonical metric map from :mod:`noosphere.forecasts.decision_metrics`;
    keys are the metric names listed in §3 of the architecture doc.
    """

    side: str | None
    metrics: Mapping[str, "MetricView"]
    transfer_best_stance: str | None = None
    transfer_best_principle_id: str | None = None
    transfer_recommendation_count: int = 0
    position_state: Mapping[str, Any] = field(default_factory=dict)
    incentive_signals: tuple[str, ...] = ()
    coordination_signals: tuple[str, ...] = ()
    reflexive_signals: tuple[str, ...] = ()
    market_closed: bool = False
    extras: Mapping[str, Any] = field(default_factory=dict)

    def metric(self, name: str) -> "MetricView | None":
        return self.metrics.get(name)

    def metric_value(self, name: str, default: float = 0.0) -> float:
        m = self.metrics.get(name)
        if m is None:
            return default
        return float(m.value)

    def metric_low_conf(self, name: str) -> bool:
        m = self.metrics.get(name)
        if m is None:
            return True
        return bool(m.low_confidence)


@dataclass(frozen=True)
class MetricView:
    """Minimal view of a decision metric that frames need.

    Avoids importing ``DecisionMetric`` (defined in
    :mod:`noosphere.forecasts.decision_metrics`) so the decisions
    package can be used standalone — e.g. in tests that construct
    contexts without spinning up the full forecast pipeline. The
    :func:`from_decision_metrics` helper builds a context from the
    real metric objects.
    """

    name: str
    value: float
    low_confidence: bool = False


@dataclass(frozen=True)
class FrameResult:
    """Output of a single frame."""

    name: str
    verdict: FrameVerdict
    assumptions_stable: bool
    confidence: float
    side_preference: str | None
    metrics_consulted: tuple[str, ...]
    reasons: tuple[str, ...]
    failure_modes: tuple[str, ...]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "assumptions_stable": bool(self.assumptions_stable),
            "confidence": round(float(self.confidence), 6),
            "side_preference": self.side_preference,
            "metrics_consulted": list(self.metrics_consulted),
            "reasons": list(self.reasons),
            "failure_modes": list(self.failure_modes),
            "detail": self.detail,
        }


Frame = Callable[[FrameContext], FrameResult]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _stake_signal_from_metrics(ctx: FrameContext) -> tuple[float, bool]:
    """How confident should a frame be by default? Driven by
    ``low_confidence`` flags on the metrics it consulted.
    """
    edge = ctx.metric("market_mispricing_edge")
    confidence = ctx.metric("calibration_adjusted_confidence")
    abs_edge = abs(edge.value) if edge and not edge.low_confidence else 0.0
    base = confidence.value if confidence and not confidence.low_confidence else 0.4
    low_conf_present = any(m.low_confidence for m in ctx.metrics.values())
    scalar = _clamp((abs_edge + base) / 2.0)
    if low_conf_present:
        scalar *= 1.0 - LOW_CONFIDENCE_PENALTY
    return scalar, low_conf_present


# ─────────────────────────────────────────────────────────────────────
# Frame: contradiction / adversarial pressure
#
# Assumption: high contradiction in the supporting citations means the
# underlying claim is actively disputed within our own evidence set.
# That's not a confidence wobble; it's a categorical reason to refuse
# the trade. Lower contradiction widens to WATCH rather than SUPPORT,
# because *no* contradiction in a sample of three citations is weak
# evidence of robustness.


def contradiction_frame(ctx: FrameContext) -> FrameResult:
    contradiction = ctx.metric("contradiction_pressure")
    failure_modes = (
        "we suppress an adversarial citation by accident",
        "contradiction metric understates the conflict because the contrary citation is short",
    )
    metrics_consulted = ("contradiction_pressure",)
    if contradiction is None or contradiction.low_confidence:
        return FrameResult(
            name="contradiction",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("contradiction_pressure is missing or low_confidence",),
            failure_modes=failure_modes,
            detail="no contradiction signal to evaluate",
        )
    value = contradiction.value
    if value >= CONTRADICTION_HARD_STOP:
        return FrameResult(
            name="contradiction",
            verdict=FrameVerdict.HARD_STOP,
            assumptions_stable=True,
            confidence=_clamp(value),
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"contradiction_pressure={value:.3f} ≥ hard-stop τ={CONTRADICTION_HARD_STOP}",
            ),
            failure_modes=failure_modes,
            detail="categorical disagreement among the load-bearing citations",
        )
    if value >= CONTRADICTION_WATCH:
        return FrameResult(
            name="contradiction",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=True,
            confidence=_clamp(1.0 - value),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"contradiction_pressure={value:.3f} above WATCH floor {CONTRADICTION_WATCH}",
            ),
            failure_modes=failure_modes,
            detail="mild conflict — surface but do not stake",
        )
    return FrameResult(
        name="contradiction",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=True,
        confidence=_clamp(1.0 - value),
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=(
            f"contradiction_pressure={value:.3f} below WATCH floor {CONTRADICTION_WATCH}",
        ),
        failure_modes=failure_modes,
        detail="evidence does not actively contradict the proposed view",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: incentive alignment
#
# Caller supplies named incentive signals (e.g. "issuer_short_position",
# "operator_compensated_on_volume"). Any such signal whose token starts
# with "conflict:" or whose name is in the curated red list is a
# hard-stop. Otherwise the frame falls back to contradiction_pressure
# as a soft proxy for "does the rest of the evidence disagree about
# who benefits?".


_INCENTIVE_REDLIST = frozenset(
    {
        "issuer_conflict",
        "operator_conflict",
        "insider_unhedged",
        "principal_self_dealing",
        "sponsor_payoff_aligned_with_yes",
        "sponsor_payoff_aligned_with_no",
    }
)


def incentive_alignment_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "a curated red-list signal is missing for a new conflict pattern",
        "we treat a tag we don't recognize as benign",
    )
    metrics_consulted = ("contradiction_pressure",)
    signals = tuple(s for s in ctx.incentive_signals if s)
    hard_signals = [s for s in signals if s in _INCENTIVE_REDLIST or s.startswith("conflict:")]
    if hard_signals:
        return FrameResult(
            name="incentive_alignment",
            verdict=FrameVerdict.HARD_STOP,
            assumptions_stable=True,
            confidence=1.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=tuple(f"incentive red-list: {s}" for s in hard_signals),
            failure_modes=failure_modes,
            detail="at least one known conflict-of-interest signal is present",
        )
    contradiction = ctx.metric("contradiction_pressure")
    cv = contradiction.value if contradiction and not contradiction.low_confidence else 0.0
    if cv >= CONTRADICTION_HARD_STOP:
        return FrameResult(
            name="incentive_alignment",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=True,
            confidence=_clamp(1.0 - cv),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"no explicit conflict signal, but contradiction_pressure={cv:.3f} suggests disputed incentives",
            ),
            failure_modes=failure_modes,
            detail="incentive frame deferring to contradiction frame on disputed evidence",
        )
    return FrameResult(
        name="incentive_alignment",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=True,
        confidence=_clamp(1.0 - cv),
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=("no red-list incentive signal; evidence is not actively disputed",),
        failure_modes=failure_modes,
        detail="no known conflict pattern detected",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: coordination / equilibrium
#
# A market price is itself an equilibrium summary of other agents'
# beliefs. The coordination frame asks: when our edge is *very* small
# (price ≈ our estimate), the equilibrium already reflects what we
# know — WATCH not SUPPORT. When the edge is implausibly large, it
# may reflect a coordination failure (everyone else has private
# information we don't) — WATCH again. The sweet spot is moderate edge.


def coordination_equilibrium_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "the implied equilibrium reflects a thin book, not consensus",
        "we are anchoring on stale order-book prices",
    )
    metrics_consulted = (
        "market_mispricing_edge",
        "liquidity_cost_feasibility",
    )
    edge = ctx.metric("market_mispricing_edge")
    liquidity = ctx.metric("liquidity_cost_feasibility")
    if edge is None or edge.low_confidence:
        return FrameResult(
            name="coordination_equilibrium",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("market_mispricing_edge missing — no equilibrium signal",),
            failure_modes=failure_modes,
            detail="cannot evaluate coordination without a comparable price",
        )
    abs_edge = abs(edge.value)
    signals = tuple(s for s in ctx.coordination_signals if s)
    thin_book = "thin_book" in signals or (liquidity is not None and liquidity.value <= 0.2 and not liquidity.low_confidence)
    if abs_edge < COORDINATION_EDGE_FLOOR:
        return FrameResult(
            name="coordination_equilibrium",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=True,
            confidence=_clamp(0.5 - abs_edge),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"|edge|={abs_edge:.3f} < equilibrium floor {COORDINATION_EDGE_FLOOR};"
                " market already prices our view",
            ),
            failure_modes=failure_modes,
            detail="price ≈ our estimate — no coordination advantage",
        )
    if abs_edge > COORDINATION_EDGE_CEILING or thin_book:
        return FrameResult(
            name="coordination_equilibrium",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=not thin_book,
            confidence=_clamp(0.5 - (abs_edge - COORDINATION_EDGE_CEILING)),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                (f"|edge|={abs_edge:.3f} > coordination ceiling {COORDINATION_EDGE_CEILING};"
                 " implausibly large edge suggests we are missing information")
                if abs_edge > COORDINATION_EDGE_CEILING
                else "liquidity flagged as thin → no informative equilibrium",
            ),
            failure_modes=failure_modes,
            detail="edge is implausibly large or book is thin",
        )
    return FrameResult(
        name="coordination_equilibrium",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=True,
        confidence=_clamp(abs_edge),
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=(
            f"|edge|={abs_edge:.3f} in coordination window "
            f"[{COORDINATION_EDGE_FLOOR}, {COORDINATION_EDGE_CEILING}]",
        ),
        failure_modes=failure_modes,
        detail="market disagrees with us within a plausible band",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: principal-agent
#
# When we already hold a position whose underlying principle was
# revoked, exit. When our open side now disagrees with the edge, the
# agent (the position) is no longer serving the principal (the thesis);
# reduce. Otherwise the frame stays silent (SUPPORT) — it has nothing
# to say about a fresh trade.


def principal_agent_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "we treat a revoked-principle signal as benign on a partial position",
        "open_side is missing or inconsistent with the actual book",
    )
    metrics_consulted = ("market_mispricing_edge",)
    state = ctx.position_state or {}
    revoked = bool(state.get("principles_revoked", False))
    open_side = str(state.get("open_side", "") or "").upper() or None
    if revoked:
        return FrameResult(
            name="principal_agent",
            verdict=FrameVerdict.EXIT,
            assumptions_stable=True,
            confidence=1.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("a principle backing the open position was revoked → exit",),
            failure_modes=failure_modes,
            detail="principal (thesis) no longer endorses the agent (position)",
        )
    edge = ctx.metric("market_mispricing_edge")
    edge_low = edge is None or edge.low_confidence
    if open_side and ctx.side and open_side != ctx.side and not edge_low:
        return FrameResult(
            name="principal_agent",
            verdict=FrameVerdict.REDUCE,
            assumptions_stable=True,
            confidence=_clamp(abs(edge.value) if edge else 0.0),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"open position side {open_side} disagrees with current edge side {ctx.side}",
            ),
            failure_modes=failure_modes,
            detail="position no longer expresses the live thesis",
        )
    return FrameResult(
        name="principal_agent",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=True,
        confidence=0.5 if not open_side else 0.75,
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=("no principal-agent conflict detected for this position state",),
        failure_modes=failure_modes,
        detail="no open conflict between thesis and position",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: reflexivity / second-order effects
#
# Reflexivity here: large naive edges that depend on the market not
# moving toward our estimate. When temporal decay is also high, the
# market is likely to adjust before resolution — the "edge" is partly
# illusory. The frame downgrades SUPPORT → WATCH in that regime.


def reflexivity_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "we mis-estimate decay when the question is binary and resolves discretely",
        "second-order effects compound faster than we modeled",
    )
    metrics_consulted = (
        "market_mispricing_edge",
        "temporal_decay_pressure",
    )
    edge = ctx.metric("market_mispricing_edge")
    decay = ctx.metric("temporal_decay_pressure")
    if edge is None or edge.low_confidence:
        return FrameResult(
            name="reflexivity",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("no edge to reason about reflexively",),
            failure_modes=failure_modes,
            detail="missing edge metric",
        )
    abs_edge = abs(edge.value)
    decay_value = decay.value if decay and not decay.low_confidence else 0.5
    explicit = bool(ctx.reflexive_signals)
    if explicit:
        reasons = (
            "caller flagged explicit reflexive signals: " + ", ".join(ctx.reflexive_signals),
        )
        return FrameResult(
            name="reflexivity",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=False,
            confidence=0.4,
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=reasons,
            failure_modes=failure_modes,
            detail="reflexive feedback explicitly named — naive edge is suspect",
        )
    if abs_edge >= REFLEXIVITY_EDGE_DOWNGRADE and decay_value >= REFLEXIVITY_DECAY_WATCH:
        return FrameResult(
            name="reflexivity",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=True,
            confidence=_clamp(1.0 - decay_value),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"|edge|={abs_edge:.3f} large enough to provoke reaction"
                f" and temporal_decay_pressure={decay_value:.3f} ≥ {REFLEXIVITY_DECAY_WATCH}",
            ),
            failure_modes=failure_modes,
            detail="market is likely to move toward our estimate before resolution",
        )
    return FrameResult(
        name="reflexivity",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=True,
        confidence=_clamp(abs_edge - decay_value * 0.25, 0.0, 1.0),
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=(
            f"|edge|={abs_edge:.3f} and decay={decay_value:.3f} below reflexivity-watch thresholds",
        ),
        failure_modes=failure_modes,
        detail="no obvious reflexive feedback expected",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: option value / asymmetry
#
# Acting now vs. waiting: when our calibration-adjusted confidence is
# weak but the edge is real, the option value of waiting (more data,
# resolved questions, fewer unknowns) is often positive — WATCH.
# When confidence is strong *and* time-to-resolution is short
# (high decay), waiting is no longer free — SUPPORT.


def option_value_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "we discount option value when the underlying volatility is high",
        "we overpay for optionality the market also prices in",
    )
    metrics_consulted = (
        "calibration_adjusted_confidence",
        "temporal_decay_pressure",
        "market_mispricing_edge",
    )
    edge = ctx.metric("market_mispricing_edge")
    confidence = ctx.metric("calibration_adjusted_confidence")
    decay = ctx.metric("temporal_decay_pressure")
    if edge is None or edge.low_confidence:
        return FrameResult(
            name="option_value",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("no edge — option value of waiting cannot be compared",),
            failure_modes=failure_modes,
            detail="missing edge",
        )
    conf_value = confidence.value if confidence and not confidence.low_confidence else 0.0
    decay_value = decay.value if decay and not decay.low_confidence else 0.0
    if conf_value < OPTION_VALUE_CONFIDENCE_FLOOR and decay_value < OPTION_VALUE_DECAY_CAP:
        return FrameResult(
            name="option_value",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=confidence is not None and not confidence.low_confidence,
            confidence=_clamp(OPTION_VALUE_CONFIDENCE_FLOOR - conf_value),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"confidence={conf_value:.3f} < {OPTION_VALUE_CONFIDENCE_FLOOR}"
                f" and decay={decay_value:.3f} leaves time to wait",
            ),
            failure_modes=failure_modes,
            detail="option value of waiting > option value of acting",
        )
    return FrameResult(
        name="option_value",
        verdict=FrameVerdict.SUPPORT,
        assumptions_stable=confidence is not None and not confidence.low_confidence,
        confidence=_clamp(conf_value),
        side_preference=ctx.side,
        metrics_consulted=metrics_consulted,
        reasons=(
            f"confidence={conf_value:.3f} ≥ floor or decay={decay_value:.3f} ≥ cap — acting now",
        ),
        failure_modes=failure_modes,
        detail="waiting is no longer cheap",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame: empirical transfer
#
# Maps the analogical-transfer best stance into a frame verdict.
# DOES_NOT_APPLY is a hard-stop only if the transfer report had
# enough recommendations to be informative; a thin report degrades
# to ABSTAIN (unstable assumption) instead.


def empirical_transfer_frame(ctx: FrameContext) -> FrameResult:
    failure_modes = (
        "the closest empirical case is structurally similar but causally different",
        "we have too few cases to draw a stance",
    )
    metrics_consulted = ()
    stance = (ctx.transfer_best_stance or "").upper()
    n = ctx.transfer_recommendation_count
    principle_id = ctx.transfer_best_principle_id
    if not stance:
        return FrameResult(
            name="empirical_transfer",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.0,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=("no analogical transfer report attached",),
            failure_modes=failure_modes,
            detail="empirical transfer unavailable",
        )
    if stance == "DOES_NOT_APPLY":
        if n >= 2:
            return FrameResult(
                name="empirical_transfer",
                verdict=FrameVerdict.HARD_STOP,
                assumptions_stable=True,
                confidence=1.0,
                side_preference=None,
                metrics_consulted=metrics_consulted,
                reasons=(
                    f"transfer best_stance=DOES_NOT_APPLY across {n} recommendations"
                    + (f" (principle={principle_id})" if principle_id else ""),
                ),
                failure_modes=failure_modes,
                detail="empirically analogous cases reject this thesis",
            )
        return FrameResult(
            name="empirical_transfer",
            verdict=FrameVerdict.ABSTAIN,
            assumptions_stable=False,
            confidence=0.5,
            side_preference=None,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"transfer best_stance=DOES_NOT_APPLY but only {n} recommendations — insufficient base",
            ),
            failure_modes=failure_modes,
            detail="single negative transfer; abstain rather than veto",
        )
    if stance == "APPLIES":
        return FrameResult(
            name="empirical_transfer",
            verdict=FrameVerdict.SUPPORT,
            assumptions_stable=True,
            confidence=_clamp(min(1.0, 0.4 + 0.1 * n)),
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"transfer best_stance=APPLIES across {n} recommendations"
                + (f" (principle={principle_id})" if principle_id else ""),
            ),
            failure_modes=failure_modes,
            detail="prior cases support the thesis",
        )
    if stance == "WATCH":
        return FrameResult(
            name="empirical_transfer",
            verdict=FrameVerdict.WATCH,
            assumptions_stable=True,
            confidence=0.4,
            side_preference=ctx.side,
            metrics_consulted=metrics_consulted,
            reasons=(
                f"transfer best_stance=WATCH across {n} recommendations",
            ),
            failure_modes=failure_modes,
            detail="prior cases ambivalent",
        )
    return FrameResult(
        name="empirical_transfer",
        verdict=FrameVerdict.ABSTAIN,
        assumptions_stable=False,
        confidence=0.2,
        side_preference=None,
        metrics_consulted=metrics_consulted,
        reasons=(f"transfer best_stance={stance} — unstable for action",),
        failure_modes=failure_modes,
        detail="empirical transfer is non-committal",
    )


# ─────────────────────────────────────────────────────────────────────
# Frame registry / runner


DEFAULT_FRAMES: tuple[Frame, ...] = (
    incentive_alignment_frame,
    coordination_equilibrium_frame,
    principal_agent_frame,
    reflexivity_frame,
    option_value_frame,
    contradiction_frame,
    empirical_transfer_frame,
)


def run_frames(
    ctx: FrameContext,
    frames: Sequence[Frame] = DEFAULT_FRAMES,
) -> tuple[FrameResult, ...]:
    """Evaluate every frame against the context. Order is preserved."""
    return tuple(frame(ctx) for frame in frames)


def context_from_decision_metrics(
    *,
    side: str | None,
    metrics: Sequence[Any],
    transfer_report: Any | None = None,
    position_state: Mapping[str, Any] | None = None,
    incentive_signals: Sequence[str] = (),
    coordination_signals: Sequence[str] = (),
    reflexive_signals: Sequence[str] = (),
    market_closed: bool = False,
) -> FrameContext:
    """Build a :class:`FrameContext` from
    :class:`noosphere.forecasts.decision_metrics.DecisionMetric` rows.

    Kept in this module (not in ``decision_metrics``) so the decisions
    package depends on forecasts only via duck typing — same shape,
    no import cycle.
    """
    metric_views: dict[str, MetricView] = {}
    for metric in metrics:
        metric_views[str(metric.name)] = MetricView(
            name=str(metric.name),
            value=float(metric.value),
            low_confidence=bool(getattr(metric, "low_confidence", False)),
        )
    stance = None
    principle_id = None
    rec_count = 0
    if transfer_report is not None:
        stance = getattr(transfer_report, "best_stance", None) or None
        principle_id = getattr(transfer_report, "best_principle_id", None)
        recs = getattr(transfer_report, "recommendations", ()) or ()
        rec_count = len(recs)
    return FrameContext(
        side=side,
        metrics=metric_views,
        transfer_best_stance=str(stance) if stance else None,
        transfer_best_principle_id=str(principle_id) if principle_id else None,
        transfer_recommendation_count=rec_count,
        position_state=dict(position_state or {}),
        incentive_signals=tuple(incentive_signals),
        coordination_signals=tuple(coordination_signals),
        reflexive_signals=tuple(reflexive_signals),
        market_closed=bool(market_closed),
    )


__all__ = [
    "CONTRADICTION_HARD_STOP",
    "CONTRADICTION_WATCH",
    "COORDINATION_EDGE_CEILING",
    "COORDINATION_EDGE_FLOOR",
    "DEFAULT_FRAMES",
    "FRAMES_VERSION",
    "Frame",
    "FrameContext",
    "FrameResult",
    "FrameVerdict",
    "MetricView",
    "OPTION_VALUE_CONFIDENCE_FLOOR",
    "OPTION_VALUE_DECAY_CAP",
    "REFLEXIVITY_DECAY_WATCH",
    "REFLEXIVITY_EDGE_DOWNGRADE",
    "context_from_decision_metrics",
    "contradiction_frame",
    "coordination_equilibrium_frame",
    "empirical_transfer_frame",
    "incentive_alignment_frame",
    "option_value_frame",
    "principal_agent_frame",
    "reflexivity_frame",
    "run_frames",
    "verdict_severity",
]
