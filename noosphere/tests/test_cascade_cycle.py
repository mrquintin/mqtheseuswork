"""Tests for cycle detection in the depends_on subgraph."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.models import CascadeEdgeRelation, MethodInvocation
from noosphere.store import Store
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


class TestCycleDetection:
    def test_direct_cycle_raises(self):
        _, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        with pytest.raises(CascadeCycleError):
            graph.add_edge(
                src="b", dst="a",
                relation=CascadeEdgeRelation.DEPENDS_ON,
                method_invocation_id=inv.id,
                confidence=1.0,
            )

    def test_transitive_cycle_raises(self):
        _, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        graph.add_edge(
            src="b", dst="c",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        with pytest.raises(CascadeCycleError):
            graph.add_edge(
                src="c", dst="a",
                relation=CascadeEdgeRelation.DEPENDS_ON,
                method_invocation_id=inv.id,
                confidence=1.0,
            )

    def test_self_loop_raises(self):
        _, graph, inv = _setup()
        with pytest.raises(CascadeCycleError):
            graph.add_edge(
                src="a", dst="a",
                relation=CascadeEdgeRelation.DEPENDS_ON,
                method_invocation_id=inv.id,
                confidence=1.0,
            )

    def test_non_depends_on_allows_cycle(self):
        """Cycles are only checked for depends_on relation."""
        _, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        eid = graph.add_edge(
            src="b", dst="a",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        assert isinstance(eid, str)

    def test_dag_without_cycle_succeeds(self):
        _, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        graph.add_edge(
            src="a", dst="c",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        eid = graph.add_edge(
            src="b", dst="c",
            relation=CascadeEdgeRelation.DEPENDS_ON,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        assert isinstance(eid, str)
