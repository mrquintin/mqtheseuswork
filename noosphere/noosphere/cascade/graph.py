from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import uuid4

from noosphere.literature.source_credibility import (
    BetaPosterior,
    aggregate_supports_confidence,
    modulated_supports_confidence,
)
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

    def mark_evidence_on_claim(
        self,
        *,
        claim_node_id: str,
        evidence_text: str,
        method_invocation_id: str,
        confidence: float,
        contradicts: bool = False,
    ) -> tuple[str, str]:
        """Operator UX hook: attach a new evidence artifact to an existing
        claim node and return ``(artifact_node_id, edge_id)`` so the caller
        can revert by retracting the edge if the founder cancels the
        revision preview. Pure graph-level — no revision plan is
        committed; that's the revision module's job."""
        artifact_id = self.add_node(
            kind=CascadeNodeKind.ARTIFACT,
            ref=f"revision-evidence:{evidence_text[:64]}",
            attrs={"text": evidence_text, "introduced_by": "revision"},
        )
        relation = (
            CascadeEdgeRelation.CONTRADICTS
            if contradicts
            else CascadeEdgeRelation.SUPPORTS
        )
        edge_id = self.add_edge(
            src=artifact_id,
            dst=claim_node_id,
            relation=relation,
            method_invocation_id=method_invocation_id,
            confidence=confidence,
        )
        return artifact_id, edge_id

    # ── source-credibility modulation ────────────────────────────────
    #
    # The cascade graph stores a base ``confidence`` per supports edge.
    # That confidence is the *upstream* assertion strength (how strongly
    # the supporting evidence claims it supports the target). The
    # *effective* contribution of that edge to the target claim's
    # evidence weight is bounded by the credibility of the cited source
    # — a 0.9-confidence support from a tabloid X-post does not carry
    # 0.9 weight if that source's credibility posterior sits at 0.3.
    #
    # The two helpers below make this modulation explicit and
    # auditable. They are pure functions on the inputs so cascade
    # callers can verify behaviour in tests without touching graph
    # state. The aggregator is capped at the maximum credibility of any
    # single contributing source: piling on low-credibility supports
    # cannot manufacture high confidence.

    @staticmethod
    def modulate_supports_edge(
        base_confidence: float,
        posterior: Optional[BetaPosterior],
    ) -> float:
        """Effective confidence for one supports edge given its source.

        Returns ``base_confidence * posterior.mean`` (clamped to
        [0, 1]); falls back to a neutral 0.5 multiplier if the source
        is not yet in the credibility ledger.
        """

        return modulated_supports_confidence(base_confidence, posterior)

    @staticmethod
    def aggregate_supports(
        contributions: Iterable[tuple[float, Optional[BetaPosterior]]],
    ) -> float:
        """Pool multiple supports edges into a single evidence weight.

        ``contributions`` is an iterable of
        ``(base_confidence, posterior)`` for each supports edge feeding
        the same target claim. The result is bounded above by the
        maximum credibility among contributors, so weak evidence does
        not multiply into strong evidence.
        """

        return aggregate_supports_confidence(contributions)

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
