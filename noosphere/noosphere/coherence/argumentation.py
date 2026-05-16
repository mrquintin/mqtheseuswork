"""
Coherence layer 2 — Dung-style abstract argumentation on a micro framework.
"""

# DEPRECATED — replaced by contradiction_engine.py in Round 19 prompt 06.
# Slated for removal in prompt 16. New contradiction detection MUST route
# through ContradictionEngine; this module is kept only as a compat shim
# for legacy regression tests that still reference the layer-2 heuristic.

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable

try:
    import networkx as nx
except ImportError:  # pragma: no cover - exercised in minimal local envs.
    class _MiniDiGraph:
        def __init__(self) -> None:
            self._nodes: set[str] = set()
            self._edges: set[tuple[str, str]] = set()

        def add_node(self, node: str) -> None:
            self._nodes.add(node)

        def add_edge(self, source: str, target: str) -> None:
            self._nodes.add(source)
            self._nodes.add(target)
            self._edges.add((source, target))

        def has_edge(self, source: str, target: str) -> bool:
            return (source, target) in self._edges

    class _MiniNetworkX:
        DiGraph = _MiniDiGraph

    nx = _MiniNetworkX()  # type: ignore[assignment]

from noosphere.models import Claim
from noosphere.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ArgumentationResult:
    jointly_acceptable: bool
    preferred_extension_size: int
    attack_edges: list[tuple[str, str]] = field(default_factory=list)


def _conflict(a: Claim, b: Claim, nli_contradiction: float) -> bool:
    return nli_contradiction > 0.55


def evaluate_pair_with_neighbors(
    target_a: Claim,
    target_b: Claim,
    neighbors: Iterable[Claim],
    neighbor_contra_scores: dict[tuple[str, str], float],
) -> ArgumentationResult:
    """
    Build AF: nodes = {a,b} ∪ neighbors; attack if pairwise contradiction score high.
    Preferred semantics: preferred extension (maximal admissible) — approximated via maximal conflict-free sets.
    """
    nodes: list[Claim] = [target_a, target_b] + list(neighbors)
    ids = [c.id for c in nodes]
    G = nx.DiGraph()
    for cid in ids:
        G.add_node(cid)
    attacks: list[tuple[str, str]] = []
    for c1, c2 in combinations(nodes, 2):
        key = (c1.id, c2.id)
        keyr = (c2.id, c1.id)
        score = neighbor_contra_scores.get(key) or neighbor_contra_scores.get(keyr) or 0.0
        if _conflict(c1, c2, score):
            G.add_edge(c1.id, c2.id)
            G.add_edge(c2.id, c1.id)
            attacks.append((c1.id, c2.id))
    # Maximal conflict-free sets containing both targets
    import itertools

    acceptable = False
    best_size = 0
    for r in range(len(ids), 1, -1):
        for subset in itertools.combinations(ids, r):
            if target_a.id not in subset or target_b.id not in subset:
                continue
            ok = True
            for u, v in itertools.combinations(subset, 2):
                if G.has_edge(u, v) or G.has_edge(v, u):
                    ok = False
                    break
            if ok:
                acceptable = True
                best_size = max(best_size, r)
                break
        if acceptable:
            break
    return ArgumentationResult(
        jointly_acceptable=acceptable,
        preferred_extension_size=best_size,
        attack_edges=attacks,
    )
