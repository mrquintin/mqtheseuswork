"""Reviewer routing driven by the agreement model.

The agreement model (:mod:`noosphere.peer_review.agreement_model`)
predicts, before the swarm runs, how tightly the reviewers will agree on
a conclusion. This module turns that prediction into a *routing
decision*:

* **Predicted contention (low agreement)** → rotate **additional**
  reviewers. More architectural diversity, more cost — the firm spends
  to get a real read on a conclusion the swarm is likely to fight over.
* **Predicted consensus (high agreement)** → run a **smaller** config.
  Cost discipline: the firm should not pay for a four-vendor rotation
  on a conclusion every reviewer will wave through.
* **In between** → keep the founder's default configuration.

Three constraints from the prompt are wired into the types here, not
left to a caller's good intentions:

1. **The model is a predictive aid, not a gate.**
   ``founder_override_full_swarm=True`` forces the full default swarm
   regardless of a high-agreement prediction. :func:`route` honours it
   unconditionally.
2. **Cost savings are reported next to coverage loss.** Every
   :class:`RoutingDecision` carries ``cost_delta_usd`` *and*
   ``coverage_delta`` (signed change in reviewer count). The firm never
   sees a cheaper number without the coverage it bought — or gave up —
   sitting beside it.
3. **The policy is documented and ablation-testable.**
   :class:`RoutingPolicy` is a plain, fully-specified dataclass, and
   :func:`routing_ablation` scores the policy against the
   always-default and always-expanded baselines so a test (or the
   founder) can ask "did routing actually save money, and what did it
   cost in coverage?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from noosphere.peer_review.providers import PROVIDER_DEFAULTS, estimate_cost

# A typical single-objection exchange, used only to price a provider mix
# for the routing decision. These are coarse on purpose — routing needs
# the *relative* cost of mixes, not a billing-grade estimate.
ROUTING_TOKENS_IN = 150
ROUTING_TOKENS_OUT = 220

# Vendors that share no training lineage with each other. ``mistral_oss``
# is the open-weights voice; counting distinct lineages is how we put a
# number on "diversity" rather than just "how many providers".
_VENDOR_LINEAGE = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google",
    "mistral_oss": "mistral-oss",
}


def estimate_mix_cost(
    provider_mix: Sequence[str],
    *,
    tokens_in: int = ROUTING_TOKENS_IN,
    tokens_out: int = ROUTING_TOKENS_OUT,
) -> float:
    """Approximate USD cost of running one swarm pass over ``provider_mix``.

    Uses the *real* price table (:data:`PROVIDER_DEFAULTS`) so the
    open-weights provider is genuinely free and Anthropic is genuinely
    the most expensive token-for-token — the routing cost column is not
    invented. An unknown provider name contributes 0.0 (it has no price
    entry); that is logged-by-omission, not an error, so a test roster
    with synthetic provider names still prices.
    """

    total = 0.0
    for name in provider_mix:
        defaults = PROVIDER_DEFAULTS.get(name)
        if defaults is None:
            continue
        total += estimate_cost(
            defaults=defaults, tokens_in=tokens_in, tokens_out=tokens_out
        )
    return total


def mix_diversity(provider_mix: Sequence[str]) -> int:
    """Number of distinct vendor lineages in a mix (the 'diversity' count)."""

    lineages = {
        _VENDOR_LINEAGE.get(name, f"unknown:{name}") for name in provider_mix
    }
    return len(lineages)


CostFn = Callable[[Sequence[str]], float]


# ── Policy ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutingPolicy:
    """The reviewer-routing policy — fully specified, no hidden defaults.

    ``base_mix`` is the founder's default swarm. When the model predicts
    agreement below ``low_agreement_threshold`` the swarm escalates to
    ``expanded_mix``; above ``high_agreement_threshold`` it de-escalates
    to ``shrunk_mix``; in between it stays on ``base_mix``.

    Every field is on the dataclass so the policy is auditable and an
    ablation test can construct alternatives by hand.
    """

    base_mix: tuple[str, ...]
    expanded_mix: tuple[str, ...]
    shrunk_mix: tuple[str, ...]
    low_agreement_threshold: float = 0.70
    high_agreement_threshold: float = 0.90
    # The policy never lets de-escalation drop the swarm below this many
    # reviewers — a one-reviewer "swarm" has no inter-reviewer signal at
    # all, and the firm's diversity guarantee would not hold.
    min_reviewers: int = 2

    def __post_init__(self) -> None:
        if not (0.0 <= self.low_agreement_threshold
                <= self.high_agreement_threshold <= 1.0):
            raise ValueError(
                "thresholds must satisfy "
                "0 <= low <= high <= 1"
            )
        if len(self.base_mix) < 1:
            raise ValueError("base_mix must contain at least one provider")
        if self.min_reviewers < 1:
            raise ValueError("min_reviewers must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_mix": list(self.base_mix),
            "expanded_mix": list(self.expanded_mix),
            "shrunk_mix": list(self.shrunk_mix),
            "low_agreement_threshold": self.low_agreement_threshold,
            "high_agreement_threshold": self.high_agreement_threshold,
            "min_reviewers": self.min_reviewers,
        }


def default_policy() -> RoutingPolicy:
    """The firm's standing routing policy.

    Default swarm is the closed-weights frontier pair. A contested
    conclusion escalates to the full four-vendor rotation (adds Gemini
    and the open-weights voice — both more diversity and more cost). A
    consensus conclusion de-escalates to a single frontier pair member
    plus the open-weights voice — still two reviewers (the
    ``min_reviewers`` floor), still cross-vendor, but markedly cheaper.
    """

    return RoutingPolicy(
        base_mix=("anthropic", "openai"),
        expanded_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        shrunk_mix=("openai", "mistral_oss"),
    )


# ── Decision ─────────────────────────────────────────────────────────

# Band names. "contested" / "consensus" describe the *swarm*; the pill
# on the review page shows the founder-facing inverse — expected
# *contention* — via :func:`expected_contention_label`.
BAND_CONTESTED = "contested"
BAND_NOMINAL = "nominal"
BAND_CONSENSUS = "consensus"

ACTION_EXPAND = "expand"
ACTION_KEEP = "keep"
ACTION_SHRINK = "shrink"
ACTION_OVERRIDE = "keep_full_swarm_override"


@dataclass(frozen=True)
class RoutingDecision:
    """What the router decided, and what it cost or saved to decide it."""

    predicted_agreement: float
    band: str
    action: str
    provider_mix: tuple[str, ...]
    baseline_mix: tuple[str, ...]
    rationale: str
    estimated_cost_usd: float
    baseline_cost_usd: float
    cost_delta_usd: float  # routed - baseline; negative = saving
    coverage_delta: int  # routed reviewer count - baseline; negative = loss
    diversity_delta: int  # routed vendor lineages - baseline
    founder_override: bool = False

    @property
    def cost_saving_usd(self) -> float:
        """Positive when routing spent *less* than the default swarm."""

        return max(0.0, -self.cost_delta_usd)

    @property
    def coverage_loss(self) -> int:
        """Positive when routing dropped reviewers vs the default swarm."""

        return max(0, -self.coverage_delta)

    @property
    def expected_contention(self) -> str:
        """Founder-facing label: low / moderate / high contention."""

        if self.band == BAND_CONSENSUS:
            return "low"
        if self.band == BAND_CONTESTED:
            return "high"
        return "moderate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicted_agreement": round(self.predicted_agreement, 6),
            "band": self.band,
            "action": self.action,
            "expected_contention": self.expected_contention,
            "provider_mix": list(self.provider_mix),
            "baseline_mix": list(self.baseline_mix),
            "rationale": self.rationale,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "baseline_cost_usd": round(self.baseline_cost_usd, 6),
            "cost_delta_usd": round(self.cost_delta_usd, 6),
            "cost_saving_usd": round(self.cost_saving_usd, 6),
            "coverage_delta": self.coverage_delta,
            "coverage_loss": self.coverage_loss,
            "diversity_delta": self.diversity_delta,
            "founder_override": self.founder_override,
        }


def contention_band(predicted_agreement: float, policy: RoutingPolicy) -> str:
    """Map a predicted agreement score onto a band name."""

    if predicted_agreement < policy.low_agreement_threshold:
        return BAND_CONTESTED
    if predicted_agreement > policy.high_agreement_threshold:
        return BAND_CONSENSUS
    return BAND_NOMINAL


def expected_contention_label(
    predicted_agreement: float, policy: RoutingPolicy
) -> str:
    """``low`` / ``moderate`` / ``high`` — the inverse of the agreement band."""

    band = contention_band(predicted_agreement, policy)
    return {
        BAND_CONSENSUS: "low",
        BAND_NOMINAL: "moderate",
        BAND_CONTESTED: "high",
    }[band]


def _enforce_floor(
    mix: Sequence[str], fallback: Sequence[str], min_reviewers: int
) -> tuple[str, ...]:
    """Never let de-escalation drop below the reviewer floor."""

    mix = tuple(mix)
    if len(mix) >= min_reviewers:
        return mix
    # Pad from the fallback (the base mix) without duplicating providers.
    out = list(mix)
    for name in fallback:
        if len(out) >= min_reviewers:
            break
        if name not in out:
            out.append(name)
    return tuple(out)


def route(
    predicted_agreement: float,
    policy: RoutingPolicy,
    *,
    founder_override_full_swarm: bool = False,
    cost_fn: CostFn = estimate_mix_cost,
) -> RoutingDecision:
    """Decide the reviewer mix for one conclusion from its predicted agreement.

    ``founder_override_full_swarm`` is the prompt's hard constraint: the
    model is an aid, not a gate. When it is set, the swarm runs the full
    default configuration no matter what the model predicted, and the
    decision records ``founder_override=True`` so the override is
    visible in the audit trail rather than silent.
    """

    predicted_agreement = max(0.0, min(1.0, float(predicted_agreement)))
    base_mix = tuple(policy.base_mix)
    baseline_cost = cost_fn(base_mix)
    baseline_n = len(base_mix)
    baseline_div = mix_diversity(base_mix)
    band = contention_band(predicted_agreement, policy)

    if founder_override_full_swarm:
        mix = base_mix
        action = ACTION_OVERRIDE
        rationale = (
            "Founder requested the full default swarm; the agreement "
            f"prediction ({predicted_agreement:.2f}, band '{band}') is "
            "recorded but not acted on. The model is a predictive aid, "
            "not a gate."
        )
    elif band == BAND_CONTESTED:
        mix = tuple(policy.expanded_mix)
        action = ACTION_EXPAND
        rationale = (
            f"Predicted agreement {predicted_agreement:.2f} is below the "
            f"contention threshold ({policy.low_agreement_threshold:.2f}); "
            "rotating additional reviewers for more architectural "
            "diversity. This costs more — see cost_delta_usd."
        )
    elif band == BAND_CONSENSUS:
        mix = _enforce_floor(
            policy.shrunk_mix, base_mix, policy.min_reviewers
        )
        action = ACTION_SHRINK
        rationale = (
            f"Predicted agreement {predicted_agreement:.2f} is above the "
            f"consensus threshold ({policy.high_agreement_threshold:.2f}); "
            "running a smaller configuration for cost discipline. "
            "Coverage given up is reported in coverage_delta — the firm "
            "does not silently prefer the cheap swarm."
        )
    else:
        mix = base_mix
        action = ACTION_KEEP
        rationale = (
            f"Predicted agreement {predicted_agreement:.2f} sits in the "
            "nominal band; keeping the founder's default configuration."
        )

    routed_cost = cost_fn(mix)
    return RoutingDecision(
        predicted_agreement=predicted_agreement,
        band=band,
        action=action,
        provider_mix=mix,
        baseline_mix=base_mix,
        rationale=rationale,
        estimated_cost_usd=routed_cost,
        baseline_cost_usd=baseline_cost,
        cost_delta_usd=routed_cost - baseline_cost,
        coverage_delta=len(mix) - baseline_n,
        diversity_delta=mix_diversity(mix) - baseline_div,
        founder_override=founder_override_full_swarm,
    )


# ── Pre-review prediction record (the artifact the review page reads) ─


def prediction_record(
    *,
    conclusion_id: str,
    decision: RoutingDecision,
    model_trained_at: str = "",
    calibration_skill: Optional[float] = None,
    top_drivers: Optional[list[dict[str, Any]]] = None,
    generated_at: str = "",
) -> dict[str, Any]:
    """Bundle a routing decision into the per-conclusion JSON artifact.

    This is what the swarm persists at review time and what the
    ``ExpectedContentionPill`` on the peer-review page renders. It is a
    flat, self-describing blob — no Python round-trip needed to display
    it.
    """

    return {
        "schema": "theseus.reviewer_agreement_prediction.v1",
        "conclusion_id": conclusion_id,
        "generated_at": generated_at,
        "model_trained_at": model_trained_at,
        "calibration_skill": (
            None if calibration_skill is None else round(calibration_skill, 6)
        ),
        "decision": decision.to_dict(),
        "top_drivers": top_drivers or [],
    }


# ── Ablation harness ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutingAblation:
    """Routing policy vs the always-default and always-expanded baselines.

    The headline pair the prompt demands: ``cost_saving_vs_base_usd``
    sits next to ``coverage_delta_vs_base``. A negative coverage delta
    is a real cost of the saving and is reported as such — the firm
    reads both numbers or neither.
    """

    n_conclusions: int
    routed_cost_usd: float
    base_cost_usd: float
    expanded_cost_usd: float
    routed_total_reviewers: int
    base_total_reviewers: int
    expanded_total_reviewers: int
    cost_saving_vs_base_usd: float
    coverage_delta_vs_base: int
    cost_saving_vs_expanded_usd: float
    coverage_delta_vs_expanded: int
    expand_count: int
    keep_count: int
    shrink_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_conclusions": self.n_conclusions,
            "routed_cost_usd": round(self.routed_cost_usd, 6),
            "base_cost_usd": round(self.base_cost_usd, 6),
            "expanded_cost_usd": round(self.expanded_cost_usd, 6),
            "routed_total_reviewers": self.routed_total_reviewers,
            "base_total_reviewers": self.base_total_reviewers,
            "expanded_total_reviewers": self.expanded_total_reviewers,
            "cost_saving_vs_base_usd": round(self.cost_saving_vs_base_usd, 6),
            "coverage_delta_vs_base": self.coverage_delta_vs_base,
            "cost_saving_vs_expanded_usd": round(
                self.cost_saving_vs_expanded_usd, 6
            ),
            "coverage_delta_vs_expanded": self.coverage_delta_vs_expanded,
            "expand_count": self.expand_count,
            "keep_count": self.keep_count,
            "shrink_count": self.shrink_count,
        }


def routing_ablation(
    predicted_agreements: Sequence[float],
    policy: RoutingPolicy,
    *,
    cost_fn: CostFn = estimate_mix_cost,
) -> RoutingAblation:
    """Score ``policy`` against the always-base / always-expanded baselines.

    Run the policy over a set of predicted-agreement scores (one per
    conclusion) and tabulate what it spent and what it covered against
    the two trivial policies it sits between. This is the
    ablation-testable surface: a test asserts the routed policy spends
    less than always-expanded, and the function reports the coverage
    that saving cost.
    """

    decisions = [route(p, policy, cost_fn=cost_fn) for p in predicted_agreements]
    n = len(decisions)

    routed_cost = sum(d.estimated_cost_usd for d in decisions)
    base_cost = sum(d.baseline_cost_usd for d in decisions)
    expanded_cost = n * cost_fn(policy.expanded_mix)

    routed_reviewers = sum(len(d.provider_mix) for d in decisions)
    base_reviewers = n * len(policy.base_mix)
    expanded_reviewers = n * len(policy.expanded_mix)

    return RoutingAblation(
        n_conclusions=n,
        routed_cost_usd=routed_cost,
        base_cost_usd=base_cost,
        expanded_cost_usd=expanded_cost,
        routed_total_reviewers=routed_reviewers,
        base_total_reviewers=base_reviewers,
        expanded_total_reviewers=expanded_reviewers,
        cost_saving_vs_base_usd=base_cost - routed_cost,
        coverage_delta_vs_base=routed_reviewers - base_reviewers,
        cost_saving_vs_expanded_usd=expanded_cost - routed_cost,
        coverage_delta_vs_expanded=routed_reviewers - expanded_reviewers,
        expand_count=sum(1 for d in decisions if d.action == ACTION_EXPAND),
        keep_count=sum(
            1 for d in decisions if d.action in (ACTION_KEEP, ACTION_OVERRIDE)
        ),
        shrink_count=sum(1 for d in decisions if d.action == ACTION_SHRINK),
    )


__all__ = [
    "ACTION_EXPAND",
    "ACTION_KEEP",
    "ACTION_OVERRIDE",
    "ACTION_SHRINK",
    "BAND_CONSENSUS",
    "BAND_CONTESTED",
    "BAND_NOMINAL",
    "RoutingAblation",
    "RoutingDecision",
    "RoutingPolicy",
    "contention_band",
    "default_policy",
    "estimate_mix_cost",
    "expected_contention_label",
    "mix_diversity",
    "prediction_record",
    "route",
    "routing_ablation",
]
