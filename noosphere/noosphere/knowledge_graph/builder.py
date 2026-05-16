"""Knowledge-graph builder (prompt 13).

Produces a :class:`~noosphere.models.GraphSnapshot` for one org by
projecting the principle / algorithm / memo / source / contradiction
rows into a typed graph. Authoritative tables are read-only here —
the graph is a projection.

The builder is intentionally *layered*:

1. Collect node-shaped rows from each authoritative table.
2. Build a ``NodeIndex`` keyed by ``(kind, ref)`` so extractors can
   resolve foreign keys to graph node ids.
3. Run each :mod:`edge_extractors` function.
4. Persist the snapshot append-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4

from noosphere.knowledge_graph import edge_extractors as _ex
from noosphere.models import (
    GraphDelta,
    GraphSnapshot,
    KGEdge,
    KGEdgeKind,
    KGNode,
    KGNodeKind,
    ProvenanceKind,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BuildContext:
    """One-pass scratchpad while the builder collects rows + edges."""

    organization_id: str
    nodes: list[KGNode] = field(default_factory=list)
    edges: list[KGEdge] = field(default_factory=list)
    index: dict[tuple[KGNodeKind, str], str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def register(
        self,
        *,
        kind: KGNodeKind,
        ref: str,
        label: str = "",
        attrs: Optional[dict[str, Any]] = None,
        provenance: ProvenanceKind = ProvenanceKind.PROPRIETARY,
    ) -> str:
        key = (kind, str(ref))
        existing = self.index.get(key)
        if existing is not None:
            return existing
        node_id = f"kgnode_{uuid4().hex[:24]}"
        # Convert ProvenanceKind to plain string to match KGNode's
        # ``use_enum_values=True`` config.
        prov_value = (
            provenance.value
            if hasattr(provenance, "value")
            else str(provenance or "PROPRIETARY")
        )
        node = KGNode(
            id=node_id,
            kind=kind,
            ref=str(ref),
            label=label or str(ref),
            attrs=attrs or {},
            provenance=prov_value,
        )
        self.nodes.append(node)
        self.index[key] = node_id
        return node_id


# ── helpers reading the authoritative tables ────────────────────────


def _principle_provenance(p: Any) -> ProvenanceKind:
    prov = getattr(p, "provenance", None)
    if prov is None:
        return ProvenanceKind.PROPRIETARY
    if isinstance(prov, ProvenanceKind):
        return prov
    try:
        return ProvenanceKind(str(prov))
    except Exception:
        return ProvenanceKind.PROPRIETARY


def _collect_principles(ctx: BuildContext, store) -> list[Any]:
    rows: list[Any] = []
    try:
        rows = list(store.list_principles())
    except Exception as exc:  # noqa: BLE001
        ctx.notes.append(f"list_principles failed: {exc!r}")
        return []
    for p in rows:
        ctx.register(
            kind=KGNodeKind.PRINCIPLE,
            ref=str(getattr(p, "id", "") or ""),
            label=str(getattr(p, "text", "") or getattr(p, "id", ""))[:120],
            attrs={
                "conviction": float(getattr(p, "conviction_score", 0.0) or 0.0),
                "domain": str(getattr(p, "domain_of_applicability", "") or ""),
                "quantifiable_proxies": list(
                    getattr(p, "quantifiable_proxies", []) or []
                ),
            },
            provenance=_principle_provenance(p),
        )
    return rows


def _collect_algorithms(ctx: BuildContext, store, org_id: str) -> list[Any]:
    rows: list[Any] = []
    try:
        rows = list(store.list_algorithms_for_org(org_id))
    except Exception as exc:  # noqa: BLE001
        ctx.notes.append(f"list_algorithms_for_org failed: {exc!r}")
        return []
    for a in rows:
        ctx.register(
            kind=KGNodeKind.ALGORITHM,
            ref=str(getattr(a, "id", "") or ""),
            label=str(getattr(a, "name", "") or getattr(a, "id", ""))[:120],
            attrs={
                "status": str(getattr(a, "status", "") or ""),
                "weighting_multiplier": float(
                    getattr(a, "weighting_multiplier", 1.0) or 1.0
                ),
            },
            provenance=_principle_provenance(a),
        )
    return rows


def _collect_memos(ctx: BuildContext, store, org_id: str) -> list[Any]:
    rows: list[Any] = []
    try:
        rows = list(store.list_investment_memos(organization_id=org_id))
    except Exception as exc:  # noqa: BLE001
        ctx.notes.append(f"list_investment_memos failed: {exc!r}")
        return []
    for m in rows:
        ctx.register(
            kind=KGNodeKind.MEMO,
            ref=str(getattr(m, "id", "") or ""),
            label=str(getattr(m, "title", "") or getattr(m, "id", ""))[:120],
            attrs={
                "status": str(getattr(m, "status", "") or ""),
                "question_type": str(getattr(m, "question_type", "") or ""),
            },
        )
    return rows


def _collect_sources_from_refs(
    ctx: BuildContext, store, refs: Iterable[str]
) -> None:
    """Materialize SOURCE nodes for each artifact referenced by other rows."""
    seen: set[str] = set()
    for raw in refs:
        ref = str(raw or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        label = ref
        attrs: dict[str, Any] = {}
        provenance = ProvenanceKind.PROPRIETARY
        try:
            art = store.get_artifact(ref)
        except Exception:
            art = None
        if art is not None:
            label = str(getattr(art, "title", "") or getattr(art, "uri", "") or ref)[:120]
            attrs = {
                "uri": str(getattr(art, "uri", "") or ""),
                "mime_type": str(getattr(art, "mime_type", "") or ""),
                "author": str(getattr(art, "author", "") or ""),
            }
            provenance = _principle_provenance(art)
        ctx.register(
            kind=KGNodeKind.SOURCE,
            ref=ref,
            label=label,
            attrs=attrs,
            provenance=provenance,
        )


def _collect_topics(ctx: BuildContext, store) -> list[Any]:
    rows: list[Any] = []
    fn = getattr(store, "list_topics", None)
    if fn is None:
        return []
    try:
        rows = list(fn())
    except Exception:
        return []
    for t in rows:
        label = (
            str(getattr(t, "label", "") or "")
            or str(getattr(t, "name", "") or "")
            or str(getattr(t, "id", ""))
        )
        ctx.register(
            kind=KGNodeKind.TOPIC,
            ref=str(getattr(t, "id", "") or ""),
            label=label[:120],
            attrs={
                "freshness": str(getattr(t, "freshness", "") or ""),
            },
        )
    return rows


def _collect_contradictions(
    ctx: BuildContext, store
) -> tuple[list[Any], dict[str, Any]]:
    lifecycles: list[Any] = []
    try:
        lifecycles = list(store.list_contradiction_lifecycles())
    except Exception as exc:  # noqa: BLE001
        ctx.notes.append(f"list_contradiction_lifecycles failed: {exc!r}")
        return [], {}
    contradiction_ids = {
        str(getattr(lc, "contradiction_id", "") or "") for lc in lifecycles
    }
    contradiction_ids.discard("")
    rows_by_id: dict[str, Any] = {}
    fetch = getattr(store, "list_contradiction_results", None)
    if fetch is not None and contradiction_ids:
        try:
            for r in fetch():
                rid = str(getattr(r, "id", "") or "")
                if rid in contradiction_ids:
                    rows_by_id[rid] = r
        except Exception:
            rows_by_id = {}
    return lifecycles, rows_by_id


# ── builder entry points ────────────────────────────────────────────


def build_for_org(
    store,
    organization_id: str,
    *,
    persist: bool = True,
    extra_supports: Optional[Iterable[dict[str, Any]]] = None,
    extra_mentions: Optional[Iterable[dict[str, Any]]] = None,
    llm_supports: Optional[Iterable[dict[str, Any]]] = None,
) -> GraphSnapshot:
    """Build a full snapshot of one org's knowledge graph.

    ``extra_supports`` / ``extra_mentions`` let tests + the operator
    surface inject manual edges without re-running the LLM extractors.
    """
    ctx = BuildContext(organization_id=organization_id)

    principles = _collect_principles(ctx, store)
    algorithms = _collect_algorithms(ctx, store, organization_id)
    memos = _collect_memos(ctx, store, organization_id)
    topics = _collect_topics(ctx, store)

    # Source nodes — collected from refs on principles, memos, and any
    # extra mentions a caller passed.
    source_refs: list[str] = []
    for p in principles:
        ref = getattr(p, "source_artifact_id", None) or getattr(
            p, "source_artifact", None
        )
        if ref:
            source_refs.append(str(ref))
    for m in memos:
        for oid in getattr(m, "observed_input_ids", []) or []:
            source_refs.append(str(oid))
    if extra_mentions is not None:
        for row in extra_mentions:
            ref = str(row.get("src_ref", "") or "")
            if ref:
                source_refs.append(ref)
    _collect_sources_from_refs(ctx, store, source_refs)

    # Person / concept nodes referenced in ``extra_mentions``.
    if extra_mentions is not None:
        for row in extra_mentions:
            try:
                dst_kind = KGNodeKind(row["dst_kind"])
            except Exception:
                continue
            if dst_kind not in (KGNodeKind.PERSON, KGNodeKind.CONCEPT):
                continue
            ref = str(row.get("dst_ref", "") or "")
            if not ref:
                continue
            ctx.register(
                kind=dst_kind,
                ref=ref,
                label=str(row.get("dst_label", "") or ref),
            )

    # Edges ───────────────────────────────────────────────────────
    ctx.edges.extend(
        _ex.extract_derived_from(principles=principles, index=ctx.index)
    )
    ctx.edges.extend(
        _ex.extract_invokes(algorithms=algorithms, index=ctx.index)
    )
    lifecycles, rows_by_id = _collect_contradictions(ctx, store)
    ctx.edges.extend(
        _ex.extract_contradicts(
            lifecycles=lifecycles,
            contradiction_rows_by_id=rows_by_id,
            index=ctx.index,
        )
    )
    ctx.edges.extend(
        _ex.extract_supports(
            manual_supports=list(extra_supports or []),
            llm_supports=llm_supports,
            index=ctx.index,
        )
    )
    ctx.edges.extend(
        _ex.extract_applies_to(
            principles=principles, topics=topics, index=ctx.index
        )
    )
    ctx.edges.extend(
        _ex.extract_predicts(
            algorithms=algorithms, topics=topics, index=ctx.index
        )
    )
    ctx.edges.extend(_ex.extract_cites(memos=memos, index=ctx.index))
    ctx.edges.extend(
        _ex.extract_mentions(
            source_mentions=list(extra_mentions or []), index=ctx.index
        )
    )

    snapshot = GraphSnapshot(
        organization_id=organization_id,
        nodes=ctx.nodes,
        edges=ctx.edges,
        node_count=len(ctx.nodes),
        edge_count=len(ctx.edges),
        snapshot_at=_utcnow(),
        notes="; ".join(ctx.notes),
    )

    if persist and hasattr(store, "put_graph_snapshot"):
        try:
            store.put_graph_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph snapshot persistence failed: %r", exc)
    return snapshot


def incremental_update(
    store,
    event: dict[str, Any],
    *,
    organization_id: Optional[str] = None,
) -> list[GraphDelta]:
    """Compute deltas for one domain event and apply to latest snapshot.

    Supported event kinds:

    * ``principle_added`` — payload carries ``principle_id`` (and
      optionally ``source_artifact_id``).
    * ``algorithm_invoked`` — payload carries ``algorithm_id``.
    * ``memo_created`` — payload carries ``memo_id``.
    * ``source_uploaded`` — payload carries ``source_id``.
    * ``contradiction_flagged`` — payload carries ``contradiction_id``.

    Unrecognised events return an empty list (no-op). The function is
    deliberately tolerant — schedulers can fire stale events without
    the builder crashing.
    """
    org_id = organization_id or str(event.get("organization_id", "") or "")
    if not org_id:
        return []
    kind = str(event.get("kind", "") or "")
    payload = event.get("payload", {}) or {}

    latest = (
        store.get_latest_graph_snapshot(org_id)
        if hasattr(store, "get_latest_graph_snapshot")
        else None
    )
    deltas: list[GraphDelta] = []

    if kind == "principle_added":
        principle_id = str(payload.get("principle_id", "") or "")
        if not principle_id:
            return []
        principles = []
        try:
            principles = list(store.list_principles())
        except Exception:
            return []
        match = next(
            (p for p in principles if str(getattr(p, "id", "")) == principle_id),
            None,
        )
        if match is None:
            return []
        node = KGNode(
            id=f"kgnode_{uuid4().hex[:24]}",
            kind=KGNodeKind.PRINCIPLE,
            ref=principle_id,
            label=str(getattr(match, "text", "") or principle_id)[:120],
            provenance=_principle_provenance(match).value,
        )
        deltas.append(
            GraphDelta(
                op="add", target="node", payload=node.model_dump(mode="json")
            )
        )
        source_ref = (
            payload.get("source_artifact_id")
            or getattr(match, "source_artifact_id", None)
            or getattr(match, "source_artifact", None)
        )
        if source_ref:
            edge = KGEdge(
                id=f"kgedge_{uuid4().hex[:24]}",
                src=node.id,
                dst=str(source_ref),
                kind=KGEdgeKind.DERIVED_FROM,
            )
            deltas.append(
                GraphDelta(
                    op="add",
                    target="edge",
                    payload=edge.model_dump(mode="json"),
                )
            )
    elif kind == "contradiction_flagged":
        contradiction_id = str(payload.get("contradiction_id", "") or "")
        a_ref = str(payload.get("principle_a_id", "") or "")
        b_ref = str(payload.get("principle_b_id", "") or "")
        score = float(payload.get("score", 0.0) or 0.0)
        if not (contradiction_id and a_ref and b_ref):
            return []
        edge = KGEdge(
            id=f"kgedge_{uuid4().hex[:24]}",
            src=a_ref,
            dst=b_ref,
            kind=KGEdgeKind.CONTRADICTS,
            weight=score,
            attrs={"contradiction_id": contradiction_id},
        )
        deltas.append(
            GraphDelta(
                op="add", target="edge", payload=edge.model_dump(mode="json")
            )
        )

    # Apply deltas to a fresh snapshot (append-only persistence). A new
    # snapshot row is written so the history is auditable.
    if deltas and latest is not None:
        new_nodes = list(latest.nodes)
        new_edges = list(latest.edges)
        for d in deltas:
            if d.op == "add" and d.target == "node":
                new_nodes.append(KGNode.model_validate(d.payload))
            elif d.op == "add" and d.target == "edge":
                new_edges.append(KGEdge.model_validate(d.payload))
            elif d.op == "remove" and d.target == "node":
                new_nodes = [
                    n for n in new_nodes if n.id != d.payload.get("id")
                ]
            elif d.op == "remove" and d.target == "edge":
                new_edges = [
                    e for e in new_edges if e.id != d.payload.get("id")
                ]
        new_snap = GraphSnapshot(
            organization_id=org_id,
            nodes=new_nodes,
            edges=new_edges,
            node_count=len(new_nodes),
            edge_count=len(new_edges),
            snapshot_at=_utcnow(),
            notes=f"incremental: {kind}",
        )
        if hasattr(store, "put_graph_snapshot"):
            try:
                store.put_graph_snapshot(new_snap)
            except Exception as exc:  # noqa: BLE001
                logger.warning("incremental snapshot persist failed: %r", exc)
    return deltas


class KnowledgeGraphBuilder:
    """Class form of the build/update entrypoints.

    Carrying the store as state lets callers reuse the same builder
    across multiple operations.
    """

    def __init__(self, store) -> None:  # noqa: ANN001
        self._store = store

    def build_for_org(
        self,
        organization_id: str,
        **kwargs: Any,
    ) -> GraphSnapshot:
        return build_for_org(self._store, organization_id, **kwargs)

    def incremental_update(
        self,
        event: dict[str, Any],
        **kwargs: Any,
    ) -> list[GraphDelta]:
        return incremental_update(self._store, event, **kwargs)
