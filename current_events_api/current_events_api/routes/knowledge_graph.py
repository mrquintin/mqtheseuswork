"""Public REST routes for the cross-source knowledge graph (prompt 13).

Serves the latest persisted :class:`GraphSnapshot` to the
``/knowledge-graph`` page and answers the "click an edge, ask the
agent why" path via :func:`reason_about_edge`. The public surface
honours ``provenance_filter`` (prompt 09) — the operator route can
override it.

This module is intentionally thin: building snapshots is the
operator's job (or the scheduler's). The read path is meant to be a
hot, low-latency endpoint.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from current_events_api.deps import enforce_read_rate_limit, get_store
from noosphere.knowledge_graph.agent_reasoner import reason_about_edge
from noosphere.knowledge_graph.builder import build_for_org
from noosphere.models import (
    EdgeReasoning,
    KGEdge,
    KGEdgeKind,
    KGNode,
    KGNodeKind,
    ProvenanceKind,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/knowledge-graph", tags=["knowledge-graph"])


def _org_filter() -> Optional[str]:
    return (
        os.environ.get("KNOWLEDGE_GRAPH_ORG_ID")
        or os.environ.get("ALGORITHMS_ORG_ID")
        or os.environ.get("FORECASTS_ORG_ID")
        or None
    )


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _public_provenance_filter() -> set[str]:
    """Default public set: PROPRIETARY + ENDORSED (prompt 09)."""
    return {
        ProvenanceKind.PROPRIETARY.value,
        ProvenanceKind.ENDORSED_EXTERNAL.value,
    }


def _node_to_public(node: KGNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": _enum_value(node.kind),
        "ref": node.ref,
        "label": node.label,
        "attrs": dict(node.attrs or {}),
        "provenance": _enum_value(node.provenance),
    }


def _edge_to_public(edge: KGEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "src": edge.src,
        "dst": edge.dst,
        "kind": _enum_value(edge.kind),
        "weight": edge.weight,
        "attrs": dict(edge.attrs or {}),
    }


@router.get("")
def get_knowledge_graph(
    request_throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    organization_id: Optional[str] = Query(default=None),
    node_kind: Optional[str] = Query(default=None),
    edge_kind: Optional[str] = Query(default=None),
    include_provenance: Optional[str] = Query(
        default=None,
        description="Comma-separated provenance kinds to include. "
        "Defaults to PROPRIETARY,ENDORSED_EXTERNAL on the public view.",
    ),
    operator_override: bool = Query(
        default=False,
        description="Operator route: bypass the provenance filter.",
    ),
) -> dict[str, Any]:
    org_id = organization_id or _org_filter()
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required",
        )
    snap = store.get_latest_graph_snapshot(org_id)
    if snap is None:
        return {
            "ok": True,
            "organization_id": org_id,
            "snapshot": None,
            "nodes": [],
            "edges": [],
        }

    if operator_override:
        allowed: Optional[set[str]] = None
    elif include_provenance:
        allowed = {
            p.strip().upper() for p in include_provenance.split(",") if p.strip()
        }
    else:
        allowed = _public_provenance_filter()

    nodes = list(snap.nodes)
    if node_kind:
        nk = node_kind.upper()
        nodes = [n for n in nodes if _enum_value(n.kind) == nk]
    if allowed is not None:
        nodes = [n for n in nodes if _enum_value(n.provenance) in allowed]
    node_ids = {n.id for n in nodes}

    edges = [
        e for e in snap.edges if e.src in node_ids and e.dst in node_ids
    ]
    if edge_kind:
        ek = edge_kind.upper()
        edges = [e for e in edges if _enum_value(e.kind) == ek]

    return {
        "ok": True,
        "organization_id": org_id,
        "snapshot": {
            "id": snap.id,
            "snapshot_at": snap.snapshot_at.isoformat()
            if snap.snapshot_at
            else None,
            "version": snap.version,
            "node_count": snap.node_count,
            "edge_count": snap.edge_count,
        },
        "nodes": [_node_to_public(n) for n in nodes],
        "edges": [_edge_to_public(e) for e in edges],
    }


@router.get("/node/{node_id}")
def get_node_detail(
    request_throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    node_id: str,
    organization_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    org_id = organization_id or _org_filter()
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required",
        )
    snap = store.get_latest_graph_snapshot(org_id)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no snapshot for org; an operator must rebuild first",
        )
    node = next(
        (n for n in snap.nodes if n.id == node_id or n.ref == node_id), None
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"node {node_id!r} not found in latest snapshot",
        )
    neighbors: list[dict[str, Any]] = []
    for e in snap.edges:
        other_id: Optional[str] = None
        if e.src == node.id:
            other_id = e.dst
        elif e.dst == node.id:
            other_id = e.src
        else:
            continue
        other = next((n for n in snap.nodes if n.id == other_id), None)
        if other is None:
            continue
        neighbors.append(
            {
                "edge": _edge_to_public(e),
                "node": _node_to_public(other),
            }
        )
        if len(neighbors) >= limit:
            break
    return {
        "ok": True,
        "node": _node_to_public(node),
        "neighbors": neighbors,
    }


class EdgeReasoningRequest(BaseModel):
    organization_id: str = Field(min_length=1)
    src: str = Field(min_length=1, description="src node id or ref")
    dst: str = Field(min_length=1, description="dst node id or ref")
    edge_kind: str = Field(min_length=1)
    use_llm: bool = Field(
        default=True,
        description=(
            "When True (default), call the configured LLM client. "
            "When False, return the deterministic structural fallback."
        ),
    )


@router.post("/reason")
async def reason_about_edge_endpoint(
    request_throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    payload: EdgeReasoningRequest,
) -> dict[str, Any]:
    snap = store.get_latest_graph_snapshot(payload.organization_id)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no snapshot for org",
        )
    try:
        kind_enum = KGEdgeKind(payload.edge_kind.strip().upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown edge kind: {payload.edge_kind!r}",
        ) from exc

    def _resolve(ref: str) -> Optional[KGNode]:
        for n in snap.nodes:
            if n.id == ref or n.ref == ref:
                return n
        return None

    a = _resolve(payload.src)
    b = _resolve(payload.dst)
    if a is None or b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="src or dst node not found in latest snapshot",
        )

    cached = store.get_edge_reasoning(
        payload.organization_id, a.id, b.id, kind_enum.value
    )
    if cached is not None:
        return {"ok": True, "cached": True, "reasoning": cached}

    edge = next(
        (
            e
            for e in snap.edges
            if e.src == a.id
            and e.dst == b.id
            and _enum_value(e.kind) == kind_enum.value
        ),
        None,
    )
    if edge is None:
        edge = KGEdge(
            id="kgedge_synthetic",
            src=a.id,
            dst=b.id,
            kind=kind_enum,
            weight=0.0,
            attrs={"synthetic": True},
        )

    llm = None
    if payload.use_llm:
        try:
            from noosphere.llm import llm_client_from_settings

            llm = llm_client_from_settings()
        except Exception:
            llm = None

    result: EdgeReasoning = await reason_about_edge(
        a, b, edge, store=store, llm=llm
    )
    try:
        store.put_edge_reasoning(
            payload.organization_id,
            a.id,
            b.id,
            kind_enum.value,
            result.model_dump(mode="json"),
        )
    except Exception:
        pass
    return {"ok": True, "cached": False, "reasoning": result.model_dump(mode="json")}


class GraphBuildRequest(BaseModel):
    organization_id: str = Field(min_length=1)


@router.post("/build", status_code=status.HTTP_202_ACCEPTED)
def rebuild_graph_endpoint(
    request_throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    payload: GraphBuildRequest,
) -> dict[str, Any]:
    """Operator: force a snapshot rebuild.

    Synchronous on purpose — the graph is small enough that operators
    expect to see the new snapshot id in the same request. A scheduler
    handles routine rebuilds.
    """
    snap = build_for_org(store, payload.organization_id, persist=True)
    return {
        "ok": True,
        "snapshot_id": snap.id,
        "node_count": snap.node_count,
        "edge_count": snap.edge_count,
        "snapshot_at": snap.snapshot_at.isoformat() if snap.snapshot_at else None,
    }


@router.get("/snapshots")
def list_snapshots_endpoint(
    request_throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    organization_id: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    rows = store.list_graph_snapshots(organization_id, limit=limit)
    return {
        "ok": True,
        "snapshots": [
            {
                "id": r["id"],
                "snapshot_at": r["snapshot_at"].isoformat()
                if r["snapshot_at"]
                else None,
                "version": r["version"],
                "node_count": r["node_count"],
                "edge_count": r["edge_count"],
                "notes": r["notes"],
            }
            for r in rows
        ],
    }
