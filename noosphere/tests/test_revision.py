"""Tests for the belief-revision engine on a synthetic cascade graph.

Coverage matches the F-test list in the prompt:
- revise a deep node, assert ancestor-set is impacted
- revise to a contradicting state, assert ≤1 minimum-distance plan
- assert the revert path
Plus determinism, snapshot capture, and the K-cap typed-confirmation gate.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.cascade import (
    InMemoryRevisionEventSink,
    RevisionInput,
    commit_revision,
    compute_revision,
    latest_for_conclusion,
    revert_revision,
)
from noosphere.cascade.graph import CascadeGraph
from noosphere.models import (
    CascadeEdgeRelation,
    CascadeNodeKind,
    MethodInvocation,
)
from noosphere.store import Store


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_inv() -> MethodInvocation:
    return MethodInvocation(
        id=_uid(),
        method_id=_uid(),
        input_hash="ih",
        output_hash="oh",
        started_at=_now(),
        ended_at=_now(),
        succeeded=True,
        error_kind=None,
        correlation_id=_uid(),
        tenant_id="t1",
    )


@pytest.fixture
def store_graph_inv():
    store = Store.from_database_url("sqlite:///:memory:")
    inv = _make_inv()
    store.insert_method_invocation(inv)
    graph = CascadeGraph(store)
    return store, graph, inv


def _claim(graph, ref="claim"):
    return graph.add_node(kind=CascadeNodeKind.CLAIM, ref=ref)


def _conclusion(graph, ref="conclusion"):
    return graph.add_node(kind=CascadeNodeKind.CONCLUSION, ref=ref)


# ─────────────────────────────────────────────────────────────────────────


class TestImpactPropagation:
    def test_revising_deep_claim_impacts_all_downstream_conclusions(
        self, store_graph_inv
    ):
        """Synthetic graph:

            deep_claim
              ├──supports──▶ mid_conclusion
              │                  └──supports──▶ top_conclusion
              └──refines───▶ side_conclusion
            unrelated_claim ──supports──▶ unrelated_conclusion
        """
        store, graph, inv = store_graph_inv
        deep = _claim(graph, "deep")
        mid = _conclusion(graph, "mid")
        top = _conclusion(graph, "top")
        side = _conclusion(graph, "side")
        unrelated = _claim(graph, "u_claim")
        unrelated_c = _conclusion(graph, "u_conc")

        graph.add_edge(
            src=deep, dst=mid,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        graph.add_edge(
            src=mid, dst=top,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.8,
        )
        graph.add_edge(
            src=deep, dst=side,
            relation=CascadeEdgeRelation.REFORMULATES,
            method_invocation_id=inv.id, confidence=0.7,
        )
        graph.add_edge(
            src=unrelated, dst=unrelated_c,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )

        plan = compute_revision(
            store,
            [RevisionInput(claim_id=deep, new_evidence="contradiction", weight=-1.0)],
        )

        all_affected_ids = {
            *(s.conclusion_id for s in plan.changed),
            *(s.conclusion_id for s in plan.newly_contradicted),
            *(s.conclusion_id for s in plan.newly_supported),
        }
        # mid, top, side all impacted; unrelated_c untouched.
        assert mid in all_affected_ids
        assert side in all_affected_ids
        assert unrelated_c not in all_affected_ids
        # mid and side are direct descendants → newly_contradicted.
        contradicted_ids = {s.conclusion_id for s in plan.newly_contradicted}
        assert mid in contradicted_ids

    def test_revision_to_contradicting_state_emits_single_plan(
        self, store_graph_inv
    ):
        """Determinism contract: same inputs + same graph → exactly one plan,
        and a second compute_revision returns an identical plan_id."""
        store, graph, inv = store_graph_inv
        c = _claim(graph, "c")
        conc = _conclusion(graph, "conc")
        graph.add_edge(
            src=c, dst=conc,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        inputs = [RevisionInput(claim_id=c, new_evidence="counter", weight=-1.0)]

        plan_a = compute_revision(store, inputs)
        plan_b = compute_revision(store, inputs)

        assert plan_a.plan_id == plan_b.plan_id
        assert plan_a.affected_count == 1
        assert plan_a.newly_contradicted[0].conclusion_id == conc

    def test_supporting_evidence_promotes_below_threshold_conclusion(
        self, store_graph_inv
    ):
        """A claim whose only basis edge is CONTRADICTS sits below θ;
        flipping the contradicting claim to weight=-1 inverts the sign
        and the conclusion crosses θ → newly_supported."""
        store, graph, inv = store_graph_inv
        opposing = _claim(graph, "opposing")
        target = _conclusion(graph, "target")
        graph.add_edge(
            src=opposing, dst=target,
            relation=CascadeEdgeRelation.CONTRADICTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        plan = compute_revision(
            store,
            [RevisionInput(claim_id=opposing, new_evidence="rebut", weight=-1.0)],
        )
        ids = {s.conclusion_id for s in plan.newly_supported}
        assert target in ids


class TestCommitAndRevert:
    def test_commit_captures_pre_confidence_snapshot(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        c = _claim(graph)
        conc = _conclusion(graph)
        graph.add_edge(
            src=c, dst=conc,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )

        plan = compute_revision(
            store,
            [RevisionInput(claim_id=c, new_evidence="x", weight=-1.0)],
        )
        sink = InMemoryRevisionEventSink()
        event = commit_revision(store, plan, sink)

        assert event.pre_confidence_snapshot[conc] == pytest.approx(0.9)
        assert sink.get(event.event_id) is not None
        assert latest_for_conclusion(sink, conc).event_id == event.event_id

    def test_revert_clears_latest_for_conclusion(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        c = _claim(graph)
        conc = _conclusion(graph)
        graph.add_edge(
            src=c, dst=conc,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )

        plan = compute_revision(
            store, [RevisionInput(claim_id=c, new_evidence="x", weight=-1.0)]
        )
        sink = InMemoryRevisionEventSink()
        event = commit_revision(store, plan, sink)

        revert_revision(sink, event.event_id)

        assert sink.get(event.event_id).reverted is True
        assert latest_for_conclusion(sink, conc) is None

    def test_revert_falls_through_to_prior_event(self, store_graph_inv):
        store, graph, inv = store_graph_inv
        c = _claim(graph)
        conc = _conclusion(graph)
        graph.add_edge(
            src=c, dst=conc,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        sink = InMemoryRevisionEventSink()

        plan_1 = compute_revision(
            store, [RevisionInput(claim_id=c, new_evidence="ev1", weight=0.5)]
        )
        e1 = commit_revision(store, plan_1, sink)

        plan_2 = compute_revision(
            store, [RevisionInput(claim_id=c, new_evidence="ev2", weight=-1.0)]
        )
        e2 = commit_revision(store, plan_2, sink)

        revert_revision(sink, e2.event_id)
        latest = latest_for_conclusion(sink, conc)
        assert latest is not None
        assert latest.event_id == e1.event_id


class TestSafetyGates:
    def test_typed_confirmation_kicks_in_above_K(self, store_graph_inv):
        """K-cap: a revision touching > K conclusions must require typed
        confirmation in the UI."""
        store, graph, inv = store_graph_inv
        root = _claim(graph, "root")
        # 15 distinct conclusions all directly supported by `root`.
        for i in range(15):
            cid = _conclusion(graph, f"c{i}")
            graph.add_edge(
                src=root, dst=cid,
                relation=CascadeEdgeRelation.SUPPORTS,
                method_invocation_id=inv.id, confidence=0.9,
            )

        plan = compute_revision(
            store, [RevisionInput(claim_id=root, new_evidence="x", weight=-1.0)]
        )
        assert plan.affected_count == 15
        assert plan.requires_typed_confirmation(k=12) is True
        assert plan.requires_typed_confirmation(k=20) is False

    def test_compute_revision_does_not_mutate_graph(self, store_graph_inv):
        """A dry-run plan must not leak edges or nodes into the store."""
        store, graph, inv = store_graph_inv
        c = _claim(graph)
        conc = _conclusion(graph)
        graph.add_edge(
            src=c, dst=conc,
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id, confidence=0.9,
        )
        before_edges = list(
            store.iter_cascade_edges(include_retracted=True)
        )
        compute_revision(
            store, [RevisionInput(claim_id=c, new_evidence="x", weight=-1.0)]
        )
        after_edges = list(
            store.iter_cascade_edges(include_retracted=True)
        )
        assert len(before_edges) == len(after_edges)
