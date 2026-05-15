"""Cluster selector for the auto-paper generator.

Picks a candidate cluster of conclusions worth turning into a draft
research paper. A valid cluster is:

  1. A connected subgraph of CascadeNodes with kind=CONCLUSION,
     reached from a seed via SUPPORTS / DEPENDS_ON / COHERES_WITH
     edges (treated as undirected for connectivity).
  2. Sharing at least one common methodology root — i.e. one
     MethodologyProfile attached (directly or via upload bridge)
     to every conclusion in the cluster.
  3. Touching at least one resolved forecast — a ForecastResolution
     whose ForecastPrediction either lists a cluster conclusion in
     its trace's principles_used or carries a topic_hint that
     matches the cluster's lead conclusion.

The selector is read-only. It returns a ``PaperCluster`` describing
what the generator should pull, never mutating store state.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

from sqlmodel import select

from noosphere.models import (
    CascadeEdgeRelation,
    CascadeNodeKind,
    Conclusion,
    ForecastPrediction,
    ForecastResolution,
    MethodologyProfile,
)

logger = logging.getLogger(__name__)

_CONNECTING_RELATIONS = frozenset(
    {
        CascadeEdgeRelation.SUPPORTS.value,
        CascadeEdgeRelation.DEPENDS_ON.value,
        CascadeEdgeRelation.COHERES_WITH.value,
        CascadeEdgeRelation.AGGREGATES.value,
        CascadeEdgeRelation.GENERALIZES.value,
        CascadeEdgeRelation.SPECIALIZES.value,
    }
)


@dataclass(frozen=True)
class MethodologyRoot:
    """The shared methodology profile that gates the cluster."""

    profile_id: str
    pattern_type: str
    title: str
    summary: str
    reasoning_moves: tuple[str, ...] = ()
    transfer_targets: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedForecastTouch:
    """A resolved forecast that touches the cluster."""

    prediction_id: str
    market_id: str
    headline: str
    market_outcome: str
    brier_score: Optional[float]
    log_loss: Optional[float]
    probability_yes: Optional[float]


@dataclass(frozen=True)
class PaperCluster:
    """A cluster of conclusions ready for paper drafting."""

    cluster_id: str
    lead_conclusion_id: str
    conclusion_ids: tuple[str, ...]
    methodology_root: MethodologyRoot
    resolved_forecasts: tuple[ResolvedForecastTouch, ...]
    citation_node_ids: tuple[str, ...] = field(default_factory=tuple)


class ClusterSelectionError(Exception):
    """No valid cluster could be selected for the requested seed."""


def _aslist(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item is not None]
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
    return []


def _connected_conclusion_nodes(
    store: Any,
    seed_node_id: str,
    *,
    max_size: int = 8,
) -> list[str]:
    """BFS over connecting edges, filtering to conclusion nodes."""
    visited: set[str] = set()
    order: list[str] = []
    queue: list[str] = [seed_node_id]

    while queue and len(order) < max_size:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = store.get_cascade_node(current)
        if node is None:
            continue
        if node.kind == CascadeNodeKind.CONCLUSION:
            order.append(current)
        for edge in store.iter_cascade_edges(src=current):
            if edge.relation.value in _CONNECTING_RELATIONS:
                queue.append(edge.dst)
        for edge in store.iter_cascade_edges(dst=current):
            if edge.relation.value in _CONNECTING_RELATIONS:
                queue.append(edge.src)
    return order


def _conclusion_id_for_node(store: Any, node_id: str) -> Optional[str]:
    node = store.get_cascade_node(node_id)
    if node is None or node.kind != CascadeNodeKind.CONCLUSION:
        return None
    return node.ref


def _shared_methodology_root(
    store: Any, conclusion_ids: Iterable[str]
) -> Optional[MethodologyRoot]:
    """Return the highest-confidence MethodologyProfile representing
    a shared methodology root across all conclusions in the cluster.

    Two profiles are treated as the same root if they share the same
    ``dedupe_key`` (the production unique key for "same methodology
    pattern across uploads"). The cluster is valid iff every
    conclusion has at least one profile attached for that key.
    """
    cids = list(conclusion_ids)
    if not cids:
        return None
    with store.session() as s:
        profiles_by_conclusion: dict[str, list[MethodologyProfile]] = {}
        for cid in cids:
            rows = s.exec(
                select(MethodologyProfile).where(
                    MethodologyProfile.conclusion_id == cid
                )
            ).all()
            profiles_by_conclusion[cid] = list(rows)

    common_keys: Optional[set[str]] = None
    profile_lookup: dict[str, list[MethodologyProfile]] = {}
    for cid, profiles in profiles_by_conclusion.items():
        keys = set()
        for p in profiles:
            keys.add(p.dedupe_key)
            profile_lookup.setdefault(p.dedupe_key, []).append(p)
        common_keys = keys if common_keys is None else common_keys & keys

    if not common_keys:
        return None

    chosen_key = max(
        common_keys,
        key=lambda k: max(p.confidence for p in profile_lookup[k]),
    )
    candidates = profile_lookup[chosen_key]
    p = max(candidates, key=lambda x: x.confidence)
    return MethodologyRoot(
        profile_id=p.id,
        pattern_type=p.pattern_type,
        title=p.title,
        summary=p.summary,
        reasoning_moves=tuple(_aslist(p.reasoning_moves)),
        transfer_targets=tuple(_aslist(p.transfer_targets)),
        assumptions=tuple(_aslist(p.assumptions)),
        failure_modes=tuple(_aslist(p.failure_modes)),
    )


def _resolved_forecasts_touching(
    store: Any, conclusion_ids: Iterable[str]
) -> list[ResolvedForecastTouch]:
    cid_set = set(conclusion_ids)
    if not cid_set:
        return []
    touches: list[ResolvedForecastTouch] = []
    seen: set[str] = set()
    with store.session() as s:
        resolutions = list(s.exec(select(ForecastResolution)).all())
    for res in resolutions:
        if res.prediction_id in seen:
            continue
        with store.session() as s:
            pred = s.get(ForecastPrediction, res.prediction_id)
        if pred is None:
            continue
        trace = None
        try:
            trace = store.get_forecast_trace(pred.id)
        except Exception:
            trace = None
        used_conclusion_ids: set[str] = set()
        if trace is not None:
            for entry in getattr(trace, "principles_used", []) or []:
                if isinstance(entry, dict):
                    val = entry.get("conclusionId") or entry.get("conclusion_id")
                    if isinstance(val, str):
                        used_conclusion_ids.add(val)
        topic_hint = (pred.topic_hint or "").strip().lower()
        topic_hits = any(
            topic_hint and topic_hint == cid.lower() for cid in cid_set
        )
        if not (used_conclusion_ids & cid_set) and not topic_hits:
            continue
        seen.add(res.prediction_id)
        touches.append(
            ResolvedForecastTouch(
                prediction_id=pred.id,
                market_id=pred.market_id,
                headline=pred.headline,
                market_outcome=str(res.market_outcome.value)
                if hasattr(res.market_outcome, "value")
                else str(res.market_outcome),
                brier_score=res.brier_score,
                log_loss=res.log_loss,
                probability_yes=float(pred.probability_yes)
                if pred.probability_yes is not None
                else None,
            )
        )
    return touches


def select_cluster(
    store: Any,
    *,
    seed_conclusion_id: str,
    cluster_id: Optional[str] = None,
    max_size: int = 8,
) -> PaperCluster:
    """Build a PaperCluster anchored on ``seed_conclusion_id``.

    Raises ClusterSelectionError if the connected component lacks a
    shared methodology root or has no resolved forecast touching it.
    """
    seed_conclusion = store.get_conclusion(seed_conclusion_id)
    if seed_conclusion is None:
        raise ClusterSelectionError(
            f"seed conclusion {seed_conclusion_id!r} not found in store"
        )

    seed_node_id: Optional[str] = None
    for edge in store.iter_cascade_edges():
        for nid in (edge.src, edge.dst):
            node = store.get_cascade_node(nid)
            if (
                node is not None
                and node.kind == CascadeNodeKind.CONCLUSION
                and node.ref == seed_conclusion_id
            ):
                seed_node_id = nid
                break
        if seed_node_id:
            break

    if seed_node_id is None:
        node_ref_id = seed_conclusion_id
        conclusion_ids = [node_ref_id]
    else:
        node_ids = _connected_conclusion_nodes(
            store, seed_node_id, max_size=max_size
        )
        conclusion_ids = []
        for nid in node_ids:
            cid = _conclusion_id_for_node(store, nid)
            if cid and cid not in conclusion_ids:
                conclusion_ids.append(cid)
        if seed_conclusion_id not in conclusion_ids:
            conclusion_ids.insert(0, seed_conclusion_id)

    methodology = _shared_methodology_root(store, conclusion_ids)
    if methodology is None:
        raise ClusterSelectionError(
            f"cluster anchored on {seed_conclusion_id!r} has no "
            "shared methodology root across its conclusions"
        )

    resolved = _resolved_forecasts_touching(store, conclusion_ids)
    if not resolved:
        raise ClusterSelectionError(
            f"cluster anchored on {seed_conclusion_id!r} has no "
            "resolved forecast touching the conclusion set"
        )

    return PaperCluster(
        cluster_id=cluster_id or f"cluster-{seed_conclusion_id}",
        lead_conclusion_id=seed_conclusion_id,
        conclusion_ids=tuple(conclusion_ids),
        methodology_root=methodology,
        resolved_forecasts=tuple(resolved),
    )


# ── Maturity ranking ─────────────────────────────────────────────────────────
#
# The auto-paper generator drafts the *most mature* clusters first. A
# cluster's maturity is a weighted sum of three signals, in descending
# order of how much they say the firm has actually pressure-tested the
# claim:
#
#   1. resolved forecast count — the cluster's claims have been settled
#      against reality, not just asserted. The strongest signal.
#   2. principle backing — the firm keeps re-deriving the cluster's
#      conclusions into standing principles. A durability signal.
#   3. size — raw conclusion count. A breadth signal, weakest of the
#      three: a big cluster of untested claims is not mature.
#
# The weights below are pinned by test_auto_paper_integration.py.
_MATURITY_W_RESOLVED_FORECASTS = 3.0
_MATURITY_W_PRINCIPLE_BACKING = 2.0
_MATURITY_W_SIZE = 1.0


@dataclass(frozen=True)
class ClusterMaturity:
    """The maturity signal that ranks a candidate cluster."""

    size: int
    resolved_forecast_count: int
    principle_backing: int
    score: float


@dataclass(frozen=True)
class ClusterRanking:
    """A ranked paper-cluster candidate: the cluster plus its maturity."""

    cluster: PaperCluster
    maturity: ClusterMaturity


def derive_cluster_id(cluster: PaperCluster) -> str:
    """Stable, readable cluster id for a selected cluster.

    Derived from the shared methodology root (so the artifact slug
    reads sensibly) plus a short hash of the conclusion-id set (so two
    clusters that happen to share a pattern type never collide). Pure
    function of the cluster — re-running the selector yields the same
    id, which keeps the on-disk ``docs/research/auto/<slug>`` directory
    stable across runs.
    """
    base = (
        cluster.methodology_root.pattern_type
        or cluster.methodology_root.title
        or "cluster"
    )
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "cluster"
    digest = hashlib.sha1(
        "|".join(sorted(cluster.conclusion_ids)).encode("utf-8")
    ).hexdigest()[:8]
    return f"{base}-{digest}"


def _principle_backing(store: Any, conclusion_ids: Iterable[str]) -> int:
    """Count the distinct standing principles backing a conclusion set."""
    seen: set[str] = set()
    for cid in conclusion_ids:
        c = store.get_conclusion(cid)
        if c is None:
            continue
        for pid in getattr(c, "supporting_principle_ids", None) or []:
            if isinstance(pid, str) and pid:
                seen.add(pid)
        for entry in getattr(c, "principles_used", None) or []:
            if isinstance(entry, str) and entry:
                seen.add(entry)
            elif isinstance(entry, dict):
                val = (
                    entry.get("principleId")
                    or entry.get("principle_id")
                    or entry.get("id")
                )
                if isinstance(val, str) and val:
                    seen.add(val)
    return len(seen)


def score_maturity(
    *, size: int, resolved_forecast_count: int, principle_backing: int
) -> float:
    """Weighted maturity score. See the module-level weight rationale."""
    return (
        _MATURITY_W_RESOLVED_FORECASTS * max(0, int(resolved_forecast_count))
        + _MATURITY_W_PRINCIPLE_BACKING * max(0, int(principle_backing))
        + _MATURITY_W_SIZE * max(0, int(size))
    )


def rank_clusters(
    store: Any,
    *,
    max_size: int = 8,
    top_n: Optional[int] = 3,
    seed_conclusion_ids: Optional[Iterable[str]] = None,
) -> list[ClusterRanking]:
    """Enumerate every valid paper-cluster reachable in the store and
    rank them by maturity.

    Each conclusion in the store (or ``seed_conclusion_ids`` if given)
    is tried as a cluster seed. Seeds that land in the same connected
    component collapse to one cluster (deduplicated by conclusion-id
    set). Seeds that do not form a valid cluster — no shared
    methodology root, no resolved forecast touching them — are skipped,
    not raised on.

    The returned list is sorted by descending maturity score, ties
    broken by ``lead_conclusion_id`` so the ordering is deterministic.
    ``top_n`` truncates the list (``None`` returns every candidate).
    Read-only: never mutates store state.
    """
    if seed_conclusion_ids is None:
        seeds = [c.id for c in store.list_conclusions()]
    else:
        seeds = list(seed_conclusion_ids)
    seeds = sorted({s for s in seeds if s})

    seen_components: dict[frozenset[str], PaperCluster] = {}
    for seed in seeds:
        try:
            cluster = select_cluster(
                store, seed_conclusion_id=seed, max_size=max_size
            )
        except ClusterSelectionError:
            continue
        except Exception:  # pragma: no cover - defensive
            logger.exception("cluster selection failed for seed %s", seed)
            continue
        key = frozenset(cluster.conclusion_ids)
        if key in seen_components:
            continue
        # Re-key every selected cluster onto a stable, readable id so the
        # ranking, the artifact slug, and the founder memo all agree.
        seen_components[key] = replace(
            cluster, cluster_id=derive_cluster_id(cluster)
        )

    rankings: list[ClusterRanking] = []
    for cluster in seen_components.values():
        size = len(cluster.conclusion_ids)
        resolved = len(cluster.resolved_forecasts)
        backing = _principle_backing(store, cluster.conclusion_ids)
        rankings.append(
            ClusterRanking(
                cluster=cluster,
                maturity=ClusterMaturity(
                    size=size,
                    resolved_forecast_count=resolved,
                    principle_backing=backing,
                    score=score_maturity(
                        size=size,
                        resolved_forecast_count=resolved,
                        principle_backing=backing,
                    ),
                ),
            )
        )

    rankings.sort(
        key=lambda r: (-r.maturity.score, r.cluster.lead_conclusion_id)
    )
    if top_n is not None and top_n >= 0:
        return rankings[:top_n]
    return rankings
