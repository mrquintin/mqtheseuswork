"""Embedding-space cluster index for the contradiction engine (R19/p07).

Solves Jacob's cost concern: testing every new principle against every old
principle is O(N²). At corpus scale that's untenable. This index pre-filters
pairs into geometric "domains of applicability" — the contradiction engine
(prompt 06) only inspects pairs the index decides are worth its CPU-seconds,
plus a deliberate non-zero sample of cross-cluster pairs so surprise links
are never lost (the founder's caveat: "language is not ideas, but it tracks
for semantic"). One cluster join, one optional cross-cluster spray, one
distant random spray — three knobs, all configurable.

The cluster index is an OPTIMISATION, not a correctness layer. It decides
WHICH pairs the engine looks at; the engine remains the source of truth for
contradiction verdicts.

Persistence is versioned: each row carries the ``assignment_method`` that
produced it (``incremental/v1`` for live assigns, ``resweep/<stamp>`` for
nightly k-means). That lets the operator surface answer
"which cluster was X in on date Y?" by range-scanning the table.
"""

from __future__ import annotations

import logging
import math
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover — exercised only on broken local wheels.
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ── Configuration (env-overridable; defaults are the prompt's defaults) ─────


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


CLUSTER_JOIN_THRESHOLD = _env_float("CLUSTER_JOIN_THRESHOLD", 0.72)
MIN_CLUSTER_SIZE = _env_int("MIN_CLUSTER_SIZE", 3)
CROSS_CLUSTER_SAMPLE_FRACTION = _env_float("CROSS_CLUSTER_SAMPLE_FRACTION", 0.05)
CROSS_CLUSTER_RANDOM_FRACTION = _env_float("CROSS_CLUSTER_RANDOM_FRACTION", 0.01)
CLUSTER_DRIFT_THRESHOLD = _env_float("CLUSTER_DRIFT_THRESHOLD", 0.15)
CONTRADICTION_TEST_BUDGET_PER_TICK_S = _env_float(
    "CONTRADICTION_TEST_BUDGET_PER_TICK_S", 30.0
)

ASSIGNMENT_METHOD_INCREMENTAL = "incremental/v1"
ASSIGNMENT_METHOD_RESWEEP_PREFIX = "resweep/"


class ClusterConfigError(ValueError):
    """Setting either cross-cluster fraction to exactly 0 is a config error.

    The whole point of the index is to never lose surprise links, so the
    engine refuses to start with zero spray.
    """


def validate_fractions(
    sample_fraction: float, random_fraction: float
) -> None:
    if sample_fraction <= 0.0:
        raise ClusterConfigError(
            "CROSS_CLUSTER_SAMPLE_FRACTION must be > 0 — the whole point of "
            "the cluster index is to never lose surprise links."
        )
    if random_fraction <= 0.0:
        raise ClusterConfigError(
            "CROSS_CLUSTER_RANDOM_FRACTION must be > 0 — the whole point of "
            "the cluster index is to never lose surprise links."
        )


# ── Helpers (numpy-or-pure-python, kept lightweight) ────────────────────────


def _as_array(vec: Sequence[float]) -> Any:
    if np is None:
        return [float(x) for x in vec]
    return np.asarray(vec, dtype=float).reshape(-1)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if np is not None:
        av = np.asarray(a, dtype=float).reshape(-1)
        bv = np.asarray(b, dtype=float).reshape(-1)
        if av.size == 0 or bv.size == 0 or av.size != bv.size:
            return 0.0
        denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
        if denom == 0.0:
            return 0.0
        return float(np.dot(av, bv) / denom)
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _mean(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        return []
    if np is not None:
        return np.mean(np.asarray(vectors, dtype=float), axis=0).tolist()
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += float(x)
    return [a / len(vectors) for a in acc]


def _new_cluster_id() -> str:
    return f"cl_{uuid.uuid4().hex[:12]}"


# ── Data carriers ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClusterMember:
    principle_id: str
    cluster_id: str
    assignment_method: str
    assigned_at: datetime


@dataclass(frozen=True)
class ClusterRecord:
    cluster_id: str
    centroid: list[float]
    member_count: int
    assignment_method: str


@dataclass(frozen=True)
class AssignmentResult:
    cluster_id: str
    is_new_cluster: bool
    cosine_to_centroid: float


@dataclass(frozen=True)
class ResweepReport:
    drift: float
    proposal_id: Optional[str]
    cluster_count_before: int
    cluster_count_after: int
    moved_principle_count: int


@dataclass(frozen=True)
class ClusterTopology:
    cluster_sizes: dict[str, int]
    centroid_spread: float  # mean pairwise cosine distance between centroids
    member_count: int
    assignment_methods: dict[str, str]  # cluster_id -> method


# ── Cluster index ───────────────────────────────────────────────────────────


class ClusterIndex:
    """Maintains the live (incremental) cluster assignment.

    Backed by ``StoredPrincipleCluster`` and ``StoredClusterCentroid`` on the
    Store. The in-memory cache holds (principle_id, embedding) so we don't
    re-query Prisma for every assignment; the cache is rehydrated lazily on
    first use of the index inside a process.
    """

    def __init__(
        self,
        store: Any,
        *,
        join_threshold: float = CLUSTER_JOIN_THRESHOLD,
        min_cluster_size: int = MIN_CLUSTER_SIZE,
        drift_threshold: float = CLUSTER_DRIFT_THRESHOLD,
    ) -> None:
        self._store = store
        self._join_threshold = float(join_threshold)
        self._min_cluster_size = int(min_cluster_size)
        self._drift_threshold = float(drift_threshold)
        # cluster_id -> {principle_id -> list[float]}
        self._members: dict[str, dict[str, list[float]]] = {}
        # cluster_id -> centroid list[float]
        self._centroids: dict[str, list[float]] = {}
        # principle_id -> cluster_id (fast reverse lookup)
        self._membership: dict[str, str] = {}
        # cluster_id -> assignment_method
        self._cluster_methods: dict[str, str] = {}
        self._hydrated = False

    # ── lifecycle ───────────────────────────────────────────────────────

    def hydrate(self, principle_embeddings: dict[str, list[float]]) -> None:
        """Rebuild in-memory state from the persisted assignments.

        ``principle_embeddings`` maps principle_id → vector. Principles not
        present in this map are dropped from the in-memory index (their row
        on disk is left intact for the resweep job to reconcile).
        """

        assignments = self._store.list_principle_cluster_assignments()
        centroids = {
            row["cluster_id"]: row
            for row in self._store.list_cluster_centroids()
        }
        members: dict[str, dict[str, list[float]]] = {}
        membership: dict[str, str] = {}
        methods: dict[str, str] = {}
        for row in assignments:
            pid = row["principle_id"]
            cid = row["cluster_id"]
            emb = principle_embeddings.get(pid)
            if emb is None:
                continue
            members.setdefault(cid, {})[pid] = list(emb)
            membership[pid] = cid
            methods[cid] = row.get("assignment_method", ASSIGNMENT_METHOD_INCREMENTAL)
        live_centroids: dict[str, list[float]] = {}
        for cid, principle_to_vec in members.items():
            persisted = centroids.get(cid)
            if persisted and persisted.get("centroid"):
                live_centroids[cid] = list(persisted["centroid"])
            else:
                live_centroids[cid] = _mean(list(principle_to_vec.values()))
        self._members = members
        self._centroids = live_centroids
        self._membership = membership
        self._cluster_methods = methods
        self._hydrated = True

    def ensure_hydrated(
        self, principle_embeddings: dict[str, list[float]] | None = None
    ) -> None:
        if self._hydrated:
            return
        self.hydrate(principle_embeddings or {})

    # ── core operations ─────────────────────────────────────────────────

    def assign(
        self, principle_id: str, embedding: Sequence[float]
    ) -> AssignmentResult:
        """Assign one principle. Joins the nearest cluster (cosine ≥
        threshold) or opens a new cluster. Persists the row.
        """

        if not embedding:
            raise ValueError("cluster_index.assign: empty embedding")
        vec = [float(x) for x in embedding]

        # If already assigned, return the existing membership (idempotent).
        existing_cid = self._membership.get(principle_id)
        if existing_cid is not None:
            centroid = self._centroids.get(existing_cid, vec)
            return AssignmentResult(
                cluster_id=existing_cid,
                is_new_cluster=False,
                cosine_to_centroid=_cosine(vec, centroid),
            )

        # Nearest existing cluster by centroid cosine.
        best_cid: Optional[str] = None
        best_sim = -1.0
        for cid, centroid in self._centroids.items():
            sim = _cosine(vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_cid = cid

        if best_cid is not None and best_sim >= self._join_threshold:
            cluster_id = best_cid
            is_new = False
        else:
            cluster_id = _new_cluster_id()
            is_new = True
            self._members[cluster_id] = {}
            self._centroids[cluster_id] = list(vec)
            self._cluster_methods[cluster_id] = ASSIGNMENT_METHOD_INCREMENTAL

        # Update in-memory state.
        self._members.setdefault(cluster_id, {})[principle_id] = vec
        self._membership[principle_id] = cluster_id
        self._recompute_centroid(cluster_id)

        # Persist.
        method = self._cluster_methods.get(
            cluster_id, ASSIGNMENT_METHOD_INCREMENTAL
        )
        self._store.upsert_principle_cluster(
            principle_id=principle_id,
            cluster_id=cluster_id,
            assignment_method=method,
        )
        self._persist_centroid(cluster_id)

        final_sim = (
            best_sim
            if not is_new and best_cid == cluster_id
            else _cosine(vec, self._centroids[cluster_id])
        )
        return AssignmentResult(
            cluster_id=cluster_id,
            is_new_cluster=is_new,
            cosine_to_centroid=float(final_sim),
        )

    def remove(self, principle_id: str) -> Optional[str]:
        """Remove a principle (revocation). If the cluster falls below the
        minimum size, merge it into the nearest neighbor (or dissolve if no
        neighbor exists).

        Returns the cluster id the principle was removed from, or None.
        """

        cid = self._membership.pop(principle_id, None)
        if cid is None:
            self._store.delete_principle_cluster(principle_id)
            return None
        member_map = self._members.get(cid, {})
        member_map.pop(principle_id, None)
        self._store.delete_principle_cluster(principle_id)
        if not member_map:
            self._dissolve(cid)
            return cid
        self._recompute_centroid(cid)
        self._persist_centroid(cid)
        if len(member_map) < self._min_cluster_size:
            self._merge_or_dissolve(cid)
        return cid

    # ── neighbors + sampling ────────────────────────────────────────────

    def cluster_id_of(self, principle_id: str) -> Optional[str]:
        return self._membership.get(principle_id)

    def members_of(self, cluster_id: str) -> list[str]:
        return list(self._members.get(cluster_id, {}).keys())

    def neighboring_cluster_ids(
        self, cluster_id: str, *, k: int = 3
    ) -> list[str]:
        """Top-k other clusters by centroid cosine to ``cluster_id``."""

        centroid = self._centroids.get(cluster_id)
        if centroid is None:
            return []
        scored = [
            (cid, _cosine(centroid, c))
            for cid, c in self._centroids.items()
            if cid != cluster_id
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [cid for cid, _ in scored[: max(0, k)]]

    def distant_cluster_ids(
        self, cluster_id: str, *, k: int | None = None
    ) -> list[str]:
        """Clusters NOT in the top-k neighbors. With k=None, returns every
        other cluster. Order is reverse centroid cosine (most distant first)."""

        centroid = self._centroids.get(cluster_id)
        if centroid is None:
            return []
        scored = [
            (cid, _cosine(centroid, c))
            for cid, c in self._centroids.items()
            if cid != cluster_id
        ]
        scored.sort(key=lambda pair: pair[1])
        if k is None:
            return [cid for cid, _ in scored]
        return [cid for cid, _ in scored[: max(0, k)]]

    def topology(self) -> ClusterTopology:
        sizes = {cid: len(members) for cid, members in self._members.items()}
        centroids = list(self._centroids.values())
        spread = 0.0
        if len(centroids) >= 2:
            distances: list[float] = []
            for i, ci in enumerate(centroids):
                for cj in centroids[i + 1 :]:
                    distances.append(1.0 - _cosine(ci, cj))
            if distances:
                spread = sum(distances) / len(distances)
        return ClusterTopology(
            cluster_sizes=sizes,
            centroid_spread=float(spread),
            member_count=sum(sizes.values()),
            assignment_methods=dict(self._cluster_methods),
        )

    # ── resweep ─────────────────────────────────────────────────────────

    def resweep_kmeans(
        self,
        principle_embeddings: dict[str, list[float]],
        *,
        k: int | None = None,
        max_iter: int = 25,
        seed: int = 0,
    ) -> ResweepReport:
        """Full k-means over every principle embedding. Compares the new
        assignments to the incremental ones and logs the fraction of
        principles that moved. If drift > ``CLUSTER_DRIFT_THRESHOLD``, an
        operator-visible ``ClusterReindexProposal`` row is inserted.

        Does NOT mutate the live assignments. The operator must explicitly
        accept the proposal to swap them in. This keeps the incremental
        assignment the system runs on, while still surfacing drift.
        """

        if np is None:
            raise RuntimeError(
                "cluster_index.resweep_kmeans requires numpy"
            )
        ids = [
            pid
            for pid, vec in principle_embeddings.items()
            if vec
        ]
        if not ids:
            return ResweepReport(
                drift=0.0,
                proposal_id=None,
                cluster_count_before=len(self._members),
                cluster_count_after=0,
                moved_principle_count=0,
            )
        vectors = np.asarray(
            [principle_embeddings[pid] for pid in ids], dtype=float
        )
        target_k = k or max(
            2, min(len(ids), max(2, len(self._members) or 2))
        )
        rng = np.random.default_rng(seed)
        # k-means++ init: pick the first centroid uniformly, then sample the
        # next centroid with probability proportional to squared distance.
        centroids = np.empty((target_k, vectors.shape[1]), dtype=float)
        first = int(rng.integers(0, len(ids)))
        centroids[0] = vectors[first]
        for ci in range(1, target_k):
            diff = vectors[:, None, :] - centroids[:ci, None, :].squeeze(1)
            # squared euclidean (vectors are normalized-ish; sqr-eucl is fine)
            if diff.ndim == 2:
                d2 = np.sum(diff ** 2, axis=-1)[:, None]
            else:
                d2 = np.sum(diff ** 2, axis=-1)
            min_d2 = np.min(d2, axis=1)
            total = float(min_d2.sum())
            if total <= 0.0:
                centroids[ci] = vectors[int(rng.integers(0, len(ids)))]
                continue
            probs = min_d2 / total
            choice = int(rng.choice(len(ids), p=probs))
            centroids[ci] = vectors[choice]

        labels = np.zeros(len(ids), dtype=int)
        for _ in range(max_iter):
            # cosine-similar assignment: normalize then dot
            v_norm = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12)
            c_norm = centroids / (np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-12)
            sims = v_norm @ c_norm.T
            new_labels = np.argmax(sims, axis=1)
            if np.array_equal(new_labels, labels):
                labels = new_labels
                break
            labels = new_labels
            for ci in range(target_k):
                mask = labels == ci
                if mask.any():
                    centroids[ci] = vectors[mask].mean(axis=0)
        proposed_labels = {ids[i]: int(labels[i]) for i in range(len(ids))}

        # Compute drift as fraction of principles whose proposed-label
        # group disagrees with their current cluster's plurality vote.
        moved = 0
        evaluated = 0
        # Map current cluster -> dominant proposed label.
        cluster_to_proposed: dict[str, int] = {}
        for cid, members in self._members.items():
            if not members:
                continue
            votes: dict[int, int] = {}
            for pid in members:
                if pid not in proposed_labels:
                    continue
                votes[proposed_labels[pid]] = votes.get(proposed_labels[pid], 0) + 1
            if not votes:
                continue
            dominant = max(votes.items(), key=lambda kv: kv[1])[0]
            cluster_to_proposed[cid] = dominant
        for pid, cid in self._membership.items():
            if pid not in proposed_labels:
                continue
            evaluated += 1
            dominant = cluster_to_proposed.get(cid)
            if dominant is None:
                moved += 1
                continue
            if proposed_labels[pid] != dominant:
                moved += 1
        drift = (moved / evaluated) if evaluated else 0.0

        proposal_id: Optional[str] = None
        if drift > self._drift_threshold:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            summary = {
                "stamp": stamp,
                "evaluated": evaluated,
                "moved": moved,
                "proposed_cluster_count": int(target_k),
                "assignment_method": f"{ASSIGNMENT_METHOD_RESWEEP_PREFIX}{stamp}",
                "moved_examples": [
                    pid
                    for pid in list(self._membership.keys())[:20]
                ],
            }
            proposal_id = self._store.insert_cluster_reindex_proposal(
                drift=drift,
                cluster_count_before=len(self._members),
                cluster_count_after=int(target_k),
                summary=summary,
            )
            logger.info(
                "cluster_resweep_drift drift=%.4f moved=%d evaluated=%d "
                "proposal_id=%s",
                drift,
                moved,
                evaluated,
                proposal_id,
            )
        return ResweepReport(
            drift=float(drift),
            proposal_id=proposal_id,
            cluster_count_before=len(self._members),
            cluster_count_after=int(target_k),
            moved_principle_count=int(moved),
        )

    # ── internals ───────────────────────────────────────────────────────

    def _recompute_centroid(self, cluster_id: str) -> None:
        member_map = self._members.get(cluster_id, {})
        if not member_map:
            self._centroids.pop(cluster_id, None)
            return
        self._centroids[cluster_id] = _mean(list(member_map.values()))

    def _persist_centroid(self, cluster_id: str) -> None:
        centroid = self._centroids.get(cluster_id)
        if centroid is None:
            self._store.delete_cluster_centroid(cluster_id)
            return
        self._store.upsert_cluster_centroid(
            cluster_id=cluster_id,
            centroid=centroid,
            member_count=len(self._members.get(cluster_id, {})),
            assignment_method=self._cluster_methods.get(
                cluster_id, ASSIGNMENT_METHOD_INCREMENTAL
            ),
        )

    def _dissolve(self, cluster_id: str) -> None:
        self._members.pop(cluster_id, None)
        self._centroids.pop(cluster_id, None)
        self._cluster_methods.pop(cluster_id, None)
        self._store.delete_cluster_centroid(cluster_id)

    def _merge_or_dissolve(self, cluster_id: str) -> None:
        """Cluster fell below MIN_CLUSTER_SIZE — find nearest neighbor and
        absorb its members; if no neighbor, leave as-is (still tracked, just
        a stub the resweep can fold)."""

        centroid = self._centroids.get(cluster_id)
        if centroid is None:
            self._dissolve(cluster_id)
            return
        neighbors = [
            (cid, _cosine(centroid, c))
            for cid, c in self._centroids.items()
            if cid != cluster_id
        ]
        if not neighbors:
            return
        neighbors.sort(key=lambda kv: kv[1], reverse=True)
        target_cid, _sim = neighbors[0]
        member_map = self._members.get(cluster_id, {})
        target_map = self._members.setdefault(target_cid, {})
        for pid, vec in member_map.items():
            target_map[pid] = vec
            self._membership[pid] = target_cid
            self._store.upsert_principle_cluster(
                principle_id=pid,
                cluster_id=target_cid,
                assignment_method=self._cluster_methods.get(
                    target_cid, ASSIGNMENT_METHOD_INCREMENTAL
                ),
            )
        self._dissolve(cluster_id)
        self._recompute_centroid(target_cid)
        self._persist_centroid(target_cid)


# ── Sampling helper used by the scheduler ───────────────────────────────────


def sample_cross_cluster_pool(
    pool: Iterable[str],
    fraction: float,
    *,
    rng: random.Random | None = None,
    minimum: int = 0,
) -> list[str]:
    """Sample ``fraction`` of ``pool`` (no replacement). Guarantees at least
    ``minimum`` items when the pool is non-empty and fraction > 0.
    """

    items = list(pool)
    if not items or fraction <= 0.0:
        return []
    rng = rng or random.Random()
    count = max(minimum, int(math.ceil(len(items) * float(fraction))))
    count = min(count, len(items))
    return rng.sample(items, count) if count else []
