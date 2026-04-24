"""Tests for cascade cut operation and confidence deltas."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.models import CascadeEdgeRelation, MethodInvocation
from noosphere.store import Store
from noosphere.cascade.graph import CascadeGraph
from noosphere.cascade.traverse import cut, downstream, explain


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


class TestCut:
    def test_cut_single_support_orphans_dependent(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="evidence", dst="conclusion",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        report = cut(store, "evidence")
        assert len(report.affected_edges) == 1
        assert "conclusion" in report.orphaned_nodes
        assert report.confidence_deltas["conclusion"] == pytest.approx(-0.9)

    def test_cut_with_multiple_supports_no_orphan(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="ev1", dst="conclusion",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.8,
        )
        graph.add_edge(
            src="ev2", dst="conclusion",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.7,
        )
        report = cut(store, "ev1")
        assert "conclusion" not in report.orphaned_nodes
        assert report.confidence_deltas["conclusion"] == pytest.approx(-0.8)

    def test_cut_node_with_no_outgoing(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="leaf",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.5,
        )
        report = cut(store, "leaf")
        assert len(report.affected_edges) == 0
        assert len(report.orphaned_nodes) == 0

    def test_cut_cascading_confidence(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="raw", dst="claim",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        graph.add_edge(
            src="claim", dst="principle",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.85,
        )
        report_raw = cut(store, "raw")
        assert "claim" in report_raw.orphaned_nodes

        report_claim = cut(store, "claim")
        assert "principle" in report_claim.orphaned_nodes
        assert report_claim.confidence_deltas["principle"] == pytest.approx(-0.85)


class TestExplainAndDownstream:
    def test_explain_returns_incoming(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="ev1", dst="target",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.add_edge(
            src="ev2", dst="target",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        basis = explain(store, "target")
        assert len(basis) == 2
        sources = {e.src for e in basis}
        assert sources == {"ev1", "ev2"}

    def test_downstream_returns_outgoing(self):
        store, graph, inv = _setup()
        graph.add_edge(
            src="source", dst="t1",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.add_edge(
            src="source", dst="t2",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.8,
        )
        out = downstream(store, "source")
        assert len(out) == 2
        dsts = {e.dst for e in out}
        assert dsts == {"t1", "t2"}
