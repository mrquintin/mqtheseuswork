"""
Bayesian-belief layer — CPT learning.

A freshly built BN (``bayesian_network.build_bn_dag``) carries *seeded*
CPTs: a noisy-OR stipulation derived from cascade weights and source
credibility. A stipulation is a reasonable starting point, but the firm
accumulates ground truth — forecasts resolve, peer reviews land,
retractions arrive — and where it has enough resolved cases for a node,
the CPT should be **fit to that data instead of stipulated**.

This module does exactly that and nothing more:

* :func:`fit_cpt` — fit one node's CPT from resolved cases. Each parent
  assignment ("CPT row") is fit independently; sparse rows are pulled
  toward the no-information midpoint with **Laplace smoothing**, and a
  row with *no* observations keeps its seeded value rather than being
  overwritten by a second guess.
* :func:`learn_network` — apply :func:`fit_cpt` to every node that
  clears ``min_cases_for_fit``, leaving the rest seeded. The returned
  network's nodes carry ``seeded=False`` exactly where a CPT was fit, so
  the founder UI can mark a marginal as data-backed or stipulated.

What learning does *not* touch: DAG structure. Edges come from the
cascade; learning only refines the numbers on the nodes. Re-deriving the
BN from a newer cascade snapshot and re-learning is the supported way to
pick up structural change.

The per-row pseudo-counts a fit produces (``n_true + α``, ``n_false +
α``) flow straight into ``bn_inference``'s credible interval: a row fit
from 200 cases yields a tight interval, a row fit from 3 a wide one.
That is the whole point of carrying counts on the CPT.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from noosphere.inquiry.bayesian_network import (
    BayesianNetwork,
    BNNode,
    ConditionalProbabilityTable,
    _all_assignments,
)

# Laplace (add-α) smoothing strength. α = 1 is the classic "add-one"
# rule: a row observed once True reads 2/3, not 1/1, so a single lucky
# case cannot stipulate certainty.
DEFAULT_LAPLACE_ALPHA = 1.0

# A node needs at least this many resolved cases (weighted) before its
# CPT is fit at all. Below it, the seeded stipulation is still the best
# available estimate and is left in place.
DEFAULT_MIN_CASES_FOR_FIT = 4


@dataclass(frozen=True)
class ResolvedCase:
    """One historical resolution: a node's truth value, with its parents.

    ``parent_assignment`` must cover exactly the node's BN parents.
    ``weight`` ∈ (0, 1] mirrors the credibility ledger's load-bearing
    weight — a case where the node was decisively resolved counts more
    than a marginal one — and enters the counts as a weighted
    pseudo-observation, the same Beta-binomial trick the credibility
    ledger uses.
    """

    node_id: str
    parent_assignment: Mapping[str, bool]
    outcome: bool
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.weight <= 1.0:
            raise ValueError(
                f"ResolvedCase weight must be in (0, 1]; got {self.weight!r}"
            )

    def row_key(self, parents: tuple[str, ...]) -> tuple[bool, ...]:
        """The CPT row this case lands in, for a node with ``parents``."""
        try:
            return tuple(self.parent_assignment[p] for p in parents)
        except KeyError as exc:  # pragma: no cover - caller-data error
            raise ValueError(
                f"ResolvedCase for {self.node_id!r} is missing parent "
                f"{exc.args[0]!r}; it covers {sorted(self.parent_assignment)!r} "
                f"but the node's parents are {list(parents)!r}"
            ) from exc


@dataclass(frozen=True)
class CPTFitReport:
    """Diagnostics for one :func:`fit_cpt` call.

    ``fitted_rows`` / ``seeded_rows`` partition the CPT's rows by whether
    they had ≥1 observation. ``total_weight`` is the weighted case count
    the fit consumed. Surfaced so a founder can see *which* rows of a
    CPT rest on data and which are still stipulated.
    """

    node_id: str
    total_weight: float
    fitted_rows: tuple[tuple[bool, ...], ...]
    seeded_rows: tuple[tuple[bool, ...], ...]

    @property
    def fully_fit(self) -> bool:
        return not self.seeded_rows

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "total_weight": self.total_weight,
            "fitted_rows": [list(r) for r in self.fitted_rows],
            "seeded_rows": [list(r) for r in self.seeded_rows],
            "fully_fit": self.fully_fit,
        }


def fit_cpt(
    node: BNNode,
    cases: Sequence[ResolvedCase],
    *,
    laplace_alpha: float = DEFAULT_LAPLACE_ALPHA,
) -> tuple[ConditionalProbabilityTable, CPTFitReport]:
    """Fit ``node``'s CPT from resolved cases, row by row.

    For each parent assignment, the cases landing in that row contribute
    weighted True/False counts. The row probability is the Laplace-
    smoothed estimate ``(n_true + α) / (n_true + n_false + 2α)``; a row
    with no cases keeps its seeded probability and seeded counts. The
    returned CPT's per-row counts are ``(n_true + α, n_false + α)`` for
    fit rows, which is what gives ``bn_inference`` a data-driven
    credible interval.
    """
    if laplace_alpha <= 0.0:
        raise ValueError(f"laplace_alpha must be positive; got {laplace_alpha!r}")

    parents = node.parents
    relevant = [c for c in cases if c.node_id == node.node_id]

    true_w: dict[tuple[bool, ...], float] = defaultdict(float)
    false_w: dict[tuple[bool, ...], float] = defaultdict(float)
    for case in relevant:
        key = case.row_key(parents)
        if case.outcome:
            true_w[key] += case.weight
        else:
            false_w[key] += case.weight

    probabilities: dict[tuple[bool, ...], float] = {}
    counts: dict[tuple[bool, ...], tuple[float, float]] = {}
    fitted: list[tuple[bool, ...]] = []
    seeded: list[tuple[bool, ...]] = []
    total_weight = 0.0

    for assignment in _all_assignments(len(parents)):
        nt = true_w.get(assignment, 0.0)
        nf = false_w.get(assignment, 0.0)
        observed = nt + nf
        if observed <= 0.0:
            # No data for this row — keep the stipulation rather than
            # overwriting one guess with a flat 0.5.
            probabilities[assignment] = node.cpt.p_true(assignment)
            existing = node.cpt.row_counts(assignment)
            if existing is not None:
                counts[assignment] = existing
            seeded.append(assignment)
            continue
        total_weight += observed
        alpha = nt + laplace_alpha
        beta = nf + laplace_alpha
        probabilities[assignment] = alpha / (alpha + beta)
        counts[assignment] = (alpha, beta)
        fitted.append(assignment)

    cpt = node.cpt.with_probabilities(probabilities, counts)
    report = CPTFitReport(
        node_id=node.node_id,
        total_weight=total_weight,
        fitted_rows=tuple(fitted),
        seeded_rows=tuple(seeded),
    )
    return cpt, report


@dataclass
class LearnedNetwork:
    """Result of :func:`learn_network`.

    ``network`` is the refined BN; ``reports`` holds a :class:`CPTFitReport`
    for every node that was fit (nodes left seeded are absent). ``network``
    nodes carry ``seeded=False`` exactly where a fit happened.
    """

    network: BayesianNetwork
    reports: dict[str, CPTFitReport] = field(default_factory=dict)

    @property
    def fitted_node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.reports))

    def to_dict(self) -> dict:
        return {
            "node_count": len(self.network),
            "fitted_node_ids": list(self.fitted_node_ids),
            "reports": {nid: r.to_dict() for nid, r in self.reports.items()},
        }


def group_cases_by_node(
    cases: Sequence[ResolvedCase],
) -> dict[str, list[ResolvedCase]]:
    """Bucket resolved cases by the node they resolve."""
    grouped: dict[str, list[ResolvedCase]] = defaultdict(list)
    for case in cases:
        grouped[case.node_id].append(case)
    return dict(grouped)


def learn_network(
    bn: BayesianNetwork,
    cases: Sequence[ResolvedCase],
    *,
    laplace_alpha: float = DEFAULT_LAPLACE_ALPHA,
    min_cases_for_fit: float = DEFAULT_MIN_CASES_FOR_FIT,
) -> LearnedNetwork:
    """Fit every node's CPT that clears ``min_cases_for_fit``; leave the rest.

    The threshold is on *weighted* case count, so ten 0.3-weight cases
    count the same as three full-weight ones. Nodes below the threshold
    keep their seeded CPT and ``seeded=True``; nodes at or above it are
    refit and marked ``seeded=False``. Structure is never touched — a new
    :class:`BayesianNetwork` is returned with the same nodes and edges.
    """
    grouped = group_cases_by_node(cases)
    new_nodes: dict[str, BNNode] = {}
    reports: dict[str, CPTFitReport] = {}

    for node_id, node in bn.nodes.items():
        node_cases = grouped.get(node_id, [])
        total_weight = sum(c.weight for c in node_cases)
        if total_weight < min_cases_for_fit:
            new_nodes[node_id] = node
            continue
        cpt, report = fit_cpt(node, node_cases, laplace_alpha=laplace_alpha)
        new_nodes[node_id] = BNNode(
            node_id=node.node_id,
            ref=node.ref,
            kind=node.kind,
            parents=node.parents,
            cpt=cpt,
            seeded=False,
        )
        reports[node_id] = report

    learned = BayesianNetwork(nodes=new_nodes, dropped_edges=bn.dropped_edges)
    return LearnedNetwork(network=learned, reports=reports)


__all__ = [
    "DEFAULT_LAPLACE_ALPHA",
    "DEFAULT_MIN_CASES_FOR_FIT",
    "ResolvedCase",
    "CPTFitReport",
    "LearnedNetwork",
    "fit_cpt",
    "group_cases_by_node",
    "learn_network",
]
