from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from noosphere.models import (
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
)

logger = logging.getLogger(__name__)


class CascadeCycleError(Exception):
    """Adding this edge would create a cycle in the depends_on subgraph."""


class CascadeGraph:
    def __init__(self, store) -> None:  # noqa: ANN001
        self._store = store

    # ── node helpers ────────────────────────────────────────────────────

    def add_node(
        self,
        *,
        kind: CascadeNodeKind,
        ref: str,
        attrs: Optional[dict] = None,
        node_id: Optional[str] = None,
    ) -> str:
        nid = node_id or str(uuid4())
        node = CascadeNode(
            node_id=nid,
            kind=kind,
            ref=ref,
            attrs=attrs or {},
        )
        self._store.insert_cascade_node(node)
        return nid

    # ── edge helpers ────────────────────────────────────────────────────

    def add_edge(
        self,
        *,
        src: str,
        dst: str,
        relation: CascadeEdgeRelation,
        method_invocation_id: str,
        confidence: float,
        unresolved: bool = False,
    ) -> str:
        from noosphere.store import CascadeEdgeConflictError, CascadeEdgeOrphanError

        inv = self._store.get_method_invocation(method_invocation_id)
        if inv is None:
            raise CascadeEdgeOrphanError(
                f"method_invocation_id {method_invocation_id!r} not found"
            )

        if relation in (CascadeEdgeRelation.SUPPORTS, CascadeEdgeRelation.REFUTES):
            opposite = (
                CascadeEdgeRelation.REFUTES
                if relation == CascadeEdgeRelation.SUPPORTS
                else CascadeEdgeRelation.SUPPORTS
            )
            for existing in self._store.iter_cascade_edges(
                src=src, dst=dst, relation=opposite.value, include_retracted=False
            ):
                raise CascadeEdgeConflictError(
                    f"Non-retracted {opposite.value} edge exists "
                    f"between {src} -> {dst}"
                )

        if relation == CascadeEdgeRelation.DEPENDS_ON:
            self._check_cycle(src, dst)

        edge_id = str(uuid4())
        edge = CascadeEdge(
            edge_id=edge_id,
            src=src,
            dst=dst,
            relation=relation,
            method_invocation_id=method_invocation_id,
            confidence=confidence,
            unresolved=unresolved,
            established_at=datetime.now(timezone.utc),
        )
        self._store.insert_cascade_edge(edge)
        return edge_id

    def retract_edge(self, edge_id: str) -> None:
        self._store.retract_cascade_edge(edge_id, datetime.now(timezone.utc))

    def iter_edges(
        self,
        *,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        relation: Optional[str] = None,
        include_retracted: bool = False,
    ):
        yield from self._store.iter_cascade_edges(
            src=src, dst=dst, relation=relation, include_retracted=include_retracted
        )

    # ── cycle detection ─────────────────────────────────────────────────

    def _check_cycle(self, src: str, dst: str) -> None:
        """BFS forward from dst in depends_on subgraph; if we reach src it's a cycle."""
        visited: set[str] = set()
        queue: deque[str] = deque([dst])
        while queue:
            current = queue.popleft()
            if current == src:
                raise CascadeCycleError(
                    f"Adding depends_on edge {src} -> {dst} would create a cycle"
                )
            if current in visited:
                continue
            visited.add(current)
            for edge in self._store.iter_cascade_edges(
                src=current,
                relation=CascadeEdgeRelation.DEPENDS_ON.value,
                include_retracted=False,
            ):
                queue.append(edge.dst)
