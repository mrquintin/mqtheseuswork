"""Tests for basic cascade edge insert, retract, and iter operations."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.models import (
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
    MethodInvocation,
)
from noosphere.store import CascadeEdgeConflictError, CascadeEdgeOrphanError, Store
from noosphere.cascade.graph import CascadeCycleError, CascadeGraph


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_inv(**kw) -> MethodInvocation:
    d = dict(
        id=_uid(), method_id=_uid(),
        input_hash="ih", output_hash="oh",
        started_at=_now(), ended_at=_now(),
        succeeded=True, error_kind=None,
        correlation_id=_uid(), tenant_id="t1",
    )
    d.update(kw)
    return MethodInvocation(**d)


def _setup():
    store = _store()
    inv = _make_inv()
    store.insert_method_invocation(inv)
    graph = CascadeGraph(store)
    return store, graph, inv


class TestInsertEdge:
    def test_insert_and_iter(self):
        store, graph, inv = _setup()
        eid = graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.85,
        )
        assert isinstance(eid, str)
        edges = list(graph.iter_edges(src="a"))
        assert len(edges) == 1
        assert edges[0].src == "a"
        assert edges[0].dst == "b"
        assert edges[0].relation == CascadeEdgeRelation.SUPPORTS
        assert edges[0].confidence == 0.85

    def test_iter_by_dst(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="x", dst="y",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        edges = list(graph.iter_edges(dst="y"))
        assert len(edges) == 1
        assert edges[0].src == "x"

    def test_iter_by_relation(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.add_edge(
            src="a", dst="c",
            relation=CascadeEdgeRelation.REFUTES,
            method_invocation_id=inv.id,
            confidence=0.7,
        )
        supports = list(graph.iter_edges(relation=CascadeEdgeRelation.SUPPORTS.value))
        assert len(supports) == 1
        assert supports[0].dst == "b"

    def test_orphan_edge_raises(self):
        store = _store()
        graph = CascadeGraph(store)
        with pytest.raises(CascadeEdgeOrphanError):
            graph.add_edge(
                src="a", dst="b",
                relation=CascadeEdgeRelation.SUPPORTS,
                method_invocation_id="nonexistent",
                confidence=0.5,
            )


class TestRetractEdge:
    def test_retract_excludes_from_iter(self):
        store, graph, inv = _setup()
        eid = graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.retract_edge(eid)
        assert list(graph.iter_edges(src="a")) == []

    def test_retract_visible_with_include_retracted(self):
        store, graph, inv = _setup()
        eid = graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.retract_edge(eid)
        edges = list(graph.iter_edges(src="a", include_retracted=True))
        assert len(edges) == 1
        assert edges[0].retracted_at is not None

    def test_retract_nonexistent_is_noop(self):
        store, graph, inv = _setup()
        graph.retract_edge("nonexistent-id")


class TestConflictDetection:
    def test_supports_then_refutes_conflict(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        with pytest.raises(CascadeEdgeConflictError):
            graph.add_edge(
                src="a", dst="b",
                relation=CascadeEdgeRelation.REFUTES,
                method_invocation_id=inv.id,
                confidence=0.5,
            )

    def test_retracted_conflict_allows_new_edge(self):
        store, graph, inv = _setup()
        eid = graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.retract_edge(eid)
        eid2 = graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.REFUTES,
            method_invocation_id=inv.id,
            confidence=0.8,
        )
        assert isinstance(eid2, str)
