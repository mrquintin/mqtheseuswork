"""Analogical transfer engine — apply abstract principles to a new situation.

Given a new event/market/case, this module asks: which of our recorded
:class:`AbstractPrinciple` instances plausibly apply, which of their
preconditions are satisfied, which failure conditions are tripped, and
which prior cases are *structurally* analogous (not merely
keyword-similar). The output is a typed :class:`TransferReport` whose
:class:`TransferRecommendation` rows are reproducible from the inputs
alone — no LLM calls, no randomness — so a forecast decision trace can
quote them by id.

What the engine deliberately does *not* do:

- **Promote analogy to proof.** A recommendation with stance
  ``APPLIES`` is a hypothesis with a defensible bracket, never a
  conclusion. Downstream callers (e.g. :mod:`noosphere.forecasts.
  decision_metrics`) consume the report as one input among several;
  they do not let any single recommendation force a decision past
  ``PAPER_TRADE`` unless the rule graph already had grounds.
- **Cluster by keyword.** Token Jaccard is one of several axes; we
  separately score precondition coverage, mechanism match, and
  failure-signal presence. A passage that *says* "regulatory capture"
  without describing the mechanism scores poorly on mechanism_match
  even if it shares vocabulary with a hundred prior cases.
- **Let a single case dominate.** The aggregator weighs the *median*
  closest case alongside the single closest, and a recommendation's
  confidence is pulled down whenever fewer than two supporting cases
  reach a structural-fit floor.

The metrics catalog is intentionally aligned with — but distinct from —
``noosphere.forecasts.decision_metrics``. Decision metrics are about
the *market* (edge, liquidity, calibration); transfer metrics are
about the *principle's applicability to the new situation*. Both feed
the same trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from noosphere.cases.models import EmpiricalCaseStudy
from noosphere.principles.models import (
    AbstractPrinciple,
    PrincipleConfidence,
    PrincipleStatus,
    TransferGraph,
)


TRANSFER_VERSION = "analogical_transfer@v1"


# Thresholds. Tuned to be conservative: a principle has to *clearly*
# fit before it earns ``APPLIES``, and a single contradiction signal is
# enough to drop it to ``DOES_NOT_APPLY``.
APPLIES_FIT_FLOOR = 0.45
WATCH_FIT_FLOOR = 0.20
MISSING_PRECONDITION_FLOOR = 0.50
CONTRADICTION_DROP_FLOOR = 0.50
CASE_DISTANCE_WATCH = 0.80
DOMAIN_SHIFT_WATCH = 0.70
MECHANISM_MATCH_FLOOR = 0.10
MIN_CLOSE_CASES = 2
DEFAULT_TIME_DECAY_REFERENCE_DAYS = 18 * 31


# A small stop list for token comparison. Without this, "the", "with",
# "for", and other ≥3-char function words inflate Jaccard scores so
# that superficially similar text scores higher than structurally
# similar text. The list is deliberately tiny — domain-specific
# stopwording belongs upstream.
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "will",
        "would",
        "could",
        "should",
        "into",
        "onto",
        "over",
        "under",
        "than",
        "then",
        "but",
        "not",
        "any",
        "all",
        "some",
        "such",
        "their",
        "there",
        "where",
        "when",
        "what",
        "which",
        "while",
        "about",
        "between",
        "across",
        "after",
        "before",
        "because",
        "been",
        "being",
        "they",
        "them",
        "its",
        "his",
        "her",
        "our",
        "your",
    }
)


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        out: set[str] = set()
        for item in value:
            out |= _tokens(item)
        return out
    text = str(value)
    pieces = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    return {token for token in pieces if len(token) >= 3 and token not in _STOPWORDS}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _overlap_coefficient(left: set[str], right: set[str]) -> float:
    """Symmetric overlap normalized by the smaller set.

    Jaccard punishes large token bags that share a meaningful core,
    which is the wrong signal when comparing case-token bags (rich on
    one side, sparse on the other). Overlap coefficient asks
    "how much of the smaller bag is shared?", which is closer to what
    structural similarity means here. Used for case-bag-against-bag
    comparison; precondition / mechanism comparisons keep using
    Jaccard since both sides are small and targeted.
    """

    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _confidence_to_scalar(band: Any) -> float:
    name = getattr(band, "value", band)
    if name == PrincipleConfidence.HIGH.value:
        return 1.0
    if name == PrincipleConfidence.MODERATE.value:
        return 0.65
    return 0.35


# ── Inputs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransferQuery:
    """Description of a new situation against which principles are tested.

    Only ``case_id`` and a usable text (any of ``title``, ``mechanism``,
    ``outcome_question``, ``source_text``) are required. Empty fields
    are treated as missing, not falsified — the engine reports
    ``low_confidence`` rather than scoring against absent data.
    """

    case_id: str
    title: str = ""
    domain: str = ""
    actors: tuple[str, ...] = ()
    institutions: tuple[str, ...] = ()
    mechanism: str = ""
    preconditions_present: tuple[str, ...] = ()
    preconditions_absent: tuple[str, ...] = ()
    failure_signals_present: tuple[str, ...] = ()
    outcome_question: str = ""
    time_horizon_days: int | None = None
    source_text: str = ""
    observed_at: datetime | None = None

    def all_text(self) -> str:
        parts = [
            self.title,
            self.mechanism,
            self.outcome_question,
            self.source_text,
            " ".join(self.actors),
            " ".join(self.institutions),
            " ".join(self.preconditions_present),
            " ".join(self.failure_signals_present),
        ]
        return " ".join(p for p in parts if p)


@dataclass(frozen=True)
class TransferMetric:
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


class TransferStance(str):
    """String constants for stance values.

    Kept as plain strings (not :class:`Enum`) so a recommendation
    serializes byte-identically across processes without enum
    representation drift.
    """

    APPLIES = "APPLIES"
    WATCH = "WATCH"
    ABSTAIN = "ABSTAIN"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"


_STANCE_RANK = {
    TransferStance.DOES_NOT_APPLY: 0,
    TransferStance.ABSTAIN: 1,
    TransferStance.WATCH: 2,
    TransferStance.APPLIES: 3,
}


@dataclass(frozen=True)
class TransferRecommendation:
    principle_id: str
    canonical_statement: str
    stance: str
    confidence: float
    closest_case_ids: tuple[str, ...]
    metrics: tuple[TransferMetric, ...]
    reasons: tuple[str, ...]

    def metric(self, name: str) -> TransferMetric | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "canonical_statement": self.canonical_statement,
            "stance": self.stance,
            "confidence": round(float(self.confidence), 6),
            "closest_case_ids": list(self.closest_case_ids),
            "metrics": [m.to_dict() for m in self.metrics],
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class TransferReport:
    query_case_id: str
    recommendations: tuple[TransferRecommendation, ...]
    summary_metrics: tuple[TransferMetric, ...]
    best_principle_id: str | None
    best_stance: str
    trace_version: str = TRANSFER_VERSION

    def recommendation(self, principle_id: str) -> TransferRecommendation | None:
        for rec in self.recommendations:
            if rec.principle_id == principle_id:
                return rec
        return None

    def summary(self, name: str) -> TransferMetric | None:
        for m in self.summary_metrics:
            if m.name == name:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_case_id": self.query_case_id,
            "best_principle_id": self.best_principle_id,
            "best_stance": self.best_stance,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "summary_metrics": [m.to_dict() for m in self.summary_metrics],
            "trace_version": self.trace_version,
        }


# ── Per-pair scoring ────────────────────────────────────────────────────────


def _structural_fit(
    query: TransferQuery,
    principle: AbstractPrinciple,
    *,
    mechanism_score: float,
) -> TransferMetric:
    """Composite of precondition coverage, mechanism match (computed
    upstream against supporting cases), and outcome alignment.

    Preconditions and outcomes are scored with Jaccard against the
    principle's own targeted fields; mechanism is supplied by the
    caller so the same case-aware mechanism scoring used elsewhere
    in the report is what feeds the fit axis. This avoids penalizing
    a principle whose terse one-line ``mechanism`` text happens not
    to share vocabulary with the query when the supporting cases'
    mechanisms clearly do.
    """

    query_text = _tokens(query.all_text())
    pre_terms = _tokens(principle.preconditions)
    out_terms = _tokens(principle.expected_outcomes)

    pre_score = _jaccard(_tokens(query.preconditions_present), pre_terms) if pre_terms else 0.0
    if pre_terms and not query.preconditions_present:
        pre_score = max(pre_score, _jaccard(query_text, pre_terms) * 0.5)
    out_score = (
        _overlap_coefficient(_tokens(query.outcome_question) or query_text, out_terms)
        if out_terms
        else 0.0
    )

    components = (pre_score, mechanism_score, out_score)
    if all(c == 0.0 for c in components):
        return TransferMetric(
            name="structural_fit",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="no structural overlap on preconditions, mechanism, or outcome",
        )

    weights = (0.45, 0.4, 0.15)
    weighted = sum(w * v for w, v in zip(weights, components))
    return TransferMetric(
        name="structural_fit",
        value=_clamp(weighted, 0.0, 1.0),
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=(
            f"pre={pre_score:.3f} mech={mechanism_score:.3f} outcome={out_score:.3f}"
        ),
    )


def _missing_preconditions(
    query: TransferQuery,
    principle: AbstractPrinciple,
) -> TransferMetric:
    """Fraction of recorded preconditions whose tokens are *not* present
    in the query's stated preconditions or surrounding text.
    """

    if not principle.preconditions:
        return TransferMetric(
            name="missing_preconditions",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="principle has no stated preconditions",
        )
    haystack = _tokens(query.preconditions_present) | _tokens(query.all_text())
    missing = 0
    for pre in principle.preconditions:
        terms = _tokens(pre)
        if not terms:
            continue
        if not (terms & haystack):
            missing += 1
    fraction = missing / len(principle.preconditions)
    return TransferMetric(
        name="missing_preconditions",
        value=_clamp(fraction, 0.0, 1.0),
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=f"{missing}/{len(principle.preconditions)} preconditions unmatched",
    )


def _contradiction_risk(
    query: TransferQuery,
    principle: AbstractPrinciple,
) -> TransferMetric:
    """Fraction of failure conditions whose detectable signal appears
    in the query, plus a boost when a negation candidate's tokens are
    densely present in the query text.
    """

    fc = principle.failure_conditions
    nc = principle.negation_candidates
    if not fc and not nc:
        return TransferMetric(
            name="contradiction_risk",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="principle has no failure_conditions or negation_candidates",
        )

    # Baseline tokens describe the *principle itself*; they appear in
    # failure-condition descriptions only as context. We strip them so
    # the test asks "are the failure-specific tokens present?" rather
    # than "does the failure description share any vocabulary with
    # the query?".
    baseline = (
        _tokens(principle.preconditions)
        | _tokens(principle.mechanism)
        | _tokens(principle.expected_outcomes)
        | _tokens(principle.domain)
    )
    explicit_signals = _tokens(query.failure_signals_present) | _tokens(
        query.preconditions_absent
    )
    text_signals = _tokens(query.all_text())
    fc_hits = 0
    for cond in fc:
        signal_terms = _tokens(cond.detectable_signal) - baseline
        desc_terms = _tokens(cond.description) - baseline
        # An explicit failure signal is a strong contradiction: even
        # a single specific match counts. Inferring contradiction from
        # ambient text requires a denser overlap so a stray word in
        # a long passage doesn't trigger the veto.
        if signal_terms and (signal_terms & explicit_signals):
            fc_hits += 1
            continue
        novel = signal_terms | desc_terms
        if not novel:
            continue
        overlap = novel & text_signals
        if len(overlap) >= 2 or (overlap and len(novel) <= 3):
            fc_hits += 1
    fc_fraction = (fc_hits / len(fc)) if fc else 0.0

    nc_score = 0.0
    if nc:
        nc_terms: set[str] = set()
        for n in nc:
            nc_terms |= _tokens(n.statement)
        nc_specific = nc_terms - baseline
        if nc_specific:
            nc_score = _jaccard(nc_specific, text_signals)

    value = _clamp(max(fc_fraction, nc_score), 0.0, 1.0)
    return TransferMetric(
        name="contradiction_risk",
        value=value,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=(
            f"failure_hits={fc_hits}/{len(fc) if fc else 0} "
            f"negation_jaccard={nc_score:.3f}"
        ),
    )


def _case_token_bag(case: EmpiricalCaseStudy) -> set[str]:
    return (
        _tokens(case.observed_mechanism)
        | _tokens(case.outcome)
        | _tokens(case.actors)
        | _tokens(case.institutions)
        | _tokens(case.stated_causal_claim)
        | _tokens(case.title)
        | _tokens(case.domain)
    )


def _case_distance_and_mechanism(
    query: TransferQuery,
    principle: AbstractPrinciple,
    cases_by_id: Mapping[str, EmpiricalCaseStudy],
) -> tuple[TransferMetric, TransferMetric, tuple[str, ...]]:
    """Closest-case distance + mechanism match, plus the case ids that
    contributed to the closest scores.

    Returns three things in one pass to avoid re-walking the supporting
    case list.
    """

    supporting_ids = list(principle.supporting_case_ids)
    bounding_ids = list(principle.bounding_case_ids)
    contradicting_ids = list(principle.contradicting_case_ids)
    relevant_ids = supporting_ids + bounding_ids + contradicting_ids

    query_bag = _tokens(query.all_text())
    query_mech = _tokens(query.mechanism) or query_bag

    similarities: list[tuple[str, float, float]] = []  # (case_id, structural_sim, mech_sim)
    for cid in relevant_ids:
        case = cases_by_id.get(cid)
        if case is None:
            continue
        case_bag = _case_token_bag(case)
        structural = _overlap_coefficient(query_bag, case_bag)
        mech_sim = _overlap_coefficient(query_mech, _tokens(case.observed_mechanism))
        similarities.append((cid, structural, mech_sim))

    if not similarities:
        distance = TransferMetric(
            name="case_distance",
            value=1.0,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="no supporting / bounding / contradicting cases available",
        )
        mechanism = TransferMetric(
            name="mechanism_match",
            value=_overlap_coefficient(query_mech, _tokens(principle.mechanism)),
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="no case-level mechanism evidence; using principle.mechanism",
        )
        return distance, mechanism, ()

    similarities.sort(key=lambda triple: triple[1], reverse=True)
    structural_scores = [s for _, s, _ in similarities]
    mech_scores = [m for _, _, m in similarities]
    closest_struct = structural_scores[0]
    median_struct = median(structural_scores)
    closest_ids = tuple(cid for cid, s, _ in similarities[: min(3, len(similarities))])

    distance_value = _clamp(1.0 - ((closest_struct + median_struct) / 2.0), 0.0, 1.0)
    distance = TransferMetric(
        name="case_distance",
        value=distance_value,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=f"closest={closest_struct:.3f} median={median_struct:.3f} n={len(similarities)}",
    )

    mech_principle = _overlap_coefficient(query_mech, _tokens(principle.mechanism))
    mech_value = _clamp(max(max(mech_scores), mech_principle), 0.0, 1.0)
    mechanism = TransferMetric(
        name="mechanism_match",
        value=mech_value,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=(
            f"max_case_mech={max(mech_scores):.3f} principle_mech={mech_principle:.3f}"
        ),
    )
    return distance, mechanism, closest_ids


def _domain_shift(
    query: TransferQuery,
    principle: AbstractPrinciple,
) -> TransferMetric:
    """0 if the query domain matches the principle's domain or scope;
    1 if no overlap; intermediate if the principle has broad scope but
    no exact match.
    """

    q_domain = (query.domain or "").strip().lower()
    p_domain = (principle.domain or "").strip().lower()
    scope_terms = {s.strip().lower() for s in principle.scope if s}

    if not q_domain and not p_domain and not scope_terms:
        return TransferMetric(
            name="domain_shift",
            value=0.5,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="neither query nor principle declares a domain",
        )
    if not q_domain:
        return TransferMetric(
            name="domain_shift",
            value=0.6,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=True,
            detail="query has no declared domain",
        )

    if q_domain == p_domain or q_domain in scope_terms:
        return TransferMetric(
            name="domain_shift",
            value=0.0,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            detail=f"query domain {q_domain!r} matches principle scope",
        )
    if any(q_domain in s or s in q_domain for s in {p_domain} | scope_terms if s):
        return TransferMetric(
            name="domain_shift",
            value=0.4,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            detail=f"partial domain overlap with scope={sorted(scope_terms)}",
        )
    return TransferMetric(
        name="domain_shift",
        value=1.0,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=(
            f"query domain {q_domain!r} not in principle.domain={p_domain!r} "
            f"or scope={sorted(scope_terms)}"
        ),
    )


def _time_decay_risk(
    query: TransferQuery,
    principle: AbstractPrinciple,
    *,
    now: datetime,
    case_dates: Mapping[str, datetime] | None,
    reference_days: int,
) -> TransferMetric:
    """Older supporting cases → higher decay risk. ``case_dates`` is
    an optional caller-supplied map of case_id → observation date; when
    absent we fall back to the principle's status (a ``BOUNDED`` or
    ``CONTRADICTED`` principle implies the recorded scope has already
    drifted, which is itself a decay signal).
    """

    supporting = list(principle.supporting_case_ids)
    if case_dates and supporting:
        ages = []
        for cid in supporting:
            date = case_dates.get(cid)
            if date is None:
                continue
            ages.append(max(0.0, (now - _as_utc(date)).total_seconds() / 86400.0))
        if ages:
            mean_age = sum(ages) / len(ages)
            value = _clamp(mean_age / max(1.0, float(reference_days)), 0.0, 1.0)
            return TransferMetric(
                name="time_decay_risk",
                value=value,
                range_low=0.0,
                range_high=1.0,
                method=TRANSFER_VERSION,
                detail=f"mean_supporting_age_days={mean_age:.1f} ref={reference_days}d",
            )

    status = getattr(principle.status, "value", principle.status)
    if status == PrincipleStatus.CONTRADICTED.value:
        return TransferMetric(
            name="time_decay_risk",
            value=0.8,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            detail="principle status=CONTRADICTED",
        )
    if status == PrincipleStatus.BOUNDED.value:
        return TransferMetric(
            name="time_decay_risk",
            value=0.5,
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            detail="principle status=BOUNDED — scope drift recorded",
        )
    return TransferMetric(
        name="time_decay_risk",
        value=0.3,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        low_confidence=True,
        detail="no case dates supplied; using neutral prior",
    )


def _outcome_uncertainty(
    principle: AbstractPrinciple,
    contradiction: TransferMetric,
    missing_pre: TransferMetric,
) -> TransferMetric:
    """1 − (principle calibration × precondition coverage), bumped by
    contradiction risk. The calibration is the principle's recorded
    confidence band — it caps how confident *any* transfer recommendation
    can be even when the structural axes align.
    """

    cal = principle.confidence
    cal_score = float(getattr(cal, "score", 0.0) or 0.0)
    band_scalar = _confidence_to_scalar(getattr(cal, "band", None))
    base_conf = max(cal_score, band_scalar * 0.5)
    pre_coverage = 1.0 - missing_pre.value if not missing_pre.low_confidence else 0.5
    grounded = base_conf * pre_coverage
    uncertainty = _clamp(1.0 - grounded + 0.5 * contradiction.value, 0.0, 1.0)
    return TransferMetric(
        name="outcome_uncertainty",
        value=uncertainty,
        range_low=0.0,
        range_high=1.0,
        method=TRANSFER_VERSION,
        detail=(
            f"calibration_score={cal_score:.3f} band_scalar={band_scalar:.3f} "
            f"pre_coverage={pre_coverage:.3f}"
        ),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ── Recommendation builder ──────────────────────────────────────────────────


def _decide_stance(
    fit: TransferMetric,
    missing: TransferMetric,
    contradiction: TransferMetric,
    case_distance: TransferMetric,
    domain_shift: TransferMetric,
    mechanism: TransferMetric,
    close_case_count: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if contradiction.value >= CONTRADICTION_DROP_FLOOR and not contradiction.low_confidence:
        reasons.append(
            f"contradiction_risk={contradiction.value:.3f} ≥ {CONTRADICTION_DROP_FLOOR}"
        )
        return TransferStance.DOES_NOT_APPLY, reasons
    if (
        missing.value >= MISSING_PRECONDITION_FLOOR
        and not missing.low_confidence
    ):
        reasons.append(
            f"missing_preconditions={missing.value:.3f} ≥ {MISSING_PRECONDITION_FLOOR}"
        )
        return TransferStance.ABSTAIN, reasons
    if fit.value < WATCH_FIT_FLOOR or mechanism.value < MECHANISM_MATCH_FLOOR:
        reasons.append(
            f"structural_fit={fit.value:.3f} mech_match={mechanism.value:.3f} below floor"
        )
        return TransferStance.WATCH, reasons
    if (
        case_distance.value >= CASE_DISTANCE_WATCH
        or close_case_count < MIN_CLOSE_CASES
    ):
        reasons.append(
            f"case_distance={case_distance.value:.3f} or close_cases={close_case_count} insufficient"
        )
        return TransferStance.WATCH, reasons
    if domain_shift.value >= DOMAIN_SHIFT_WATCH and not domain_shift.low_confidence:
        reasons.append(
            f"domain_shift={domain_shift.value:.3f} ≥ {DOMAIN_SHIFT_WATCH} — structural match in a different domain"
        )
        return TransferStance.WATCH, reasons
    if fit.value < APPLIES_FIT_FLOOR:
        reasons.append(
            f"structural_fit={fit.value:.3f} below APPLIES floor {APPLIES_FIT_FLOOR}"
        )
        return TransferStance.WATCH, reasons
    reasons.append(
        f"fit={fit.value:.3f} mech={mechanism.value:.3f} "
        f"contradiction={contradiction.value:.3f}"
    )
    return TransferStance.APPLIES, reasons


def _recommendation_confidence(
    fit: TransferMetric,
    mechanism: TransferMetric,
    case_distance: TransferMetric,
    contradiction: TransferMetric,
    outcome_uncertainty: TransferMetric,
    principle: AbstractPrinciple,
) -> float:
    structural = (fit.value + mechanism.value + (1.0 - case_distance.value)) / 3.0
    risk_penalty = (contradiction.value + outcome_uncertainty.value) / 2.0
    calibration = float(getattr(principle.confidence, "score", 0.0) or 0.0)
    raw = max(0.0, structural - 0.5 * risk_penalty) * (0.5 + 0.5 * calibration)
    return _clamp(raw, 0.0, 1.0)


def _score_principle(
    query: TransferQuery,
    principle: AbstractPrinciple,
    *,
    cases_by_id: Mapping[str, EmpiricalCaseStudy],
    now: datetime,
    case_dates: Mapping[str, datetime] | None,
    reference_days: int,
) -> TransferRecommendation:
    distance, mechanism, closest_ids = _case_distance_and_mechanism(
        query, principle, cases_by_id
    )
    fit = _structural_fit(query, principle, mechanism_score=mechanism.value)
    missing = _missing_preconditions(query, principle)
    contradiction = _contradiction_risk(query, principle)
    shift = _domain_shift(query, principle)
    decay = _time_decay_risk(
        query,
        principle,
        now=now,
        case_dates=case_dates,
        reference_days=reference_days,
    )
    outcome = _outcome_uncertainty(principle, contradiction, missing)

    # Close-case count: supporting cases whose structural similarity to
    # the query was above an explicit floor. We require at least two
    # such cases before APPLIES is reachable — a single match cannot
    # carry the stance.
    close_count = 0
    query_bag_text = _tokens(query.all_text())
    for cid in principle.supporting_case_ids:
        case = cases_by_id.get(cid)
        if case is None:
            continue
        if _overlap_coefficient(query_bag_text, _case_token_bag(case)) >= 0.15:
            close_count += 1

    stance, reasons = _decide_stance(
        fit,
        missing,
        contradiction,
        distance,
        shift,
        mechanism,
        close_count,
    )
    confidence = _recommendation_confidence(fit, mechanism, distance, contradiction, outcome, principle)

    metrics = (fit, missing, contradiction, distance, shift, decay, mechanism, outcome)
    return TransferRecommendation(
        principle_id=principle.id,
        canonical_statement=principle.canonical_statement,
        stance=stance,
        confidence=confidence,
        closest_case_ids=closest_ids,
        metrics=metrics,
        reasons=tuple(reasons),
    )


# ── Public engine ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransferEngineConfig:
    reference_decay_days: int = DEFAULT_TIME_DECAY_REFERENCE_DAYS
    top_k_recommendations: int = 5


def evaluate_transfer(
    *,
    query: TransferQuery,
    principles: Sequence[AbstractPrinciple] | TransferGraph,
    cases: Sequence[EmpiricalCaseStudy] = (),
    case_dates: Mapping[str, datetime] | None = None,
    now: datetime | None = None,
    config: TransferEngineConfig | None = None,
) -> TransferReport:
    """Score every candidate principle against ``query`` and assemble a report.

    The engine never raises on missing data — principles without
    enough substrate yield ``WATCH`` or ``ABSTAIN`` recommendations
    with the relevant metrics flagged ``low_confidence``. Callers can
    therefore drop the report into a decision trace without defensive
    branches.
    """

    cfg = config or TransferEngineConfig()
    now = _as_utc(now or datetime.now(timezone.utc))

    if isinstance(principles, TransferGraph):
        principle_list = list(principles.principles)
    else:
        principle_list = list(principles)

    cases_by_id = {c.id: c for c in cases}

    recs: list[TransferRecommendation] = []
    for principle in principle_list:
        rec = _score_principle(
            query,
            principle,
            cases_by_id=cases_by_id,
            now=now,
            case_dates=case_dates,
            reference_days=cfg.reference_decay_days,
        )
        recs.append(rec)

    # Rank: stance first, then confidence, then structural_fit.
    def _rank(rec: TransferRecommendation) -> tuple[int, float, float, str]:
        fit = rec.metric("structural_fit")
        return (
            -_STANCE_RANK.get(rec.stance, 0),
            -rec.confidence,
            -(fit.value if fit else 0.0),
            rec.principle_id,
        )

    recs.sort(key=_rank)
    recs = recs[: cfg.top_k_recommendations] if cfg.top_k_recommendations > 0 else recs

    if recs:
        best = recs[0]
        best_id = best.principle_id
        best_stance = best.stance
    else:
        best_id = None
        best_stance = TransferStance.ABSTAIN

    summary = _aggregate_summary(recs)

    return TransferReport(
        query_case_id=query.case_id,
        recommendations=tuple(recs),
        summary_metrics=summary,
        best_principle_id=best_id,
        best_stance=best_stance,
    )


def _aggregate_summary(
    recs: Sequence[TransferRecommendation],
) -> tuple[TransferMetric, ...]:
    """Aggregate per-recommendation metrics into report-level summaries.

    For each metric name we surface the *maximum across applies-eligible
    recommendations* for fit/mechanism and the *minimum across
    applies-eligible recommendations* for risk metrics. This is what
    downstream consumers want — "across the principles we entertain,
    how well does the best one fit, and how risky is the least risky
    one?". When no recommendation reached APPLIES/WATCH we fall back
    to the global aggregate so the report is never empty.
    """

    if not recs:
        return ()

    eligible = [r for r in recs if r.stance in (TransferStance.APPLIES, TransferStance.WATCH)]
    pool = eligible or list(recs)

    def _agg(name: str, mode: str) -> TransferMetric:
        values: list[float] = []
        lows: list[bool] = []
        details: list[str] = []
        for rec in pool:
            m = rec.metric(name)
            if m is None:
                continue
            values.append(m.value)
            lows.append(m.low_confidence)
            details.append(f"{rec.principle_id}={m.value:.3f}")
        if not values:
            return TransferMetric(
                name=f"summary_{name}",
                value=0.0,
                range_low=0.0,
                range_high=1.0,
                method=TRANSFER_VERSION,
                low_confidence=True,
                detail=f"no values for {name}",
            )
        value = max(values) if mode == "max" else min(values)
        return TransferMetric(
            name=f"summary_{name}",
            value=_clamp(value, 0.0, 1.0),
            range_low=0.0,
            range_high=1.0,
            method=TRANSFER_VERSION,
            low_confidence=all(lows),
            detail="; ".join(details[:5]),
        )

    return (
        _agg("structural_fit", "max"),
        _agg("mechanism_match", "max"),
        _agg("case_distance", "min"),
        _agg("contradiction_risk", "min"),
        _agg("missing_preconditions", "min"),
        _agg("domain_shift", "min"),
        _agg("time_decay_risk", "min"),
        _agg("outcome_uncertainty", "min"),
    )


# ── Monitoring hooks ────────────────────────────────────────────────────────
#
# These adapters convert upstream artifacts (Currents events, market
# refreshes, uploads) into a :class:`TransferQuery`. They live here
# instead of in the producing modules so the *transfer contract*
# stays in one place — adding a new source means writing a single
# adapter, not edits scattered across the producer.


def query_from_currents_event(
    event: Any,
    *,
    case_id: str | None = None,
) -> TransferQuery:
    """Build a TransferQuery from a Currents event row.

    Accepts duck-typed objects (dataclasses, ORM rows, dicts) and
    pulls the fields the engine cares about. Missing fields stay
    empty rather than being faked.
    """

    def _get(name: str, default: Any = "") -> Any:
        if isinstance(event, Mapping):
            return event.get(name, default)
        return getattr(event, name, default)

    return TransferQuery(
        case_id=str(case_id or _get("id") or _get("event_id") or "currents_event"),
        title=str(_get("title") or _get("headline") or "").strip(),
        domain=str(_get("topic") or _get("category") or "").strip(),
        actors=tuple(_get("actors", ()) or ()),
        institutions=tuple(_get("institutions", ()) or ()),
        mechanism=str(_get("mechanism", "")).strip(),
        outcome_question=str(_get("question") or _get("outcome_question") or "").strip(),
        source_text=str(_get("summary") or _get("body") or "").strip(),
        observed_at=_get("observed_at") or _get("created_at") or None,
    )


def query_from_market(
    market: Any,
    *,
    case_id: str | None = None,
    extra_text: str = "",
) -> TransferQuery:
    """Build a TransferQuery from a ForecastMarket row (or duck-typed shim).

    The adapter mirrors the recipe in
    :func:`noosphere.forecasts.retrieval_adapter.build_query_from_market`
    but emits the typed query shape transfer expects.
    """

    def _get(name: str, default: Any = "") -> Any:
        return getattr(market, name, default)

    title = str(_get("title") or "").strip()
    description = str(_get("description") or "").strip()
    resolution = str(_get("resolution_criteria", _get("resolutionCriteria", ""))).strip()
    category = str(_get("category") or "").strip()
    return TransferQuery(
        case_id=str(case_id or _get("id") or "market"),
        title=title,
        domain=category,
        mechanism="",
        outcome_question=title or resolution,
        source_text="\n\n".join(p for p in (description, resolution, extra_text) if p),
        observed_at=_get("updated_at") or _get("created_at") or None,
    )


def query_from_upload(
    upload: Any,
    *,
    case_id: str | None = None,
) -> TransferQuery:
    """Build a TransferQuery from a Noosphere upload row.

    The intent here is "we just ingested a new source — does it look
    like a case that any existing principle would predict?". The
    adapter pulls title/body/disciplines into the structural fields
    so the engine can answer that without a separate extractor pass.
    """

    def _get(name: str, default: Any = "") -> Any:
        if isinstance(upload, Mapping):
            return upload.get(name, default)
        return getattr(upload, name, default)

    disciplines = _get("disciplines", ()) or ()
    if isinstance(disciplines, (str, bytes)):
        disciplines = (str(disciplines),)
    return TransferQuery(
        case_id=str(case_id or _get("id") or "upload"),
        title=str(_get("title") or "").strip(),
        domain=str(disciplines[0]) if disciplines else "",
        mechanism=str(_get("observed_mechanism", "")).strip(),
        outcome_question=str(_get("outcome_question", "")).strip(),
        source_text=str(_get("body") or _get("text") or "").strip(),
        observed_at=_get("created_at") or None,
    )


__all__ = [
    "APPLIES_FIT_FLOOR",
    "CASE_DISTANCE_WATCH",
    "CONTRADICTION_DROP_FLOOR",
    "DEFAULT_TIME_DECAY_REFERENCE_DAYS",
    "DOMAIN_SHIFT_WATCH",
    "MECHANISM_MATCH_FLOOR",
    "MIN_CLOSE_CASES",
    "MISSING_PRECONDITION_FLOOR",
    "TRANSFER_VERSION",
    "TransferEngineConfig",
    "TransferMetric",
    "TransferQuery",
    "TransferRecommendation",
    "TransferReport",
    "TransferStance",
    "WATCH_FIT_FLOOR",
    "evaluate_transfer",
    "query_from_currents_event",
    "query_from_market",
    "query_from_upload",
]
