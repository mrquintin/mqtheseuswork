"""Anchor curation for ``DomainBound`` anchor centroids.

Given a corpus of conclusions historically labeled in-domain for a method
(by a human or by past LLM judgments), this module proposes a small set
of ``k`` centroids that summarize the embedding region the method is
allowed to operate in. The technique is k-medoids (PAM, the simple swap
variant) because medoids are *real points from the corpus* — a curator
can read the conclusion text behind each anchor and decide whether it
truly represents an in-domain prototype before accepting the proposal.

Nothing here auto-commits. The CLI prints the proposal as a
``ProposedAnchorRevision`` blob; the human edits it (drop bad anchors,
adjust the radius, set the model id) and writes the final
``AnchorBound`` into the method's declaration. Re-curation produces a
new revision rather than mutating the prior one — older conclusions
keep the verdict that was true under the anchors that were active when
they ran.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from noosphere.methods.domain_bounds import angular_cosine_distance


# ── Inputs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CandidateConclusion:
    """One historically in-domain conclusion. ``conclusion_id`` is opaque
    to this module; the caller resolves text/embedding from its store."""

    conclusion_id: str
    embedding: tuple[float, ...]


# ── Outputs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProposedAnchorRevision:
    """A draft anchor revision. The CLI prints this; the human accepts or
    edits it before it is wired into a method's ``DomainBound``."""

    method_name: str
    embedding_model: str
    k: int
    medoid_ids: tuple[str, ...]
    medoid_vectors: tuple[tuple[float, ...], ...]
    suggested_in_radius: float
    suggested_edge_radius: float
    revision_id: str
    coverage: float = 0.0
    cluster_sizes: tuple[int, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "embedding_model": self.embedding_model,
            "k": self.k,
            "medoid_ids": list(self.medoid_ids),
            "medoid_vectors": [list(v) for v in self.medoid_vectors],
            "suggested_in_radius": round(self.suggested_in_radius, 6),
            "suggested_edge_radius": round(self.suggested_edge_radius, 6),
            "revision_id": self.revision_id,
            "coverage": round(self.coverage, 6),
            "cluster_sizes": list(self.cluster_sizes),
        }


# ── k-medoids ──────────────────────────────────────────────────────────────


def _pairwise_distance(
    candidates: Sequence[CandidateConclusion],
) -> list[list[float]]:
    n = len(candidates)
    d: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            v = angular_cosine_distance(
                candidates[i].embedding, candidates[j].embedding
            )
            d[i][j] = v
            d[j][i] = v
    return d


def _initial_medoids(d: list[list[float]], k: int, seed: int) -> list[int]:
    """Deterministic k-medoids++ seeding: pick the point with smallest sum
    of distances first, then repeatedly add the point that is farthest
    (max-min) from the current medoid set."""
    n = len(d)
    sums = [sum(row) for row in d]
    first = min(range(n), key=lambda i: (sums[i], i))
    medoids = [first]
    rng = random.Random(seed)
    while len(medoids) < k:
        best_i = -1
        best_min_d = -1.0
        for i in range(n):
            if i in medoids:
                continue
            min_d = min(d[i][m] for m in medoids)
            # Tie-break by index so the algorithm stays deterministic.
            if (min_d > best_min_d) or (
                math.isclose(min_d, best_min_d) and (best_i < 0 or i < best_i)
            ):
                best_min_d = min_d
                best_i = i
        if best_i < 0:
            # Fallback (every point already a medoid — only when k >= n).
            remaining = [i for i in range(n) if i not in medoids]
            if not remaining:
                break
            best_i = rng.choice(remaining)
        medoids.append(best_i)
    return medoids


def _assign(d: list[list[float]], medoids: list[int]) -> tuple[list[int], float]:
    """Return (assignment, total_cost) where assignment[i] is the index
    into ``medoids`` of the closest medoid for candidate i."""
    n = len(d)
    assignment = [0] * n
    cost = 0.0
    for i in range(n):
        best_m = 0
        best_d = d[i][medoids[0]]
        for mi in range(1, len(medoids)):
            dd = d[i][medoids[mi]]
            if dd < best_d:
                best_d = dd
                best_m = mi
        assignment[i] = best_m
        cost += best_d
    return assignment, cost


def _kmedoids(
    d: list[list[float]], k: int, *, seed: int, max_iter: int = 64
) -> tuple[list[int], list[int]]:
    """PAM-style swap k-medoids on a precomputed distance matrix.

    Returns ``(medoids, assignment)``. Deterministic given the same
    seed and inputs."""
    n = len(d)
    if k <= 0:
        raise ValueError("k must be >= 1")
    if k >= n:
        return list(range(n)), list(range(n))

    medoids = _initial_medoids(d, k, seed=seed)
    assignment, current_cost = _assign(d, medoids)

    for _ in range(max_iter):
        improved = False
        # For each cluster, try replacing its medoid with each cluster
        # member that lowers the within-cluster total distance. This is
        # the cheap PAM variant ("alternating") — sufficient because we
        # use it only as a starting proposal for a human curator.
        for mi in range(len(medoids)):
            members = [i for i in range(n) if assignment[i] == mi]
            if not members:
                continue
            best_candidate = medoids[mi]
            best_within = sum(d[i][medoids[mi]] for i in members)
            for cand in members:
                if cand == medoids[mi]:
                    continue
                within = sum(d[i][cand] for i in members)
                if within < best_within - 1e-12:
                    best_within = within
                    best_candidate = cand
            if best_candidate != medoids[mi]:
                medoids[mi] = best_candidate
                improved = True
        new_assignment, new_cost = _assign(d, medoids)
        if not improved or new_cost >= current_cost - 1e-12:
            return medoids, new_assignment
        assignment, current_cost = new_assignment, new_cost
    return medoids, assignment


# ── Radius proposal ────────────────────────────────────────────────────────


def _suggested_radius(
    d: list[list[float]],
    medoids: list[int],
    assignment: list[int],
    *,
    in_quantile: float = 0.90,
    edge_quantile: float = 0.98,
) -> tuple[float, float]:
    """Pick ``in_radius`` at the configured quantile of within-cluster
    distances and ``edge_radius`` at a wider quantile. Empirical
    quantiles, not parametric — methods rarely have enough labeled
    examples for a parametric fit."""
    in_distances: list[float] = []
    for i, mi in enumerate(assignment):
        in_distances.append(d[i][medoids[mi]])
    if not in_distances:
        return 0.25, 0.35
    in_distances.sort()
    in_radius = _quantile(in_distances, in_quantile)
    edge_radius = max(in_radius, _quantile(in_distances, edge_quantile))
    # Guard against a degenerate cluster (all points equal a medoid).
    if in_radius < 1e-6:
        in_radius = 0.05
    if edge_radius < in_radius:
        edge_radius = min(1.0, in_radius * 1.25)
    return float(in_radius), float(min(1.0, edge_radius))


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


# ── Public API ─────────────────────────────────────────────────────────────


def propose_anchors(
    *,
    method_name: str,
    embedding_model: str,
    candidates: Iterable[CandidateConclusion],
    k: int,
    seed: int = 0,
    in_quantile: float = 0.90,
    edge_quantile: float = 0.98,
) -> ProposedAnchorRevision:
    """Run k-medoids on ``candidates`` and propose an anchor revision.

    The resulting proposal is *not* wired into the method automatically.
    The CLI prints it; a human reviews the medoid IDs (so they can
    inspect each prototype conclusion's text), edits the radii if
    needed, and explicitly accepts it. Acceptance produces a fresh
    ``AnchorBound`` keyed by the proposal's ``revision_id``."""
    cands = list(candidates)
    if not cands:
        raise ValueError("propose_anchors: at least one candidate required")
    if k < 1:
        raise ValueError("propose_anchors: k must be >= 1")

    dim = len(cands[0].embedding)
    for c in cands:
        if len(c.embedding) != dim:
            raise ValueError(
                f"propose_anchors: embedding dim mismatch on {c.conclusion_id}"
            )

    d = _pairwise_distance(cands)
    medoids, assignment = _kmedoids(d, k, seed=seed)
    in_radius, edge_radius = _suggested_radius(
        d, medoids, assignment, in_quantile=in_quantile, edge_quantile=edge_quantile
    )

    medoid_ids = tuple(cands[m].conclusion_id for m in medoids)
    medoid_vecs = tuple(tuple(cands[m].embedding) for m in medoids)

    cluster_sizes = [0] * len(medoids)
    for mi in assignment:
        cluster_sizes[mi] += 1

    # Coverage = fraction of candidates whose nearest medoid is within
    # the suggested in_radius. A low coverage means the proposed
    # in_radius is too tight for this corpus and the curator should
    # widen it (or split into more anchors).
    covered = 0
    for i in range(len(cands)):
        if d[i][medoids[assignment[i]]] <= in_radius:
            covered += 1
    coverage = covered / len(cands)

    revision_id = _proposal_revision_id(
        method_name=method_name,
        embedding_model=embedding_model,
        medoid_vecs=medoid_vecs,
        in_radius=in_radius,
        edge_radius=edge_radius,
    )

    return ProposedAnchorRevision(
        method_name=method_name,
        embedding_model=embedding_model,
        k=len(medoids),
        medoid_ids=medoid_ids,
        medoid_vectors=medoid_vecs,
        suggested_in_radius=in_radius,
        suggested_edge_radius=edge_radius,
        revision_id=revision_id,
        coverage=coverage,
        cluster_sizes=tuple(cluster_sizes),
    )


def _proposal_revision_id(
    *,
    method_name: str,
    embedding_model: str,
    medoid_vecs: tuple[tuple[float, ...], ...],
    in_radius: float,
    edge_radius: float,
) -> str:
    payload = json.dumps(
        {
            "method": method_name,
            "model": embedding_model,
            "medoids": [list(v) for v in medoid_vecs],
            "in_radius": round(in_radius, 8),
            "edge_radius": round(edge_radius, 8),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "rev_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def to_anchor_bound_dict(
    proposal: ProposedAnchorRevision,
    *,
    in_radius: Optional[float] = None,
    edge_radius: Optional[float] = None,
) -> dict[str, Any]:
    """Convert a (possibly human-edited) proposal into the dict form that
    ``load_domain_bound`` accepts. The curator may override the radii
    here — the revision_id is preserved verbatim so downstream consumers
    can match it to the proposal record."""
    return {
        "anchors": [list(v) for v in proposal.medoid_vectors],
        "embedding_model": proposal.embedding_model,
        "in_radius": float(in_radius if in_radius is not None else proposal.suggested_in_radius),
        "edge_radius": float(
            edge_radius if edge_radius is not None else proposal.suggested_edge_radius
        ),
        "revision_id": proposal.revision_id,
    }


__all__ = [
    "CandidateConclusion",
    "ProposedAnchorRevision",
    "propose_anchors",
    "to_anchor_bound_dict",
]
