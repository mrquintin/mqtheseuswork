"""
Bayesian-belief layer — inference engine.

Given a :class:`~noosphere.inquiry.bayesian_network.BayesianNetwork`
derived from a cascade snapshot, this module answers three questions:

* **What does the firm believe?** ``infer_marginals`` returns a marginal
  probability per claim, each with a credible interval that reflects
  *CPT uncertainty* — wide when the CPT is a seeded guess, tight once
  ``bn_learning`` has fit it to resolved cases.
* **What changes when evidence lands?** ``infer_marginals`` takes an
  ``evidence`` map (a source retracts → that claim is pinned False; a
  forecast resolves → pinned True); ``compare_to_stored`` then diffs the
  recomputed marginal against the firm's stored confidence, and
  ``to_revision_inputs`` hands the significant deltas to the cascade
  revision engine.
* **Why does the firm believe it?** ``sensitivity`` reports, per parent
  claim, what the marginal would be if that parent were retracted —
  ``p`` would drop to ``p'`` — which is exactly what the founder
  ``Bayesian view`` tab renders.

Two inference backends, picked by graph size:

* **Exact** (``≤ EXACT_NODE_LIMIT`` nodes): variable elimination in
  reverse-topological order. The result is exact up to floating point;
  the credible interval is obtained by resampling every CPT from its
  Beta posterior and re-running elimination.
* **Approximate** (larger graphs): likelihood-weighted importance
  sampling. The result carries ``method="importance_sampling"`` and an
  honest sample count + CI so the UI never implies exactness it does
  not have.

This module imports the cascade revision engine's ``RevisionInput`` to
close the loop from B → C → the revision layer. That import direction
(inquiry → cascade) is allowed; the reverse is not, which is why the
cascade only ever exposes a plain-data *skeleton*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Mapping, Optional, Sequence

import numpy as np

from noosphere.cascade.revision import DEFAULT_DELTA, RevisionInput
from noosphere.inquiry.bayesian_network import BayesianNetwork

# Above this node count, exact variable elimination is no longer the
# right default (treewidth blows up); we fall back to importance
# sampling. The prompt's practical limit.
EXACT_NODE_LIMIT = 200

# Default resample count for the exact-path credible interval and for
# importance sampling. Both are overridable per call.
DEFAULT_CI_SAMPLES = 0          # 0 ⇒ point estimate only (no CPT resampling)
DEFAULT_IMPORTANCE_SAMPLES = 20_000

# Credible-interval coverage: 5th / 95th percentile ⇒ a 90% interval.
_CI_LOW_Q = 5.0
_CI_HIGH_Q = 95.0
# z for a 90% Wald interval (importance-sampling path).
_WALD_Z = 1.645

Evidence = Mapping[str, bool]


# ── factor algebra (variable elimination) ───────────────────────────────


@dataclass(frozen=True)
class _Factor:
    """A discrete factor over binary variables.

    ``table`` is keyed by a tuple of bools aligned positionally with
    ``variables``. Not part of the public surface — VE plumbing only.
    """

    variables: tuple[str, ...]
    table: Mapping[tuple[bool, ...], float]

    def get(self, full_assignment: Mapping[str, bool]) -> float:
        key = tuple(full_assignment[v] for v in self.variables)
        return self.table.get(key, 0.0)


def _cpt_to_factor(node) -> _Factor:  # noqa: ANN001 (BNNode)
    cpt = node.cpt
    variables = (node.node_id,) + cpt.parents
    table: dict[tuple[bool, ...], float] = {}
    from noosphere.inquiry.bayesian_network import _all_assignments

    for parent_assignment in _all_assignments(len(cpt.parents)):
        p_true = cpt.p_true(parent_assignment)
        table[(True,) + parent_assignment] = p_true
        table[(False,) + parent_assignment] = 1.0 - p_true
    return _Factor(variables=variables, table=table)


def _reduce(factor: _Factor, evidence: Evidence) -> _Factor:
    """Restrict a factor to an evidence assignment, dropping pinned vars."""
    pinned = [v for v in factor.variables if v in evidence]
    if not pinned:
        return factor
    keep = tuple(v for v in factor.variables if v not in evidence)
    keep_idx = [i for i, v in enumerate(factor.variables) if v not in evidence]
    pin_idx = [(i, evidence[v]) for i, v in enumerate(factor.variables) if v in evidence]
    out: dict[tuple[bool, ...], float] = {}
    for key, value in factor.table.items():
        if any(key[i] != want for i, want in pin_idx):
            continue
        new_key = tuple(key[i] for i in keep_idx)
        out[new_key] = out.get(new_key, 0.0) + value
    return _Factor(variables=keep, table=out)


def _multiply(f1: _Factor, f2: _Factor) -> _Factor:
    extra = tuple(v for v in f2.variables if v not in f1.variables)
    new_vars = f1.variables + extra
    f1_idx = {v: i for i, v in enumerate(f1.variables)}
    f2_idx = {v: i for i, v in enumerate(f2.variables)}
    out: dict[tuple[bool, ...], float] = {}
    from noosphere.inquiry.bayesian_network import _all_assignments

    for assignment in _all_assignments(len(new_vars)):
        amap = dict(zip(new_vars, assignment))
        k1 = tuple(amap[v] for v in f1.variables)
        k2 = tuple(amap[v] for v in f2.variables)
        out[assignment] = f1.table.get(k1, 0.0) * f2.table.get(k2, 0.0)
    return _Factor(variables=new_vars, table=out)


def _marginalize(factor: _Factor, var: str) -> _Factor:
    if var not in factor.variables:
        return factor
    idx = factor.variables.index(var)
    new_vars = factor.variables[:idx] + factor.variables[idx + 1 :]
    out: dict[tuple[bool, ...], float] = {}
    for key, value in factor.table.items():
        new_key = key[:idx] + key[idx + 1 :]
        out[new_key] = out.get(new_key, 0.0) + value
    return _Factor(variables=new_vars, table=out)


def _variable_elimination(
    bn: BayesianNetwork,
    query: str,
    evidence: Evidence,
) -> float:
    """Exact ``P(query = True | evidence)`` by bucket elimination.

    Elimination order is reverse-topological (leaves first), which keeps
    the intermediate factors small for the tree-shaped graphs the
    cascade tends to produce, and is fully deterministic.
    """
    if query in evidence:
        return 1.0 if evidence[query] else 0.0

    factors = [_reduce(_cpt_to_factor(node), evidence) for node in bn]
    order = [
        v
        for v in reversed(bn.topological_order())
        if v != query and v not in evidence
    ]
    for var in order:
        touching = [f for f in factors if var in f.variables]
        if not touching:
            continue
        factors = [f for f in factors if var not in f.variables]
        product = touching[0]
        for f in touching[1:]:
            product = _multiply(product, f)
        factors.append(_marginalize(product, var))

    result = factors[0]
    for f in factors[1:]:
        result = _multiply(result, f)
    # ``result`` now ranges over a subset of {query}. Normalise.
    if result.variables == (query,):
        p_true = result.table.get((True,), 0.0)
        p_false = result.table.get((False,), 0.0)
    elif result.variables == ():
        # query had no factor mentioning it — should not happen, every
        # node contributes its own CPT factor — but stay total.
        return 0.5
    else:  # pragma: no cover - defensive
        raise RuntimeError(
            f"variable elimination left stray variables {result.variables!r}"
        )
    total = p_true + p_false
    if total <= 0.0:
        # Evidence has zero probability under the model — return the
        # prior-free midpoint rather than dividing by zero.
        return 0.5
    return p_true / total


# ── public result types ─────────────────────────────────────────────────


@dataclass(frozen=True)
class MarginalResult:
    """A marginal probability for one claim plus its credible interval.

    ``exact`` distinguishes variable elimination from importance
    sampling. ``n_samples`` is the CPT-resample count on the exact path
    (0 ⇒ point estimate, CI collapses to the point) and the
    importance-sample count on the approximate path. ``is_evidence`` is
    True when this node was pinned by an evidence update.
    """

    node_id: str
    p_true: float
    ci_low: float
    ci_high: float
    method: str
    n_samples: int
    exact: bool
    is_evidence: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "p_true": self.p_true,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "method": self.method,
            "n_samples": self.n_samples,
            "exact": self.exact,
            "is_evidence": self.is_evidence,
        }


@dataclass(frozen=True)
class ParentSensitivity:
    """How much one parent claim moves a node's marginal.

    ``p_if_retracted`` is the marginal with the parent pinned False (the
    claim does not hold); ``p_if_held`` pins it True. ``delta`` is the
    drop the founder sees described as "if X were retracted, the
    marginal would fall from p to p'". ``influence`` is the full swing
    between the two pins — the right key for ranking parents.
    """

    parent_id: str
    parent_ref: str
    baseline: float
    p_if_retracted: float
    p_if_held: float

    @property
    def delta(self) -> float:
        return self.baseline - self.p_if_retracted

    @property
    def influence(self) -> float:
        return abs(self.p_if_held - self.p_if_retracted)

    def to_dict(self) -> dict:
        return {
            "parent_id": self.parent_id,
            "parent_ref": self.parent_ref,
            "baseline": self.baseline,
            "p_if_retracted": self.p_if_retracted,
            "p_if_held": self.p_if_held,
            "delta": self.delta,
            "influence": self.influence,
        }


# ── exact / approximate marginals ───────────────────────────────────────


def marginal(
    bn: BayesianNetwork,
    node_id: str,
    *,
    evidence: Optional[Evidence] = None,
) -> float:
    """Exact ``P(node_id = True | evidence)`` via variable elimination."""
    return _variable_elimination(bn, node_id, dict(evidence or {}))


def _resample_network(
    bn: BayesianNetwork, rng: np.random.Generator
) -> BayesianNetwork:
    """A copy of ``bn`` with every CPT drawn from its Beta posterior."""
    from noosphere.inquiry.bayesian_network import BNNode

    def beta_sampler(a: float, b: float) -> float:
        return float(rng.beta(a, b))

    nodes = {}
    for node in bn:
        resampled = node.cpt.resample(beta_sampler)
        nodes[node.node_id] = BNNode(
            node_id=node.node_id,
            ref=node.ref,
            kind=node.kind,
            parents=node.parents,
            cpt=resampled,
            seeded=node.seeded,
        )
    return BayesianNetwork(nodes=nodes, dropped_edges=bn.dropped_edges)


def _exact_marginals(
    bn: BayesianNetwork,
    evidence: Evidence,
    ci_samples: int,
    rng: np.random.Generator,
) -> dict[str, MarginalResult]:
    point = {nid: _variable_elimination(bn, nid, evidence) for nid in bn.nodes}

    has_uncertainty = any(node.cpt.counts for node in bn)
    if ci_samples <= 0 or not has_uncertainty:
        return {
            nid: MarginalResult(
                node_id=nid,
                p_true=point[nid],
                ci_low=point[nid],
                ci_high=point[nid],
                method="exact",
                n_samples=0,
                exact=True,
                is_evidence=nid in evidence,
            )
            for nid in bn.nodes
        }

    samples: dict[str, list[float]] = {nid: [] for nid in bn.nodes}
    for _ in range(ci_samples):
        resampled = _resample_network(bn, rng)
        for nid in bn.nodes:
            samples[nid].append(_variable_elimination(resampled, nid, evidence))

    out: dict[str, MarginalResult] = {}
    for nid in bn.nodes:
        arr = np.asarray(samples[nid], dtype=float)
        out[nid] = MarginalResult(
            node_id=nid,
            p_true=point[nid],
            ci_low=float(np.percentile(arr, _CI_LOW_Q)),
            ci_high=float(np.percentile(arr, _CI_HIGH_Q)),
            method="exact",
            n_samples=ci_samples,
            exact=True,
            is_evidence=nid in evidence,
        )
    return out


def _importance_sampling_marginals(
    bn: BayesianNetwork,
    evidence: Evidence,
    n_samples: int,
    rng: np.random.Generator,
) -> dict[str, MarginalResult]:
    """Likelihood-weighted sampling for graphs past the exact limit.

    Each sample fixes evidence nodes to their pinned value, draws every
    other node from its CPT given already-sampled parents, and weights
    the sample by the likelihood of the evidence. The CI is a Wald
    interval on the *effective* sample size, so a graph where the
    evidence is improbable honestly reports a wide interval.
    """
    order = bn.topological_order()
    w_true: dict[str, float] = {nid: 0.0 for nid in bn.nodes}
    w_sq_true: dict[str, float] = {nid: 0.0 for nid in bn.nodes}
    total_w = 0.0
    total_w_sq = 0.0

    for _ in range(n_samples):
        assignment: dict[str, bool] = {}
        weight = 1.0
        for nid in order:
            node = bn.nodes[nid]
            parent_assignment = tuple(assignment[p] for p in node.parents)
            p_true = node.cpt.p_true(parent_assignment)
            if nid in evidence:
                value = evidence[nid]
                weight *= p_true if value else (1.0 - p_true)
                assignment[nid] = value
            else:
                assignment[nid] = bool(rng.random() < p_true)
        total_w += weight
        total_w_sq += weight * weight
        for nid, value in assignment.items():
            if value:
                w_true[nid] += weight
                w_sq_true[nid] += weight * weight

    # Effective sample size of the weighting scheme.
    ess = (total_w * total_w) / total_w_sq if total_w_sq > 0.0 else 0.0

    out: dict[str, MarginalResult] = {}
    for nid in bn.nodes:
        if nid in evidence:
            value = evidence[nid]
            p = 1.0 if value else 0.0
            out[nid] = MarginalResult(
                node_id=nid,
                p_true=p,
                ci_low=p,
                ci_high=p,
                method="importance_sampling",
                n_samples=n_samples,
                exact=False,
                is_evidence=True,
            )
            continue
        p = (w_true[nid] / total_w) if total_w > 0.0 else 0.5
        if ess > 0.0:
            se = sqrt(max(p * (1.0 - p), 0.0) / ess)
        else:
            se = 0.5
        out[nid] = MarginalResult(
            node_id=nid,
            p_true=p,
            ci_low=max(0.0, p - _WALD_Z * se),
            ci_high=min(1.0, p + _WALD_Z * se),
            method="importance_sampling",
            n_samples=n_samples,
            exact=False,
            is_evidence=False,
        )
    return out


def infer_marginals(
    bn: BayesianNetwork,
    *,
    evidence: Optional[Evidence] = None,
    ci_samples: int = DEFAULT_CI_SAMPLES,
    importance_samples: int = DEFAULT_IMPORTANCE_SAMPLES,
    seed: int = 0,
    exact_limit: int = EXACT_NODE_LIMIT,
) -> dict[str, MarginalResult]:
    """Marginal probability per claim, with a CI reflecting CPT uncertainty.

    For ``len(bn) <= exact_limit`` the result is exact (variable
    elimination); the CI is obtained by resampling CPTs from their Beta
    posteriors ``ci_samples`` times (``0`` ⇒ point estimate only). Past
    the limit the result is importance-sampled and flagged
    ``method="importance_sampling"`` so the UI shows the sample count
    and interval rather than implying exactness.
    """
    evidence = dict(evidence or {})
    rng = np.random.default_rng(seed)
    if len(bn) <= exact_limit:
        return _exact_marginals(bn, evidence, ci_samples, rng)
    return _importance_sampling_marginals(bn, evidence, importance_samples, rng)


# ── sensitivity analysis ────────────────────────────────────────────────


def sensitivity(
    bn: BayesianNetwork,
    node_id: str,
    *,
    evidence: Optional[Evidence] = None,
) -> list[ParentSensitivity]:
    """Per-parent sensitivity of ``node_id``'s marginal.

    For each direct parent the marginal is recomputed with the parent
    pinned False (retracted) and pinned True (held). Parents already
    fixed by ``evidence`` are skipped — their value is not a free
    variable. Exact; uses variable elimination, so it is cheap on the
    graph sizes the founder UI cares about.
    """
    evidence = dict(evidence or {})
    baseline = _variable_elimination(bn, node_id, evidence)
    results: list[ParentSensitivity] = []
    for parent_id in bn.parents_of(node_id):
        if parent_id in evidence:
            continue
        ev_false = {**evidence, parent_id: False}
        ev_true = {**evidence, parent_id: True}
        results.append(
            ParentSensitivity(
                parent_id=parent_id,
                parent_ref=bn.nodes[parent_id].ref,
                baseline=baseline,
                p_if_retracted=_variable_elimination(bn, node_id, ev_false),
                p_if_held=_variable_elimination(bn, node_id, ev_true),
            )
        )
    results.sort(key=lambda s: (-s.influence, s.parent_id))
    return results


def most_influential_parents(
    bn: BayesianNetwork,
    node_id: str,
    *,
    evidence: Optional[Evidence] = None,
    top_k: int = 5,
) -> list[ParentSensitivity]:
    """The ``top_k`` parents with the largest swing on ``node_id``."""
    return sensitivity(bn, node_id, evidence=evidence)[:top_k]


# ── evidence updates → revision engine (part C) ─────────────────────────


@dataclass(frozen=True)
class EvidenceUpdate:
    """One piece of external evidence that pins a claim's truth value.

    A source retraction or a peer-review fail lands as ``holds=False``;
    a forecast resolving the firm's way lands as ``holds=True``. The
    ``kind`` mirrors the credibility ledger's event kinds purely for
    audit; it does not change the maths.
    """

    node_id: str
    holds: bool
    kind: str = "evidence"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "holds": self.holds,
            "kind": self.kind,
            "note": self.note,
        }


def evidence_map(updates: Sequence[EvidenceUpdate]) -> dict[str, bool]:
    """Fold a list of updates into an ``evidence`` map.

    Last write wins if two updates name the same claim, so callers get
    deterministic behaviour by controlling input order.
    """
    out: dict[str, bool] = {}
    for u in updates:
        out[u.node_id] = u.holds
    return out


@dataclass(frozen=True)
class ConfidenceDelta:
    """A diff between the BN's recomputed marginal and stored confidence.

    ``significant`` gates which deltas reach the revision engine — it
    uses the cascade revision engine's ``DEFAULT_DELTA`` so the two
    layers agree on what counts as a real shift.
    """

    node_id: str
    stored_confidence: float
    recomputed_marginal: float
    ci_low: float
    ci_high: float
    significant: bool

    @property
    def delta(self) -> float:
        return self.recomputed_marginal - self.stored_confidence

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "stored_confidence": self.stored_confidence,
            "recomputed_marginal": self.recomputed_marginal,
            "delta": self.delta,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "significant": self.significant,
        }


def compare_to_stored(
    marginals: Mapping[str, MarginalResult],
    stored_confidence: Mapping[str, float],
    *,
    threshold: float = DEFAULT_DELTA,
) -> list[ConfidenceDelta]:
    """Diff recomputed marginals against the firm's stored confidence.

    Only nodes present in *both* ``marginals`` and ``stored_confidence``
    are compared — the BN spans claims the firm has not published a
    confidence for, and those are not revision candidates. Result is
    sorted by descending absolute delta so the founder sees the biggest
    movers first.
    """
    deltas: list[ConfidenceDelta] = []
    for node_id, stored in stored_confidence.items():
        result = marginals.get(node_id)
        if result is None:
            continue
        d = ConfidenceDelta(
            node_id=node_id,
            stored_confidence=stored,
            recomputed_marginal=result.p_true,
            ci_low=result.ci_low,
            ci_high=result.ci_high,
            significant=abs(result.p_true - stored) >= threshold,
        )
        deltas.append(d)
    deltas.sort(key=lambda x: (-abs(x.delta), x.node_id))
    return deltas


def to_revision_inputs(
    deltas: Sequence[ConfidenceDelta],
    *,
    only_significant: bool = True,
    note: str = "bayesian marginal update",
) -> list[RevisionInput]:
    """Convert significant confidence deltas into cascade ``RevisionInput``s.

    The revision engine's weight is signed in ``[-1, 1]`` — corroborates
    vs contradicts — so a recomputed marginal ``m`` maps to ``2m − 1``: a
    marginal of 1.0 fully corroborates the claim, 0.0 fully contradicts
    it, 0.5 is neutral. The caller then dry-runs ``compute_revision``
    with these inputs to preview the blast radius before committing.
    """
    inputs: list[RevisionInput] = []
    for d in deltas:
        if only_significant and not d.significant:
            continue
        weight = max(-1.0, min(1.0, 2.0 * d.recomputed_marginal - 1.0))
        inputs.append(
            RevisionInput(claim_id=d.node_id, new_evidence=note, weight=weight)
        )
    return inputs


# ── founder UI payload (part E) ─────────────────────────────────────────


def bayesian_view_payload(
    bn: BayesianNetwork,
    node_id: str,
    *,
    evidence: Optional[Evidence] = None,
    top_k: int = 5,
    ci_samples: int = 32,
    importance_samples: int = DEFAULT_IMPORTANCE_SAMPLES,
    seed: int = 0,
) -> dict:
    """The exact payload the founder ``Bayesian view`` tab consumes.

    Mirrors ``theseus-codex/src/lib/bayesianApi.ts``. Bundles the
    node's marginal + credible interval, the inference method (so the UI
    can show the "approximate inference (n=K samples)" caveat for large
    graphs), and the ranked parent sensitivities.
    """
    if node_id not in bn:
        raise KeyError(f"{node_id!r} is not a node in this Bayesian network")
    marginals = infer_marginals(
        bn,
        evidence=evidence,
        ci_samples=ci_samples,
        importance_samples=importance_samples,
        seed=seed,
    )
    result = marginals[node_id]
    parents = most_influential_parents(
        bn, node_id, evidence=evidence, top_k=top_k
    )
    node = bn.nodes[node_id]
    return {
        "node_id": node_id,
        "ref": node.ref,
        "kind": node.kind.value,
        "seeded": node.seeded,
        "marginal": result.p_true,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "method": result.method,
        "exact": result.exact,
        "n_samples": result.n_samples,
        "is_evidence": result.is_evidence,
        "node_count": len(bn),
        "exact_limit": EXACT_NODE_LIMIT,
        "dropped_edge_count": len(bn.dropped_edges),
        "evidence": dict(evidence or {}),
        "parents": [s.to_dict() for s in parents],
    }


__all__ = [
    "EXACT_NODE_LIMIT",
    "DEFAULT_CI_SAMPLES",
    "DEFAULT_IMPORTANCE_SAMPLES",
    "Evidence",
    "MarginalResult",
    "ParentSensitivity",
    "EvidenceUpdate",
    "ConfidenceDelta",
    "marginal",
    "infer_marginals",
    "sensitivity",
    "most_influential_parents",
    "evidence_map",
    "compare_to_stored",
    "to_revision_inputs",
    "bayesian_view_payload",
]
