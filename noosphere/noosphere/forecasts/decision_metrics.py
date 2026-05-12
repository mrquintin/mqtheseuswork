"""Deterministic decision-metric and rule-graph engine for Forecasts.

This module implements the §3 catalog and §2.3 rule graph described in
``docs/architecture/Algorithmized_Decision_Making.md``. Inputs are the
artifacts already produced by ``forecast_generator`` (market row,
retrieved sources, validated citations, parsed LLM payload, optional
paper-bet record, optional calibration record). Outputs are a
typed :class:`MarketDecisionTrace` whose intermediate metric values,
rule firings, final action, and stake recommendation are reproducible
from those inputs alone — no further LLM calls, no randomness.

The trace is the investable artifact. Prose generated elsewhere is
allowed to describe it but never to override it: callers serialize the
trace into a stable JSON shape and persist it under
``ForecastTrace.model_output["decision_trace"]``.

Missing inputs degrade gracefully: metrics that cannot be computed are
recorded with ``low_confidence=True`` and a sentinel value, the
``confidence`` field on the trace is reduced, and the rule graph
refuses to escalate beyond ``WATCH`` rather than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Sequence

from noosphere.decisions.frames import (
    FrameResult,
    context_from_decision_metrics,
    run_frames,
)
from noosphere.decisions.synthesis import (
    DecisionSynthesis,
    SynthesisAction,
    synthesize,
)
from noosphere.principles.transfer import (
    TransferReport,
    TransferStance,
)


TRACE_VERSION = "decision_metrics@v1"

# Thresholds. Kept here (not env-driven) so the trace is reproducible
# from inputs alone; production overrides will move into a versioned
# rule-graph config per §2.3 of the design doc.
EDGE_PAPER_THRESHOLD = 0.05
EDGE_LIVE_THRESHOLD = 0.08
CONFIDENCE_LIVE_THRESHOLD = 0.55
LOCALITY_LIVE_THRESHOLD = 0.6
LIQUIDITY_LIVE_THRESHOLD = 0.5
CONTRADICTION_VETO = 0.5
DECAY_VETO = 0.9
DECAY_DOWNGRADE = 0.7
MIN_PAPER_STAKE_USD = 1.0
DEFAULT_PAPER_STAKE_USD = 10.0
SOURCE_AGE_REFERENCE = timedelta(days=18 * 31)


class MarketDecisionAction(str, Enum):
    """Investable outputs the rule graph may emit.

    The first version implements ABSTAIN, WATCH, PAPER_TRADE, and
    LIVE_CANDIDATE end-to-end. REDUCE and EXIT are reachable only when
    callers supply a non-empty ``position_state`` to
    :func:`build_decision_trace` (§6 prompt 20). HEDGE is intentionally
    omitted from v1 per §8 open questions.
    """

    ABSTAIN = "ABSTAIN"
    WATCH = "WATCH"
    PAPER_TRADE = "PAPER_TRADE"
    LIVE_CANDIDATE = "LIVE_CANDIDATE"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


@dataclass(frozen=True)
class DecisionMetric:
    name: str
    value: float
    range_low: float
    range_high: float
    method: str
    low_confidence: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(float(self.value), 6),
            "range": [self.range_low, self.range_high],
            "method": self.method,
            "low_confidence": bool(self.low_confidence),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DecisionRuleResult:
    name: str
    kind: str           # "threshold" | "veto" | "bucket" | "combiner"
    fired: bool         # rule was evaluated (vs short-circuited)
    passed: bool        # rule's predicate held
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "fired": bool(self.fired),
            "passed": bool(self.passed),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class MarketDecisionTrace:
    action: MarketDecisionAction
    side: str | None
    confidence: float
    stake_recommendation_usd: float | None
    metrics: tuple[DecisionMetric, ...]
    rules: tuple[DecisionRuleResult, ...]
    reasons: tuple[str, ...]
    trace_version: str = TRACE_VERSION
    transfer_report: TransferReport | None = None
    frames: tuple[FrameResult, ...] = ()
    synthesis: DecisionSynthesis | None = None

    def metric(self, name: str) -> DecisionMetric | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def frame(self, name: str) -> FrameResult | None:
        for f in self.frames:
            if f.name == name:
                return f
        return None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "action": self.action.value,
            "side": self.side,
            "confidence": round(float(self.confidence), 6),
            "stake_recommendation_usd": (
                None
                if self.stake_recommendation_usd is None
                else round(float(self.stake_recommendation_usd), 2)
            ),
            "metrics": [m.to_dict() for m in self.metrics],
            "rules": [r.to_dict() for r in self.rules],
            "reasons": list(self.reasons),
            "trace_version": self.trace_version,
        }
        if self.transfer_report is not None:
            body["analogical_transfer"] = self.transfer_report.to_dict()
        if self.frames:
            body["frames"] = [f.to_dict() for f in self.frames]
        if self.synthesis is not None:
            body["synthesis"] = self.synthesis.to_dict()
        return body


# ---------------------------------------------------------------------
# Helpers


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _status_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value or "").upper()


def _source_created_at(source: Any) -> datetime | None:
    metadata = getattr(source, "metadata", {}) or {}
    for key in ("created_at", "createdAt", "episode_date", "updated_at"):
        raw = metadata.get(key) if isinstance(metadata, Mapping) else None
        if isinstance(raw, datetime):
            return _as_utc(raw)
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            return _as_utc(parsed)
    return None


# ---------------------------------------------------------------------
# Metric calculators
#
# Every calculator is pure: same inputs → same metric. Calculators
# that lack their data return ``low_confidence=True`` with a sentinel
# value rather than raising.


def compute_market_mispricing_edge(
    probability_yes: Any,
    market_yes_price: Any,
) -> DecisionMetric:
    """§3.9 — signed edge in [-1, 1]."""
    p = _to_float(probability_yes)
    market_p = _to_float(market_yes_price)
    if p is None or market_p is None or not 0.0 < market_p < 1.0:
        return DecisionMetric(
            name="market_mispricing_edge",
            value=0.0,
            range_low=-1.0,
            range_high=1.0,
            method="edge_calc@v1",
            low_confidence=True,
            detail="missing or invalid probability/price",
        )
    edge = _clamp(p - market_p, -1.0, 1.0)
    return DecisionMetric(
        name="market_mispricing_edge",
        value=edge,
        range_low=-1.0,
        range_high=1.0,
        method="edge_calc@v1",
        detail=f"firm_p={p:.4f} market_p={market_p:.4f}",
    )


def compute_calibration_adjusted_confidence(
    confidence_low: Any,
    confidence_high: Any,
    calibration_state: Mapping[str, Any] | None,
    topic_hint: str | None = None,
) -> DecisionMetric:
    """§3.8 — confidence (1 - interval width) mapped through per-domain
    calibration when available; otherwise the raw scalar with
    ``low_confidence=True`` so the rule graph refuses to escalate to live.
    """
    low = _to_float(confidence_low)
    high = _to_float(confidence_high)
    if low is None or high is None or low > high:
        return DecisionMetric(
            name="calibration_adjusted_confidence",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method="recalibration@v1",
            low_confidence=True,
            detail="confidence interval missing or inverted",
        )
    raw = _clamp(1.0 - (high - low), 0.0, 1.0)

    if not calibration_state:
        return DecisionMetric(
            name="calibration_adjusted_confidence",
            value=raw,
            range_low=0.0,
            range_high=1.0,
            method="recalibration@v1",
            low_confidence=True,
            detail="no active calibration record",
        )
    samples = int(calibration_state.get("min_samples", 0) or 0)
    threshold = int(calibration_state.get("recalibration_min_samples", 30) or 30)
    if samples < threshold:
        return DecisionMetric(
            name="calibration_adjusted_confidence",
            value=raw,
            range_low=0.0,
            range_high=1.0,
            method="recalibration@v1",
            low_confidence=True,
            detail=f"calibration samples {samples} < min {threshold}",
        )
    domain_map = calibration_state.get("domains") or {}
    adjustment = 1.0
    if topic_hint and isinstance(domain_map, Mapping):
        adjustment = float(domain_map.get(topic_hint, domain_map.get("__default__", 1.0)) or 1.0)
    adjusted = _clamp(raw * adjustment, 0.0, 1.0)
    return DecisionMetric(
        name="calibration_adjusted_confidence",
        value=adjusted,
        range_low=0.0,
        range_high=1.0,
        method="recalibration@v1",
        detail=f"raw={raw:.4f} factor={adjustment:.4f}",
    )


def compute_source_domain_locality(
    sources: Sequence[Any],
    citations: Sequence[Mapping[str, Any]],
    market: Any,
) -> DecisionMetric:
    """§3.4 — fraction of cited sources whose metadata-derived domain
    overlaps the market's category. Missing categories → low_confidence.
    """
    market_category = str(getattr(market, "category", "") or "").strip().lower()
    if not citations:
        return DecisionMetric(
            name="source_domain_locality",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method="domain_bounds@v1",
            low_confidence=True,
            detail="no citations present",
        )
    by_id = {
        (str(getattr(s, "source_type", "")).upper(), str(getattr(s, "source_id", ""))): s
        for s in sources
    }
    if not market_category:
        return DecisionMetric(
            name="source_domain_locality",
            value=0.5,
            range_low=0.0,
            range_high=1.0,
            method="domain_bounds@v1",
            low_confidence=True,
            detail="market has no category; locality cannot be tested",
        )
    in_bounds = 0
    judged = 0
    for citation in citations:
        key = (
            str(citation.get("source_type", "")).upper(),
            str(citation.get("source_id", "")),
        )
        source = by_id.get(key)
        if source is None:
            continue
        judged += 1
        metadata = getattr(source, "metadata", {}) or {}
        disciplines = metadata.get("disciplines") if isinstance(metadata, Mapping) else None
        terms: list[str] = []
        if isinstance(disciplines, (list, tuple)):
            terms.extend(str(d).lower() for d in disciplines)
        topic = metadata.get("topic_hint") if isinstance(metadata, Mapping) else None
        if isinstance(topic, str):
            terms.append(topic.lower())
        if not terms:
            continue
        if any(market_category in t or t in market_category for t in terms):
            in_bounds += 1
    if judged == 0:
        return DecisionMetric(
            name="source_domain_locality",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method="domain_bounds@v1",
            low_confidence=True,
            detail="no cited sources resolved to retrieved sources",
        )
    value = in_bounds / judged
    return DecisionMetric(
        name="source_domain_locality",
        value=value,
        range_low=0.0,
        range_high=1.0,
        method="domain_bounds@v1",
        detail=f"{in_bounds}/{judged} citations in-bounds for category={market_category!r}",
    )


def compute_contradiction_pressure(
    citations: Sequence[Mapping[str, Any]],
    extra_contradictions: Sequence[Mapping[str, Any]] = (),
) -> DecisionMetric:
    """§3.2 — proxy: fraction of citations whose ``support_label`` is
    ``CONTRARY``, optionally widened by a caller-supplied
    ``extra_contradictions`` list (open contradictory conclusions
    matched at retrieval time).
    """
    total = len(citations) + len(extra_contradictions)
    if total == 0:
        return DecisionMetric(
            name="contradiction_pressure",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method="contradiction_probe@v1",
            low_confidence=True,
            detail="no citations to evaluate",
        )
    contrary = sum(
        1
        for c in citations
        if str(c.get("support_label", "")).upper() == "CONTRARY"
    )
    contrary += len(extra_contradictions)
    value = _clamp(contrary / total, 0.0, 1.0)
    return DecisionMetric(
        name="contradiction_pressure",
        value=value,
        range_low=0.0,
        range_high=1.0,
        method="contradiction_probe@v1",
        detail=f"{contrary}/{total} contrary",
    )


def compute_liquidity_cost_feasibility(
    market: Any,
    suggested_stake_usd: float | None,
) -> DecisionMetric:
    """§3.10 — 1 − fraction of stake consumed by spread/depth. Uses
    ``raw_payload['spread']`` or ``raw_payload['depth_usd']`` if present.
    Collapses to 0 when ``low_liquidity`` is True on the market mirror.
    """
    raw = getattr(market, "raw_payload", {}) or {}
    if not isinstance(raw, Mapping):
        raw = {}
    low_liquidity = bool(raw.get("low_liquidity", False))
    yes_price = _to_float(getattr(market, "current_yes_price", None))
    no_price = _to_float(getattr(market, "current_no_price", None))
    spread = _to_float(raw.get("spread"))
    if spread is None and yes_price is not None and no_price is not None:
        implied = yes_price + no_price
        if 0.5 < implied < 1.5:
            spread = abs(1.0 - implied)
    depth_usd = _to_float(raw.get("depth_usd"))
    if low_liquidity:
        return DecisionMetric(
            name="liquidity_cost_feasibility",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method="edge_calc@v1",
            detail="market mirror flagged low_liquidity",
        )
    if spread is None and depth_usd is None:
        return DecisionMetric(
            name="liquidity_cost_feasibility",
            value=0.5,
            range_low=0.0,
            range_high=1.0,
            method="edge_calc@v1",
            low_confidence=True,
            detail="no spread or depth data on market.raw_payload",
        )
    stake = suggested_stake_usd if suggested_stake_usd and suggested_stake_usd > 0 else DEFAULT_PAPER_STAKE_USD
    cost_fraction = 0.0
    detail_parts: list[str] = []
    if spread is not None:
        spread_cost = max(0.0, spread) * stake
        cost_fraction += spread_cost / stake
        detail_parts.append(f"spread={spread:.4f}")
    if depth_usd is not None and depth_usd > 0:
        depth_penalty = max(0.0, stake - depth_usd) / stake
        cost_fraction += depth_penalty
        detail_parts.append(f"depth_usd={depth_usd:.2f}")
    feasibility = _clamp(1.0 - cost_fraction, 0.0, 1.0)
    return DecisionMetric(
        name="liquidity_cost_feasibility",
        value=feasibility,
        range_low=0.0,
        range_high=1.0,
        method="edge_calc@v1",
        detail=" ".join(detail_parts) or "computed",
    )


def compute_temporal_decay_pressure(
    sources: Sequence[Any],
    market: Any,
    now: datetime | None = None,
) -> DecisionMetric:
    """§3.7 — weighted age of sources, normalized by either the
    market's time-to-resolution (preferred) or by
    ``SOURCE_AGE_REFERENCE`` (fallback). Higher = more decayed.
    """
    if not sources:
        return DecisionMetric(
            name="temporal_decay_pressure",
            value=1.0,
            range_low=0.0,
            range_high=1.0,
            method="retrieval_adapter@v1",
            low_confidence=True,
            detail="no retrieved sources",
        )
    now = _as_utc(now or datetime.now(timezone.utc))
    close = getattr(market, "close_time", None)
    if isinstance(close, datetime):
        horizon = max(timedelta(days=1), _as_utc(close) - now)
    else:
        horizon = SOURCE_AGE_REFERENCE
    ages: list[float] = []
    for source in sources:
        created = _source_created_at(source)
        if created is None:
            continue
        age = (now - created).total_seconds()
        if age < 0:
            age = 0.0
        ages.append(age)
    if not ages:
        return DecisionMetric(
            name="temporal_decay_pressure",
            value=0.5,
            range_low=0.0,
            range_high=1.0,
            method="retrieval_adapter@v1",
            low_confidence=True,
            detail="no source timestamps",
        )
    mean_age_days = (sum(ages) / len(ages)) / 86400.0
    horizon_days = horizon.total_seconds() / 86400.0
    pressure = _clamp(mean_age_days / max(1.0, horizon_days), 0.0, 1.0)
    return DecisionMetric(
        name="temporal_decay_pressure",
        value=pressure,
        range_low=0.0,
        range_high=1.0,
        method="retrieval_adapter@v1",
        detail=f"mean_age_days={mean_age_days:.1f} horizon_days={horizon_days:.1f}",
    )


# ---------------------------------------------------------------------
# Rule graph


def _market_is_closed(market: Any, now: datetime) -> tuple[bool, str]:
    status = _status_value(getattr(market, "status", ""))
    if status and status != "OPEN":
        return True, f"market status={status}"
    close = getattr(market, "close_time", None)
    if isinstance(close, datetime):
        if _as_utc(close) <= now:
            return True, "market.close_time has passed"
    return False, "market is open"


def _position_state(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    return {}


def _stake_recommendation(
    paper_bet: Any,
    edge: DecisionMetric,
    liquidity: DecisionMetric,
) -> float | None:
    if paper_bet is not None:
        stake = getattr(paper_bet, "stake_usd", None)
        if stake is not None:
            try:
                stake_f = float(Decimal(str(stake)))
            except (InvalidOperation, TypeError, ValueError):
                stake_f = None
            if stake_f is not None and stake_f >= MIN_PAPER_STAKE_USD:
                return stake_f
    if liquidity.low_confidence or liquidity.value <= 0:
        return None
    if abs(edge.value) < EDGE_PAPER_THRESHOLD or edge.low_confidence:
        return None
    return DEFAULT_PAPER_STAKE_USD


def evaluate_rules(
    metrics: Sequence[DecisionMetric],
    *,
    market_closed_reason: str | None,
    sources_count: int,
    min_distinct_sources: int,
    position_state: Mapping[str, Any] | None,
    transfer_report: TransferReport | None = None,
) -> tuple[tuple[DecisionRuleResult, ...], MarketDecisionAction, str | None, list[str]]:
    """Evaluate the §2.3 rule graph and return (rules, action, side, reasons).

    Ordering matters: vetoes are evaluated first and short-circuit
    later rules (their ``fired`` is False). Bucket rules then choose
    a candidate action which threshold/combiner rules may downgrade.
    """
    metric_by_name = {m.name: m for m in metrics}
    edge = metric_by_name["market_mispricing_edge"]
    confidence = metric_by_name["calibration_adjusted_confidence"]
    locality = metric_by_name["source_domain_locality"]
    contradiction = metric_by_name["contradiction_pressure"]
    liquidity = metric_by_name["liquidity_cost_feasibility"]
    decay = metric_by_name["temporal_decay_pressure"]

    rules: list[DecisionRuleResult] = []
    reasons: list[str] = []
    veto_hit = False

    # Veto 1: market closed/expired
    rule_closed = DecisionRuleResult(
        name="market_open",
        kind="veto",
        fired=True,
        passed=market_closed_reason is None,
        detail=market_closed_reason or "open",
    )
    rules.append(rule_closed)
    if not rule_closed.passed:
        reasons.append(rule_closed.detail)
        veto_hit = True

    # Veto 2: insufficient distinct sources
    rule_sources = DecisionRuleResult(
        name="distinct_source_floor",
        kind="veto",
        fired=not veto_hit,
        passed=sources_count >= min_distinct_sources,
        detail=f"{sources_count}/{min_distinct_sources} distinct sources",
    )
    rules.append(rule_sources)
    if rule_sources.fired and not rule_sources.passed:
        reasons.append(rule_sources.detail)
        veto_hit = True

    # Veto 3: high contradiction pressure
    rule_contradict = DecisionRuleResult(
        name="contradiction_veto",
        kind="veto",
        fired=not veto_hit,
        passed=contradiction.value < CONTRADICTION_VETO,
        detail=f"contradiction_pressure={contradiction.value:.3f} vs τ={CONTRADICTION_VETO}",
    )
    rules.append(rule_contradict)
    if rule_contradict.fired and not rule_contradict.passed:
        reasons.append(rule_contradict.detail)
        veto_hit = True

    # Veto 4: temporal decay catastrophic
    rule_decay_veto = DecisionRuleResult(
        name="temporal_decay_veto",
        kind="veto",
        fired=not veto_hit,
        passed=decay.value < DECAY_VETO,
        detail=f"temporal_decay_pressure={decay.value:.3f} vs τ={DECAY_VETO}",
    )
    rules.append(rule_decay_veto)
    if rule_decay_veto.fired and not rule_decay_veto.passed:
        reasons.append(rule_decay_veto.detail)
        veto_hit = True

    # Bucket: edge magnitude
    abs_edge = abs(edge.value) if not edge.low_confidence else 0.0
    side = "YES" if edge.value >= 0 else "NO"
    if veto_hit:
        bucket_action = MarketDecisionAction.ABSTAIN
        bucket_detail = "veto upstream → abstain"
        bucket_fired = False
    elif edge.low_confidence:
        bucket_action = MarketDecisionAction.ABSTAIN
        bucket_detail = "edge data missing → abstain"
        bucket_fired = True
    elif abs_edge < EDGE_PAPER_THRESHOLD:
        bucket_action = MarketDecisionAction.WATCH
        bucket_detail = f"|edge|={abs_edge:.3f} below paper threshold {EDGE_PAPER_THRESHOLD}"
        bucket_fired = True
    elif abs_edge < EDGE_LIVE_THRESHOLD:
        bucket_action = MarketDecisionAction.PAPER_TRADE
        bucket_detail = (
            f"|edge|={abs_edge:.3f} clears paper, below live threshold {EDGE_LIVE_THRESHOLD}"
        )
        bucket_fired = True
    else:
        bucket_action = MarketDecisionAction.LIVE_CANDIDATE
        bucket_detail = f"|edge|={abs_edge:.3f} clears live threshold {EDGE_LIVE_THRESHOLD}"
        bucket_fired = True
    rules.append(
        DecisionRuleResult(
            name="edge_bucket",
            kind="bucket",
            fired=bucket_fired,
            passed=bucket_fired,
            detail=bucket_detail,
        )
    )

    # Liquidity gate (downgrades LIVE_CANDIDATE → PAPER_TRADE,
    # downgrades PAPER_TRADE → WATCH when liquidity is zero).
    liquidity_ok = liquidity.value >= LIQUIDITY_LIVE_THRESHOLD and not liquidity.low_confidence
    rule_liquidity = DecisionRuleResult(
        name="liquidity_threshold",
        kind="threshold",
        fired=not veto_hit,
        passed=liquidity_ok,
        detail=f"liquidity_cost_feasibility={liquidity.value:.3f} vs τ={LIQUIDITY_LIVE_THRESHOLD}",
    )
    rules.append(rule_liquidity)
    if rule_liquidity.fired:
        if liquidity.value <= 0.0 and not liquidity.low_confidence:
            if bucket_action in (MarketDecisionAction.PAPER_TRADE, MarketDecisionAction.LIVE_CANDIDATE):
                reasons.append("liquidity collapsed → watch")
                bucket_action = MarketDecisionAction.WATCH
        elif not liquidity_ok and bucket_action == MarketDecisionAction.LIVE_CANDIDATE:
            reasons.append("liquidity below live threshold → paper")
            bucket_action = MarketDecisionAction.PAPER_TRADE

    # Confidence/locality gate for live escalation only.
    confidence_ok = (
        confidence.value >= CONFIDENCE_LIVE_THRESHOLD and not confidence.low_confidence
    )
    locality_ok = locality.value >= LOCALITY_LIVE_THRESHOLD and not locality.low_confidence
    rule_conf = DecisionRuleResult(
        name="confidence_threshold",
        kind="threshold",
        fired=not veto_hit,
        passed=confidence_ok,
        detail=(
            f"calibration_adjusted_confidence={confidence.value:.3f} vs τ={CONFIDENCE_LIVE_THRESHOLD}"
            + (" (low_confidence)" if confidence.low_confidence else "")
        ),
    )
    rule_locality = DecisionRuleResult(
        name="locality_threshold",
        kind="threshold",
        fired=not veto_hit,
        passed=locality_ok,
        detail=(
            f"source_domain_locality={locality.value:.3f} vs τ={LOCALITY_LIVE_THRESHOLD}"
            + (" (low_confidence)" if locality.low_confidence else "")
        ),
    )
    rules.append(rule_conf)
    rules.append(rule_locality)
    if bucket_action == MarketDecisionAction.LIVE_CANDIDATE:
        if not (confidence_ok and locality_ok):
            reasons.append("confidence or locality below live thresholds → paper")
            bucket_action = MarketDecisionAction.PAPER_TRADE

    # Moderate decay downgrade
    if decay.value >= DECAY_DOWNGRADE and bucket_action in (
        MarketDecisionAction.PAPER_TRADE,
        MarketDecisionAction.LIVE_CANDIDATE,
    ):
        reasons.append(
            f"temporal_decay_pressure={decay.value:.3f} ≥ {DECAY_DOWNGRADE} → watch"
        )
        bucket_action = MarketDecisionAction.WATCH

    # Position-state overlays. v1 only emits REDUCE/EXIT when the
    # caller declares an open position whose side disagrees with the
    # current edge or whose underlying principle is revoked.
    state = _position_state(position_state)
    if state:
        open_side = str(state.get("open_side", "") or "").upper()
        revoked = bool(state.get("principles_revoked", False))
        position_action: MarketDecisionAction | None = None
        position_detail = ""
        if revoked:
            position_action = MarketDecisionAction.EXIT
            position_detail = "an active principle was revoked → exit"
        elif open_side and open_side != side and not edge.low_confidence:
            position_action = MarketDecisionAction.REDUCE
            position_detail = (
                f"existing {open_side} position vs edge side {side} → reduce"
            )
        rules.append(
            DecisionRuleResult(
                name="position_overlay",
                kind="combiner",
                fired=True,
                passed=position_action is not None,
                detail=position_detail or "no overlay applied",
            )
        )
        if position_action is not None:
            reasons.append(position_detail)
            bucket_action = position_action

    # Analogical transfer overlay. The §1 (Algorithmized Decision
    # Making) contract is explicit that analogy must not act as proof:
    # the transfer report can only *downgrade* a decision, never
    # escalate one. A best stance of ``DOES_NOT_APPLY`` (a principle
    # the engine entertained then explicitly rejected for this case)
    # forces ABSTAIN; ``WATCH`` or ``ABSTAIN`` downgrades a
    # paper/live action accordingly; ``APPLIES`` leaves bucket_action
    # unchanged. Revocation/EXIT from the position overlay above
    # already trumps this — we only act when no position overlay
    # already decided.
    if transfer_report is not None and bucket_action not in (
        MarketDecisionAction.EXIT,
        MarketDecisionAction.REDUCE,
    ):
        best_stance = transfer_report.best_stance
        rec_count = len(transfer_report.recommendations)
        transfer_detail = (
            f"best_stance={best_stance} principle={transfer_report.best_principle_id}"
            f" recs={rec_count}"
        )
        transfer_action: MarketDecisionAction | None = None
        if best_stance == TransferStance.DOES_NOT_APPLY:
            transfer_action = MarketDecisionAction.ABSTAIN
        elif (
            best_stance in (TransferStance.WATCH, TransferStance.ABSTAIN)
            and bucket_action
            in (MarketDecisionAction.PAPER_TRADE, MarketDecisionAction.LIVE_CANDIDATE)
        ):
            transfer_action = MarketDecisionAction.WATCH
        rules.append(
            DecisionRuleResult(
                name="analogical_transfer",
                kind="combiner",
                fired=True,
                passed=transfer_action is None,
                detail=transfer_detail,
            )
        )
        if transfer_action is not None:
            reasons.append(
                f"analogical transfer best stance={best_stance} → "
                f"{transfer_action.value.lower()}"
            )
            bucket_action = transfer_action

    if bucket_action == MarketDecisionAction.ABSTAIN and not reasons:
        reasons.append("rule graph produced no actionable decision")
    if bucket_action in (MarketDecisionAction.ABSTAIN,) or veto_hit:
        side_out = None
    else:
        side_out = side
    return tuple(rules), bucket_action, side_out, reasons


def build_decision_trace(
    *,
    market: Any,
    sources: Sequence[Any],
    citations: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    paper_bet: Any | None = None,
    calibration_state: Mapping[str, Any] | None = None,
    extra_contradictions: Sequence[Mapping[str, Any]] = (),
    position_state: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    min_distinct_sources: int = 3,
    transfer_report: TransferReport | None = None,
    incentive_signals: Sequence[str] = (),
    coordination_signals: Sequence[str] = (),
    reflexive_signals: Sequence[str] = (),
) -> MarketDecisionTrace:
    """Assemble metrics, evaluate the rule graph, return a trace.

    The trace's ``confidence`` is the geometric mean of the
    calibration-adjusted confidence and ``(1 - contradiction_pressure)``,
    pulled down by ``low_confidence`` metrics so missing data is
    visible in the scalar that the UI surfaces.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    probability_yes = payload.get("probability_yes")
    market_yes_price = getattr(market, "current_yes_price", None)

    edge_metric = compute_market_mispricing_edge(probability_yes, market_yes_price)
    confidence_metric = compute_calibration_adjusted_confidence(
        payload.get("confidence_low"),
        payload.get("confidence_high"),
        calibration_state,
        topic_hint=str(payload.get("topic_hint") or "").strip() or None,
    )
    locality_metric = compute_source_domain_locality(sources, citations, market)
    contradiction_metric = compute_contradiction_pressure(citations, extra_contradictions)
    decay_metric = compute_temporal_decay_pressure(sources, market, now=now)

    suggested_stake: float | None = None
    if paper_bet is not None:
        raw_stake = getattr(paper_bet, "stake_usd", None)
        if raw_stake is not None:
            try:
                suggested_stake = float(Decimal(str(raw_stake)))
            except (InvalidOperation, TypeError, ValueError):
                suggested_stake = None
    liquidity_metric = compute_liquidity_cost_feasibility(market, suggested_stake)

    metrics: tuple[DecisionMetric, ...] = (
        edge_metric,
        confidence_metric,
        locality_metric,
        contradiction_metric,
        liquidity_metric,
        decay_metric,
    )

    closed, closed_reason = _market_is_closed(market, now)
    rules, action, side, reasons = evaluate_rules(
        metrics,
        market_closed_reason=closed_reason if closed else None,
        sources_count=len(sources),
        min_distinct_sources=min_distinct_sources,
        position_state=position_state,
        transfer_report=transfer_report,
    )

    confidence_components = [
        confidence_metric.value if not confidence_metric.low_confidence else max(0.0, confidence_metric.value * 0.5),
        max(0.0, 1.0 - contradiction_metric.value),
    ]
    confidence_scalar = (confidence_components[0] * confidence_components[1]) ** 0.5
    low_conf_penalty = 0.5 if any(m.low_confidence for m in metrics) else 1.0
    confidence_scalar = _clamp(confidence_scalar * low_conf_penalty, 0.0, 1.0)
    if action == MarketDecisionAction.ABSTAIN:
        confidence_scalar = min(confidence_scalar, 0.25)

    # Multi-frame engine. Frames receive the metric outputs and the
    # transfer report; the synthesis combines their verdicts via the
    # explicit rule in :mod:`noosphere.decisions.synthesis`. Frames may
    # *downgrade* the action when a HARD_STOP fires for a signal the
    # rule graph above does not already cover (e.g. caller-supplied
    # incentive_signals). They never escalate.
    frame_ctx = context_from_decision_metrics(
        side=side,
        metrics=metrics,
        transfer_report=transfer_report,
        position_state=position_state,
        incentive_signals=incentive_signals,
        coordination_signals=coordination_signals,
        reflexive_signals=reflexive_signals,
        market_closed=closed,
    )
    frame_results = run_frames(frame_ctx)
    synthesis = synthesize(frame_results, default_side=side)

    if (
        synthesis.action == SynthesisAction.ABSTAIN
        and synthesis.hard_stop_frames
        and action in (MarketDecisionAction.PAPER_TRADE, MarketDecisionAction.LIVE_CANDIDATE)
    ):
        reasons.append(
            "multi-frame synthesis HARD_STOP from "
            + ", ".join(synthesis.hard_stop_frames)
            + " → abstain"
        )
        action = MarketDecisionAction.ABSTAIN
        side = None
    elif (
        synthesis.action == SynthesisAction.EXIT
        and action != MarketDecisionAction.ABSTAIN
    ):
        # An EXIT signal from a frame supersedes paper/live bucket
        # actions (the principal-agent frame raises EXIT on a revoked
        # principle; the rule-graph position overlay does the same,
        # so this branch is just defense-in-depth).
        if action != MarketDecisionAction.EXIT:
            reasons.append("multi-frame synthesis → exit overrides bucket action")
        action = MarketDecisionAction.EXIT
        side = None

    stake_recommendation = _stake_recommendation(paper_bet, edge_metric, liquidity_metric)
    if action not in (MarketDecisionAction.PAPER_TRADE, MarketDecisionAction.LIVE_CANDIDATE):
        stake_recommendation = None

    return MarketDecisionTrace(
        action=action,
        side=side,
        confidence=confidence_scalar,
        stake_recommendation_usd=stake_recommendation,
        metrics=metrics,
        rules=rules,
        reasons=tuple(reasons),
        transfer_report=transfer_report,
        frames=frame_results,
        synthesis=synthesis,
    )


def decision_trace_to_dict(trace: MarketDecisionTrace) -> dict[str, Any]:
    """Public stable JSON shape for UI/API consumption."""
    return trace.to_dict()


def decision_trace_gate_entries(trace: MarketDecisionTrace) -> list[dict[str, Any]]:
    """Render the rule-graph firings in the legacy ``gate_results`` shape.

    The forecast_generator already persists a ``gate_results`` list with
    ``gateName/passed/reason`` keys; the rule graph's threshold/veto
    nodes naturally project onto the same shape so downstream
    consumers (operator page, e2e tests) keep working without a
    schema migration.
    """
    return [
        {
            "gateName": rule.name,
            "passed": bool(rule.passed),
            "reason": rule.detail,
        }
        for rule in trace.rules
        if rule.fired
    ]


__all__ = [
    "DecisionMetric",
    "DecisionRuleResult",
    "MarketDecisionAction",
    "MarketDecisionTrace",
    "TRACE_VERSION",
    "build_decision_trace",
    "compute_calibration_adjusted_confidence",
    "compute_contradiction_pressure",
    "compute_liquidity_cost_feasibility",
    "compute_market_mispricing_edge",
    "compute_source_domain_locality",
    "compute_temporal_decay_pressure",
    "decision_trace_gate_entries",
    "decision_trace_to_dict",
    "evaluate_rules",
]
