from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from noosphere.models import CascadeEdge, CascadeEdgeRelation


@dataclass
class CutReport:
    """Result of cutting a node from the cascade graph."""
    cut_node_id: str
    affected_edges: list[CascadeEdge] = field(default_factory=list)
    orphaned_nodes: list[str] = field(default_factory=list)
    confidence_deltas: dict[str, float] = field(default_factory=dict)


def explain(store, node_id: str) -> list[CascadeEdge]:
    """Return all non-retracted edges pointing INTO node_id (its evidence basis)."""
    return list(store.iter_cascade_edges(dst=node_id, include_retracted=False))


def downstream(store, node_id: str) -> list[CascadeEdge]:
    """Return all non-retracted edges whose src is node_id (what it supports)."""
    return list(store.iter_cascade_edges(src=node_id, include_retracted=False))


def cut(store, node_id: str) -> CutReport:
    """Simulate cutting a node: retract its outgoing edges and compute confidence deltas."""
    report = CutReport(cut_node_id=node_id)

    outgoing = list(store.iter_cascade_edges(src=node_id, include_retracted=False))
    report.affected_edges = outgoing

    affected_dst_nodes: set[str] = set()
    for edge in outgoing:
        affected_dst_nodes.add(edge.dst)

    for dst_node in affected_dst_nodes:
        incoming = list(store.iter_cascade_edges(dst=dst_node, include_retracted=False))
        support_edges = [
            e for e in incoming
            if e.relation in (
                CascadeEdgeRelation.SUPPORTS,
                CascadeEdgeRelation.EXTRACTED_FROM,
                CascadeEdgeRelation.AGGREGATES,
                CascadeEdgeRelation.DEPENDS_ON,
            )
        ]
        total_confidence = sum(e.confidence for e in support_edges)
        cut_confidence = sum(
            e.confidence for e in support_edges if e.src == node_id
        )
        delta = -cut_confidence if total_confidence > 0 else 0.0
        report.confidence_deltas[dst_node] = delta

        remaining = [e for e in support_edges if e.src != node_id]
        if not remaining:
            report.orphaned_nodes.append(dst_node)

    return report
