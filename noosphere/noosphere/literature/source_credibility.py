"""
Source-credibility ledger.

A canonical source (see ``source_priors`` for source types and
``standing.canonical_source_id`` for identity) accumulates a track
record of how often evidence drawn from it holds up under later
scrutiny. Each scrutiny event — a forecast resolving for or against a
conclusion that cited the source, a retraction landing, a peer-review
verdict — produces a *credibility update*. The updates are folded into
a Beta posterior layered on the source-type prior.

The credibility number is **not** a single firm-wide trust score; it
is the posterior mean, displayed alongside the count of updates so the
reader can judge how much weight to put on it. Until the count clears
``MIN_UPDATES_FOR_CONFIDENT_DISPLAY`` the UI displays the underlying
``n=K updates`` rather than a confident percentage.

Design notes:

* **Weighted updates.** A forecast where the source was *load-bearing*
  (i.e. the conclusion would not have been made without it) counts
  more than one where it was tangential. The weight enters the Beta
  update directly: a confirmation of weight ``w`` adds ``w`` to alpha,
  a failure adds ``w`` to beta. This is the standard weighted Bernoulli
  / Beta-binomial trick: pseudo-observations need not be integers.

* **Time series.** The persistent representation is a list of
  ``CredibilityUpdate`` rows, append-only. ``current_credibility`` is
  computed by folding all updates into the type prior — there is no
  running cache that can drift. The Prisma side stores running totals
  for fast UI queries, but the running totals are *derived*; if they
  are ever inconsistent with the update log, the log wins.

* **Cascade modulation.** A ``supports`` edge contributes a base
  confidence, but its *effective* contribution to the parent claim's
  evidence weight is scaled by the source's posterior credibility. The
  aggregator is capped at the maximum credibility of any single
  contributing source so that piling on weak-source supports cannot
  manufacture strong evidence (the multiplication of weak evidence
  does not produce strong evidence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Iterable, Optional, Protocol, Sequence

from .source_priors import (
    MIN_UPDATES_FOR_CONFIDENT_DISPLAY,
    SourcePrior,
    SourceType,
    prior_for,
)


class CredibilityOutcome(str, Enum):
    """The two directions a credibility update can move.

    A retraction or peer-review-fail is a CONFIRMED *failure*; the
    cited source did not hold up. A forecast resolution that the
    source's evidence pointed toward is a CONFIRMED *success*. We use
    a single outcome enum to keep the update path symmetric.
    """

    CONFIRMATION = "confirmation"
    FAILURE = "failure"


class CredibilityEventKind(str, Enum):
    """Why this update is being recorded.

    The kind is informational — it does not change the maths — but is
    persisted so an auditor can ask "show me every credibility update
    that came from a forecast resolution".
    """

    FORECAST_RESOLUTION = "forecast_resolution"
    RETRACTION = "retraction"
    PEER_REVIEW_VERDICT = "peer_review_verdict"
    MANUAL_OVERRIDE = "manual_override"


@dataclass(frozen=True)
class CredibilityUpdate:
    """One append-only event in the credibility ledger.

    ``weight`` ∈ (0, 1] is the *load-bearing* weight of the source for
    the conclusion at hand: 1.0 = the conclusion would not have been
    made without this source; 0.1 = the source was a tangential cite.
    Callers compute the weight at the conclusion-resolution boundary
    using whatever signal is available (citation flag, cascade-edge
    confidence, founder annotation). The Beta update then treats the
    event as ``weight`` pseudo-observations of the outcome.
    """

    source_id: str
    outcome: CredibilityOutcome
    weight: float
    kind: CredibilityEventKind
    conclusion_id: str
    observed_at: datetime
    note: str = ""
    raw_payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isfinite(self.weight) or not 0.0 < self.weight <= 1.0:
            raise ValueError(
                f"weight must be in (0, 1]; got {self.weight!r}"
            )

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "outcome": self.outcome.value,
            "weight": self.weight,
            "kind": self.kind.value,
            "conclusion_id": self.conclusion_id,
            "observed_at": self.observed_at.isoformat(),
            "note": self.note,
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(frozen=True)
class BetaPosterior:
    """A Beta(alpha, beta) posterior over a source's credibility.

    Created by ``apply_updates`` — never mutated. The display layer
    consumes ``mean``, ``score_100``, and the underlying alpha/beta.
    ``effective_n`` counts the *weighted* number of observations on top
    of the prior; ``n_confirmations`` and ``n_failures`` are the raw
    integer counts of CONFIRMATION and FAILURE events (used by the UI
    "n+ confirmations / n- failures" line, which intentionally shows
    counts rather than weighted sums to be easier to reason about).
    """

    source_id: str
    source_type: SourceType
    alpha: float
    beta: float
    n_updates: int
    n_confirmations: int
    n_failures: int
    last_updated_at: Optional[datetime]

    def __post_init__(self) -> None:
        # The Beta distribution is undefined for non-positive shape
        # parameters; callers should never construct a posterior that
        # violates this. The prior contributes positive alpha/beta and
        # weighted updates only add non-negative mass, so the only way
        # to land here illegally is a programming error.
        if self.alpha <= 0.0 or self.beta <= 0.0:
            raise ValueError(
                f"Beta posterior requires positive alpha, beta; "
                f"got alpha={self.alpha} beta={self.beta}"
            )

    @property
    def mean(self) -> float:
        m = self.alpha / (self.alpha + self.beta)
        # Clamp paranoia — the algebra cannot leave [0,1] but UI code
        # consumes this directly and we want a hard guarantee.
        if m < 0.0:
            return 0.0
        if m > 1.0:
            return 1.0
        return m

    @property
    def score_100(self) -> float:
        """Display-friendly 0–100 strip value."""

        return round(self.mean * 100.0, 1)

    @property
    def variance(self) -> float:
        s = self.alpha + self.beta
        return (self.alpha * self.beta) / (s * s * (s + 1.0))

    @property
    def effective_n(self) -> float:
        """Weighted count of observations, prior-included."""

        return self.alpha + self.beta

    @property
    def is_confident_for_display(self) -> bool:
        """True once enough updates have landed to show a confident number."""

        return self.n_updates >= MIN_UPDATES_FOR_CONFIDENT_DISPLAY

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "alpha": self.alpha,
            "beta": self.beta,
            "mean": self.mean,
            "score_100": self.score_100,
            "n_updates": self.n_updates,
            "n_confirmations": self.n_confirmations,
            "n_failures": self.n_failures,
            "is_confident_for_display": self.is_confident_for_display,
            "last_updated_at": self.last_updated_at.isoformat()
            if self.last_updated_at
            else None,
        }


def apply_updates(
    *,
    source_id: str,
    source_type: SourceType | str | None,
    updates: Sequence[CredibilityUpdate],
    prior: Optional[SourcePrior] = None,
) -> BetaPosterior:
    """Fold a sequence of updates into the Beta posterior.

    Updates are *commutative* under the Beta-binomial conjugate update,
    so order doesn't change the posterior, but ``last_updated_at``
    tracks the most recent ``observed_at`` regardless.
    """

    p = prior or prior_for(source_type)
    alpha = p.alpha
    beta = p.beta
    n_conf = 0
    n_fail = 0
    last: Optional[datetime] = None
    for u in updates:
        if u.outcome is CredibilityOutcome.CONFIRMATION:
            alpha += u.weight
            n_conf += 1
        else:
            beta += u.weight
            n_fail += 1
        if last is None or u.observed_at > last:
            last = u.observed_at
    return BetaPosterior(
        source_id=source_id,
        source_type=p.source_type,
        alpha=alpha,
        beta=beta,
        n_updates=n_conf + n_fail,
        n_confirmations=n_conf,
        n_failures=n_fail,
        last_updated_at=last,
    )


# ── Pluggable persistence ───────────────────────────────────────────────


class CredibilityLedger(Protocol):
    """Storage contract for credibility updates.

    Production wires this to the Prisma SourceCredibility table; tests
    use the in-memory implementation below. Implementations are
    append-only — there is no update path that mutates a prior row.
    """

    def append(self, update: CredibilityUpdate) -> bool: ...
    def history(self, source_id: str) -> list[CredibilityUpdate]: ...
    def all(self) -> list[CredibilityUpdate]: ...


class InMemoryCredibilityLedger:
    """In-memory implementation used by tests and offline tooling.

    ``append`` is idempotent on the tuple
    ``(source_id, conclusion_id, kind, outcome)``: re-applying the same
    resolution writes nothing new. This matches the standing ledger's
    discipline and keeps polling code from double-counting.
    """

    def __init__(self) -> None:
        self._rows: list[CredibilityUpdate] = []

    def append(self, update: CredibilityUpdate) -> bool:
        for row in self._rows:
            if (
                row.source_id == update.source_id
                and row.conclusion_id == update.conclusion_id
                and row.kind == update.kind
                and row.outcome == update.outcome
            ):
                return False
        self._rows.append(update)
        return True

    def history(self, source_id: str) -> list[CredibilityUpdate]:
        return [r for r in self._rows if r.source_id == source_id]

    def all(self) -> list[CredibilityUpdate]:
        return list(self._rows)


def current_credibility(
    *,
    source_id: str,
    source_type: SourceType | str | None,
    ledger: CredibilityLedger,
    prior: Optional[SourcePrior] = None,
) -> BetaPosterior:
    """View: latest posterior for a source, derived from the full log."""

    return apply_updates(
        source_id=source_id,
        source_type=source_type,
        updates=ledger.history(source_id),
        prior=prior,
    )


# ── Cascade weight modulation ──────────────────────────────────────────
#
# A ``supports`` edge in the cascade carries a base confidence in
# [0, 1]. The credibility ledger modulates this in two stages:
#
#   1. **Per-edge scaling.** The effective weight of a single supports
#      edge is ``base_confidence * posterior.mean``. A 0.9-confidence
#      edge from a source with credibility 0.3 contributes only 0.27.
#      This reflects: the *evidence weight* of a supporting source is
#      bounded above by how often that source's evidence has held up.
#
#   2. **Aggregation cap.** When multiple supports edges are pooled,
#      the standard noisy-OR aggregator
#      ``1 - prod(1 - effective_i)`` lets independent weak signals
#      combine into a strong one. That is mathematically right *if*
#      independence holds, but the firm's worry case is correlated
#      weak sources (a hundred X posts repeating one tabloid claim).
#      We therefore cap the aggregate at the *maximum credibility* of
#      any single contributing source — capping at the strongest leg
#      means a claim supported only by low-credibility sources cannot
#      escape low confidence regardless of how many such sources pile
#      on.
#
# Both functions accept zero edges and return 0 — they are total.

def modulated_supports_confidence(
    base_confidence: float,
    posterior: Optional[BetaPosterior],
) -> float:
    """Scale a single supports-edge confidence by the source's credibility.

    ``posterior`` may be ``None`` if the source is unknown to the
    ledger; in that case we fall back to a neutral 0.5 (the unknown
    prior's mean), which is more conservative than treating an unknown
    source as fully credible.
    """

    if not isfinite(base_confidence) or base_confidence < 0.0:
        return 0.0
    base = min(base_confidence, 1.0)
    cred = posterior.mean if posterior is not None else 0.5
    out = base * cred
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def aggregate_supports_confidence(
    contributions: Iterable[tuple[float, Optional[BetaPosterior]]],
) -> float:
    """Combine multiple supports-edge contributions into a single weight.

    ``contributions`` is an iterable of ``(base_confidence, posterior)``
    pairs, one per supports edge feeding the same target claim. Returns
    a value in [0, 1] computed as
    ``min(1 - prod(1 - effective_i), max(credibility_i))``.

    The cap means that no matter how many low-credibility supports
    pile up, the aggregated weight cannot exceed the credibility of
    the *best* contributing source — so weak evidence does not
    multiply into strong evidence.
    """

    items = list(contributions)
    if not items:
        return 0.0

    noisy_or = 1.0
    cap = 0.0
    for base, posterior in items:
        eff = modulated_supports_confidence(base, posterior)
        noisy_or *= (1.0 - eff)
        cred = posterior.mean if posterior is not None else 0.5
        if cred > cap:
            cap = cred

    aggregate = 1.0 - noisy_or
    if aggregate > cap:
        aggregate = cap
    if aggregate < 0.0:
        return 0.0
    if aggregate > 1.0:
        return 1.0
    return aggregate


def display_payload(posterior: BetaPosterior) -> dict:
    """UI-shaped payload for CitationPopover / founder citation list.

    Returns a stable shape so the front end can render the 0–100 strip
    plus the hover detail. ``confident=False`` means the UI should
    show the ``n=K updates`` caveat rather than a confident number.
    """

    return {
        "source_id": posterior.source_id,
        "source_type": posterior.source_type.value,
        "score_100": posterior.score_100,
        "mean": posterior.mean,
        "alpha": posterior.alpha,
        "beta": posterior.beta,
        "n_updates": posterior.n_updates,
        "n_confirmations": posterior.n_confirmations,
        "n_failures": posterior.n_failures,
        "confident": posterior.is_confident_for_display,
        "min_updates_for_confidence": MIN_UPDATES_FOR_CONFIDENT_DISPLAY,
        "last_updated_at": posterior.last_updated_at.isoformat()
        if posterior.last_updated_at
        else None,
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
