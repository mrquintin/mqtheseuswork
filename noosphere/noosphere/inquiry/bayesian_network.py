"""
Bayesian-belief layer over the cascade graph — DAG construction.

The cascade weights conclusions by ``source credibility × edge weight``,
but that algebra is ad-hoc: it pools evidence with a noisy-OR and a
credibility cap, and the result is a *score*, not a probability you can
condition on. The Bayesian layer is a **derived view** that gives the
firm a principled object instead: a directed acyclic graph of
binary truth-valued nodes (one per Claim / Conclusion / Principle) with
explicit conditional probability tables (CPTs), over which marginal
probabilities and evidence updates are well-defined.

Three things this module is *not*:

* **Not a replacement for the cascade.** The cascade remains the
  primary representation. The BN is rebuilt from a cascade snapshot on
  demand (``build_bn_dag``); nothing here writes back to the graph.
* **Not public.** Marginal probabilities are a founder-side tool. They
  are surfaced behind the founder ``Bayesian view`` tab and are not
  rendered on a public article without founder review.
* **Not the inference engine.** Construction lives here; inference
  (variable elimination / importance sampling), evidence conditioning,
  and sensitivity analysis live in ``bn_inference``; CPT learning lives
  in ``bn_learning``.

Construction pipeline
---------------------
``build_bn_dag(store)``:

1. Asks the cascade for its **Bayesian skeleton**
   (``noosphere.cascade.graph.build_bayesian_skeleton``): an acyclic
   set of truth-valued nodes and the evidence edges between them. The
   cascade owns the cycle-break because cycle-freeness is a property of
   the cascade graph, not of the BN.
2. Aggregates the parent edges of each node into a single **signed
   effective weight** per parent — positive for supporting relations,
   negative for refuting ones, scaled by the cascade edge confidence
   and (optionally) the parent source's credibility posterior.
3. **Seeds a CPT** for each node with a noisy-OR / noisy-AND-style
   parameterisation of those weights. Seeded CPTs carry a *weak*
   pseudo-count prior, so the credible interval on any marginal derived
   from a purely-seeded network is honestly wide. ``bn_learning`` later
   replaces seeded rows with data-fit rows where the firm has enough
   resolved cases.

CPT representation
------------------
Every node is binary. A node with ``k`` parents has a CPT with ``2**k``
rows; each row gives ``P(node = True | parent assignment)`` plus a
``(alpha, beta)`` pseudo-count pair that drives the credible interval.
The table is *total* — every parent assignment is present — which is
what makes exact inference straightforward.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence

from noosphere.models import CascadeEdgeRelation, CascadeNodeKind

# Re-exported so callers can stay inside ``inquiry`` for the kind set.
from noosphere.cascade.graph import (  # noqa: F401  (intentional re-export)
    BN_PROJECTED_RELATIONS,
    BN_TRUTH_NODE_KINDS,
    build_bayesian_skeleton,
)

# ── tunables ────────────────────────────────────────────────────────────

# P(node = True) for a node with no *active* parent. A claim with no
# surviving evidence basis sits at the "no information" midpoint, which
# matches the cascade revision engine's treatment of a basis-free node.
DEFAULT_LEAK = 0.5

# Pseudo-count strength of a *seeded* (stipulated) CPT row. Deliberately
# small: a seeded row is a guess, and the credible interval should say
# so until ``bn_learning`` folds in real resolved cases. A row fit to
# data carries pseudo-counts equal to the data volume instead.
SEED_PSEUDO_COUNT = 2.0

# CPT entries are clamped away from exactly 0/1 so log-space inference
# and Beta posteriors stay well-defined.
_EPS = 1e-4

# Per-relation factor applied to a cascade edge's confidence when it
# becomes a BN parent edge. Sign carries the direction (supporting vs
# refuting); magnitude mirrors the revision engine's ``_RELATION_WEIGHT``
# so the two layers rank evidence the same way.
_RELATION_FACTOR: dict[CascadeEdgeRelation, float] = {
    CascadeEdgeRelation.SUPPORTS: 1.0,
    CascadeEdgeRelation.EXTRACTED_FROM: 1.0,
    CascadeEdgeRelation.AGGREGATES: 1.0,
    CascadeEdgeRelation.DEPENDS_ON: 1.0,
    CascadeEdgeRelation.REFORMULATES: 0.7,
    CascadeEdgeRelation.SPECIALIZES: 0.7,
    CascadeEdgeRelation.GENERALIZES: 0.5,
    CascadeEdgeRelation.COHERES_WITH: 0.5,
    CascadeEdgeRelation.PREDICTS: 0.5,
    CascadeEdgeRelation.REFUTES: -1.0,
    CascadeEdgeRelation.CONTRADICTS: -1.0,
}


def _clamp_prob(p: float) -> float:
    if p < _EPS:
        return _EPS
    if p > 1.0 - _EPS:
        return 1.0 - _EPS
    return p


def _all_assignments(k: int) -> list[tuple[bool, ...]]:
    """Every binary assignment over ``k`` parents, in a stable order."""
    return list(itertools.product((False, True), repeat=k))


# ── conditional probability table ───────────────────────────────────────


@dataclass(frozen=True)
class ConditionalProbabilityTable:
    """``P(node = True | parents)`` for one binary node.

    ``probabilities`` is keyed by a tuple of bools aligned positionally
    with ``parents``; it must be *total* (all ``2**k`` assignments
    present). ``counts`` is the per-row ``(alpha, beta)`` Beta
    pseudo-count pair: a seeded row carries a weak prior, a learned row
    carries the resolved-case counts. ``counts`` may be empty, in which
    case the row is treated as *certain* (no CPT uncertainty) — useful
    for analytic test fixtures.
    """

    node_id: str
    parents: tuple[str, ...]
    probabilities: Mapping[tuple[bool, ...], float]
    counts: Mapping[tuple[bool, ...], tuple[float, float]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        k = len(self.parents)
        expected = set(_all_assignments(k))
        got = set(self.probabilities)
        if got != expected:
            raise ValueError(
                f"CPT for {self.node_id!r} must be total over {len(expected)} "
                f"parent assignments; got {len(got)} "
                f"(missing={sorted(expected - got)!r}, extra={sorted(got - expected)!r})"
            )
        for assignment, p in self.probabilities.items():
            if not 0.0 <= p <= 1.0:
                raise ValueError(
                    f"CPT for {self.node_id!r} row {assignment!r}: "
                    f"probability {p!r} outside [0, 1]"
                )
        for assignment, ab in self.counts.items():
            if assignment not in expected:
                raise ValueError(
                    f"CPT for {self.node_id!r}: counts row {assignment!r} "
                    f"is not a valid parent assignment"
                )
            a, b = ab
            if a <= 0.0 or b <= 0.0:
                raise ValueError(
                    f"CPT for {self.node_id!r} row {assignment!r}: "
                    f"pseudo-counts must be positive; got {ab!r}"
                )

    # — row access —

    def p_true(self, assignment: tuple[bool, ...]) -> float:
        return self.probabilities[tuple(assignment)]

    def p_false(self, assignment: tuple[bool, ...]) -> float:
        return 1.0 - self.probabilities[tuple(assignment)]

    def row_counts(
        self, assignment: tuple[bool, ...]
    ) -> Optional[tuple[float, float]]:
        return self.counts.get(tuple(assignment))

    # — derived tables —

    def resample(
        self, beta_sampler: Callable[[float, float], float]
    ) -> "ConditionalProbabilityTable":
        """A CPT with each row's probability drawn from its Beta posterior.

        Rows with no ``counts`` entry are treated as certain and keep
        their point probability. ``beta_sampler(alpha, beta)`` is
        supplied by the inference engine (it owns the RNG, so the draw
        stays reproducible under a fixed seed).
        """
        if not self.counts:
            return self
        sampled: dict[tuple[bool, ...], float] = {}
        for assignment, p in self.probabilities.items():
            ab = self.counts.get(assignment)
            if ab is None:
                sampled[assignment] = p
            else:
                sampled[assignment] = _clamp_prob(beta_sampler(ab[0], ab[1]))
        return ConditionalProbabilityTable(
            node_id=self.node_id,
            parents=self.parents,
            probabilities=sampled,
            counts=dict(self.counts),
        )

    def with_probabilities(
        self,
        probabilities: Mapping[tuple[bool, ...], float],
        counts: Optional[Mapping[tuple[bool, ...], tuple[float, float]]] = None,
    ) -> "ConditionalProbabilityTable":
        """A copy with replaced rows — used by ``bn_learning`` to swap a
        seeded table for a data-fit one without touching structure."""
        return ConditionalProbabilityTable(
            node_id=self.node_id,
            parents=self.parents,
            probabilities=dict(probabilities),
            counts=dict(counts) if counts is not None else dict(self.counts),
        )

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "parents": list(self.parents),
            "rows": [
                {
                    "assignment": list(assignment),
                    "p_true": self.probabilities[assignment],
                    "counts": list(self.counts[assignment])
                    if assignment in self.counts
                    else None,
                }
                for assignment in _all_assignments(len(self.parents))
            ],
        }

    # — constructors —

    @classmethod
    def root(
        cls,
        node_id: str,
        p_true: float,
        *,
        strength: Optional[float] = SEED_PSEUDO_COUNT,
    ) -> "ConditionalProbabilityTable":
        """A parent-free CPT — i.e. a prior ``P(node = True)``."""
        p = _clamp_prob(p_true)
        counts: dict[tuple[bool, ...], tuple[float, float]] = {}
        if strength is not None and strength > 0.0:
            counts[()] = (p * strength, (1.0 - p) * strength)
        return cls(
            node_id=node_id,
            parents=(),
            probabilities={(): p},
            counts=counts,
        )


# ── BN node + network ───────────────────────────────────────────────────


@dataclass(frozen=True)
class BNNode:
    """One binary truth-valued node in the Bayesian DAG.

    ``seeded`` is ``True`` while the CPT is the stipulated noisy-OR seed
    and ``False`` once ``bn_learning`` has fit it to resolved cases. The
    founder UI surfaces this so a reader knows whether a marginal rests
    on a guess or on data.
    """

    node_id: str
    ref: str
    kind: CascadeNodeKind
    parents: tuple[str, ...]
    cpt: ConditionalProbabilityTable
    seeded: bool = True

    def __post_init__(self) -> None:
        if self.cpt.node_id != self.node_id:
            raise ValueError(
                f"BNNode {self.node_id!r} carries a CPT for "
                f"{self.cpt.node_id!r}"
            )
        if self.cpt.parents != self.parents:
            raise ValueError(
                f"BNNode {self.node_id!r}: parents {self.parents!r} "
                f"disagree with CPT parents {self.cpt.parents!r}"
            )

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "ref": self.ref,
            "kind": self.kind.value,
            "parents": list(self.parents),
            "seeded": self.seeded,
            "cpt": self.cpt.to_dict(),
        }


@dataclass
class BayesianNetwork:
    """A derived Bayesian DAG over a cascade snapshot.

    ``dropped_edges`` records cascade edge ids the skeleton step had to
    drop to keep the projection acyclic — surfaced so a founder can see
    which evidence link was excluded rather than silently losing it.
    """

    nodes: dict[str, BNNode]
    dropped_edges: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Validate that every parent reference resolves — a dangling
        # parent would silently corrupt inference.
        for node in self.nodes.values():
            for parent in node.parents:
                if parent not in self.nodes:
                    raise ValueError(
                        f"BN node {node.node_id!r} names parent "
                        f"{parent!r} which is not in the network"
                    )
        self._children: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for node in self.nodes.values():
            for parent in node.parents:
                self._children[parent].append(node.node_id)
        for kids in self._children.values():
            kids.sort()
        # Fail fast on a cyclic construction — ``build_bn_dag`` cannot
        # produce one (the skeleton is acyclic) but a hand-built network
        # could, and inference assumes a DAG.
        self._order = self._compute_topological_order()

    def __len__(self) -> int:
        return len(self.nodes)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.nodes

    def __iter__(self):
        return iter(self.nodes.values())

    def parents_of(self, node_id: str) -> tuple[str, ...]:
        return self.nodes[node_id].parents

    def children_of(self, node_id: str) -> list[str]:
        return list(self._children.get(node_id, ()))

    def topological_order(self) -> list[str]:
        """Node ids parents-before-children; ties broken lexically."""
        return list(self._order)

    def _compute_topological_order(self) -> list[str]:
        indegree = {nid: len(node.parents) for nid, node in self.nodes.items()}
        ready = sorted(nid for nid, d in indegree.items() if d == 0)
        order: list[str] = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            newly_ready: list[str] = []
            for child in self._children.get(nid, ()):
                indegree[child] -= 1
                if indegree[child] == 0:
                    newly_ready.append(child)
            for child in sorted(newly_ready):
                # insertion-sort into ``ready`` to keep lexical order
                lo, hi = 0, len(ready)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if ready[mid] < child:
                        lo = mid + 1
                    else:
                        hi = mid
                ready.insert(lo, child)
        if len(order) != len(self.nodes):
            raise ValueError(
                "BayesianNetwork is cyclic — a Bayesian network must be a DAG"
            )
        return order

    def to_dict(self) -> dict:
        return {
            "node_count": len(self.nodes),
            "dropped_edges": list(self.dropped_edges),
            "topological_order": self.topological_order(),
            "nodes": [
                self.nodes[nid].to_dict() for nid in self.topological_order()
            ],
        }


# ── CPT seeding ─────────────────────────────────────────────────────────


def _aggregate_parent_weight(
    edge_factors: Sequence[float],
) -> float:
    """Combine one parent's (possibly multiple) edges into a signed weight.

    A parent can reach a child by more than one relation (e.g. ``supports``
    *and* ``coheres_with``). Same-sign contributions pool via noisy-OR —
    two corroborating links are stronger than either alone — and the
    positive and negative pools then net against each other. The result
    is a single signed weight in roughly ``[-1, 1]``.
    """
    pos = 1.0
    neg = 1.0
    for f in edge_factors:
        if f > 0.0:
            pos *= 1.0 - min(f, 1.0)
        elif f < 0.0:
            neg *= 1.0 - min(-f, 1.0)
    positive_mass = 1.0 - pos
    negative_mass = 1.0 - neg
    return positive_mass - negative_mass


def seed_cpt(
    node_id: str,
    parent_weights: Mapping[str, float],
    *,
    leak: float = DEFAULT_LEAK,
) -> ConditionalProbabilityTable:
    """Stipulate a CPT from signed parent weights with a noisy-OR seed.

    ``parent_weights`` maps each parent id to a signed effective weight
    in ``[-1, 1]`` (positive = corroborating, negative = refuting). For a
    given parent assignment:

    * supporting parents that are *active* (True) contribute to a
      noisy-OR ``positive_mass``;
    * refuting parents that are active contribute to a noisy-OR
      ``negative_mass``;
    * the row probability is
      ``(leak + positive_mass · (1 − leak)) · (1 − negative_mass)``,

    which reduces to ``leak`` when no parent is active, climbs toward 1
    as supporting parents fire, and is dragged toward 0 by refuting
    parents. Every row carries a weak ``SEED_PSEUDO_COUNT`` prior so the
    credible interval is honest about this being a stipulation.
    """
    leak = _clamp_prob(leak)
    parents = tuple(sorted(parent_weights))
    probabilities: dict[tuple[bool, ...], float] = {}
    counts: dict[tuple[bool, ...], tuple[float, float]] = {}
    for assignment in _all_assignments(len(parents)):
        pos = 1.0
        neg = 1.0
        for parent, active in zip(parents, assignment):
            if not active:
                continue
            w = parent_weights[parent]
            if w > 0.0:
                pos *= 1.0 - min(w, 1.0)
            elif w < 0.0:
                neg *= 1.0 - min(-w, 1.0)
        positive_mass = 1.0 - pos
        negative_mass = 1.0 - neg
        p_on = (leak + positive_mass * (1.0 - leak)) * (1.0 - negative_mass)
        p_on = _clamp_prob(p_on)
        probabilities[assignment] = p_on
        counts[assignment] = (
            p_on * SEED_PSEUDO_COUNT,
            (1.0 - p_on) * SEED_PSEUDO_COUNT,
        )
    return ConditionalProbabilityTable(
        node_id=node_id,
        parents=parents,
        probabilities=probabilities,
        counts=counts,
    )


# ── DAG construction from the cascade ───────────────────────────────────

# A credibility lookup maps a node id (the *source* end of a parent
# edge) to its credibility posterior mean in [0, 1]. Production wires
# this to the source-credibility ledger
# (``noosphere.literature.source_credibility``); tests can pass a plain
# dict or omit it entirely.
CredibilityLookup = Mapping[str, float]


def _edge_factor(
    relation_value: str,
    confidence: float,
    src: str,
    credibility: Optional[CredibilityLookup],
) -> float:
    """Signed effective weight of one cascade edge as a BN parent edge.

    ``confidence`` is the cascade edge's base assertion strength. It is
    scaled by the per-relation factor (sign + magnitude) and, when the
    source is known to the credibility ledger, by the source's
    posterior mean — exactly the modulation the cascade already applies
    to ``supports`` edges, lifted into the BN seed.
    """
    try:
        relation = CascadeEdgeRelation(relation_value)
    except ValueError:
        return 0.0
    factor = _RELATION_FACTOR.get(relation, 0.0)
    base = max(0.0, min(1.0, confidence))
    weight = base * factor
    if credibility is not None and src in credibility:
        weight *= max(0.0, min(1.0, credibility[src]))
    return weight


def build_bn_dag_from_skeleton(
    skeleton: dict,
    *,
    credibility: Optional[CredibilityLookup] = None,
    leak: float = DEFAULT_LEAK,
) -> BayesianNetwork:
    """Build a :class:`BayesianNetwork` from a cascade Bayesian skeleton.

    ``skeleton`` is the dict returned by
    ``noosphere.cascade.graph.build_bayesian_skeleton`` /
    ``CascadeGraph.bayesian_skeleton``. Split out from
    :func:`build_bn_dag` so tests (and callers that already hold a
    skeleton) need no live store.
    """
    node_meta: dict[str, tuple[str, CascadeNodeKind]] = {}
    for node_id, ref, kind_value in skeleton["nodes"]:
        node_meta[node_id] = (ref, CascadeNodeKind(kind_value))

    # Collect, per child, the list of signed edge factors keyed by parent.
    parent_factors: dict[str, dict[str, list[float]]] = {
        nid: {} for nid in node_meta
    }
    for edge_id, src, dst, relation_value, confidence in skeleton["edges"]:
        if src not in node_meta or dst not in node_meta:
            continue
        factor = _edge_factor(relation_value, confidence, src, credibility)
        parent_factors[dst].setdefault(src, []).append(factor)

    nodes: dict[str, BNNode] = {}
    for node_id, (ref, kind) in node_meta.items():
        per_parent = parent_factors[node_id]
        parent_weights: dict[str, float] = {
            parent: _aggregate_parent_weight(factors)
            for parent, factors in per_parent.items()
        }
        cpt = seed_cpt(node_id, parent_weights, leak=leak)
        nodes[node_id] = BNNode(
            node_id=node_id,
            ref=ref,
            kind=kind,
            parents=cpt.parents,
            cpt=cpt,
            seeded=True,
        )

    return BayesianNetwork(
        nodes=nodes,
        dropped_edges=tuple(skeleton.get("dropped_edge_ids", ())),
    )


def build_bn_dag(
    store,  # noqa: ANN001
    *,
    credibility: Optional[CredibilityLookup] = None,
    leak: float = DEFAULT_LEAK,
    truth_kinds: frozenset[CascadeNodeKind] = BN_TRUTH_NODE_KINDS,
) -> BayesianNetwork:
    """Derive a Bayesian DAG from a live cascade store.

    The cascade is *not* mutated — this is a read-only projection. Call
    it again to pick up graph changes; the BN is cheap to rebuild and
    deliberately holds no state of its own.

    ``credibility`` optionally maps a source node id to its
    credibility-posterior mean (see
    ``noosphere.literature.source_credibility``); when supplied, parent
    edges from low-credibility sources seed weaker CPT rows.
    """
    skeleton = build_bayesian_skeleton(store, truth_kinds=truth_kinds)
    return build_bn_dag_from_skeleton(
        skeleton, credibility=credibility, leak=leak
    )


__all__ = [
    "DEFAULT_LEAK",
    "SEED_PSEUDO_COUNT",
    "BN_PROJECTED_RELATIONS",
    "BN_TRUTH_NODE_KINDS",
    "ConditionalProbabilityTable",
    "BNNode",
    "BayesianNetwork",
    "CredibilityLookup",
    "seed_cpt",
    "build_bn_dag",
    "build_bn_dag_from_skeleton",
    "build_bayesian_skeleton",
]
