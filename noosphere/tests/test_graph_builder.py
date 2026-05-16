"""Tests for the cross-source knowledge-graph builder (prompt 13)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable, Optional

import pytest

from noosphere.knowledge_graph import edge_extractors as edge_ex
from noosphere.knowledge_graph.builder import (
    KnowledgeGraphBuilder,
    build_for_org,
    incremental_update,
)
from noosphere.models import (
    Artifact,
    GraphSnapshot,
    KGEdgeKind,
    KGNodeKind,
    ProvenanceKind,
    Topic,
)


def _stub_principle(
    *,
    id: str,
    text: str,
    domain_of_applicability: str = "",
    source_artifact_id: Optional[str] = None,
    quantifiable_proxies: Optional[list[str]] = None,
):
    """SimpleNamespace stand-in for a Principle row.

    The canonical Pydantic Principle is strict-fielded and does not
    expose a source_artifact_id today; the builder reads the attribute
    via ``getattr(p, "source_artifact_id", None)``, so a lightweight
    namespace mirrors the runtime contract without the strict-schema
    drag.
    """
    return SimpleNamespace(
        id=id,
        text=text,
        description="",
        domain_of_applicability=domain_of_applicability,
        quantifiable_proxies=list(quantifiable_proxies or []),
        source_artifact_id=source_artifact_id,
        provenance=ProvenanceKind.PROPRIETARY,
        conviction_score=0.5,
    )
from noosphere.store import Store


class _FakeStore:
    """Minimal stand-in for ``Store`` covering only what the builder needs.

    Wraps a real in-memory ``Store`` for snapshot persistence — that
    path uses raw SQLModel tables so the rest of the codebase can swap
    in later without touching the test.
    """

    def __init__(
        self,
        *,
        principles: Iterable[Any] = (),
        algorithms: Iterable[Any] = (),
        memos: Iterable[Any] = (),
        topics: Iterable[Topic] = (),
        artifacts: Iterable[Artifact] = (),
        lifecycles: Iterable[Any] = (),
        contradiction_results: Iterable[Any] = (),
    ) -> None:
        self._principles = list(principles)
        self._algorithms = list(algorithms)
        self._memos = list(memos)
        self._topics = list(topics)
        self._artifacts = {a.id: a for a in artifacts}
        self._lifecycles = list(lifecycles)
        self._results = list(contradiction_results)
        self._inner = Store.from_database_url("sqlite:///:memory:")

    def list_principles(self) -> list[Any]:
        return list(self._principles)

    def list_algorithms_for_org(self, org_id: str) -> list[Any]:
        return list(self._algorithms)

    def list_investment_memos(self, *, organization_id: str, **_kw: Any) -> list[Any]:
        return list(self._memos)

    def list_topics(self) -> list[Topic]:
        return list(self._topics)

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def list_contradiction_lifecycles(self, **_kw: Any) -> list[Any]:
        return list(self._lifecycles)

    def list_contradiction_results(self, **_kw: Any) -> list[Any]:
        return list(self._results)

    # Snapshot persistence delegates straight to the in-memory Store.
    def put_graph_snapshot(self, snap) -> None:
        self._inner.put_graph_snapshot(snap)

    def get_latest_graph_snapshot(self, organization_id: str):
        return self._inner.get_latest_graph_snapshot(organization_id)

    def list_graph_snapshots(self, organization_id: str, *, limit: int = 50):
        return self._inner.list_graph_snapshots(organization_id, limit=limit)

    def put_edge_reasoning(self, *args: Any, **kwargs: Any) -> str:
        return self._inner.put_edge_reasoning(*args, **kwargs)

    def get_edge_reasoning(self, *args: Any, **kwargs: Any):
        return self._inner.get_edge_reasoning(*args, **kwargs)


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def fixture_corpus():
    artifact_a = Artifact(
        id="art_security_dilemma",
        uri="file:///docs/security_dilemma.pdf",
        mime_type="application/pdf",
        title="Security Dilemma — primer",
        byte_length=1024,
    )
    artifact_b = Artifact(
        id="art_attention_paper",
        uri="https://arxiv.org/attention",
        mime_type="application/pdf",
        title="Attention Is All You Need",
        byte_length=2048,
    )
    principle_a = _stub_principle(
        id="principle_security_dilemma",
        text="States facing other states arming will arm themselves.",
        domain_of_applicability="great-power competition",
        quantifiable_proxies=["defense spending YoY"],
        source_artifact_id=artifact_a.id,
    )
    principle_b = _stub_principle(
        id="principle_dark_enlightenment",
        text="Dark-enlightenment thinkers prefer hyperstition over critique.",
        domain_of_applicability="philosophy",
        source_artifact_id=artifact_b.id,
    )
    topic = Topic(id="topic_geopolitics", name="geopolitics", label="great-power")

    algorithm = SimpleNamespace(
        id="algorithm_arms_race",
        name="Arms-Race Escalation Predictor",
        source_principle_ids=["principle_security_dilemma"],
        status="DRAFT",
        weighting_multiplier=1.0,
        provenance=ProvenanceKind.PROPRIETARY,
        output=SimpleNamespace(
            name="arms_race_projection",
            description="great-power escalation outlook",
            fields=[{"name": "horizon_months"}],
        ),
    )
    memo = SimpleNamespace(
        id="memo_arms_race_2026",
        title="Arms-race outlook",
        status="DRAFT",
        question_type="EXPLANATORY",
        governing_principle_ids=["principle_security_dilemma"],
        observed_input_ids=["art_security_dilemma"],
    )

    lifecycle = SimpleNamespace(
        contradiction_id="contradiction_arms_dark",
        current_status="STANDING",
    )
    result = SimpleNamespace(
        id="contradiction_arms_dark",
        principle_a_id="principle_security_dilemma",
        principle_b_id="principle_dark_enlightenment",
        score=0.78,
        axis="empirical",
    )
    store = _FakeStore(
        principles=[principle_a, principle_b],
        algorithms=[algorithm],
        memos=[memo],
        topics=[topic],
        artifacts=[artifact_a, artifact_b],
        lifecycles=[lifecycle],
        contradiction_results=[result],
    )
    return store


# ── tests ───────────────────────────────────────────────────────────


def test_builder_emits_expected_node_and_edge_counts(fixture_corpus):
    snap = build_for_org(fixture_corpus, "org_test", persist=True)
    kinds = {n.kind for n in snap.nodes}
    assert {"PRINCIPLE", "ALGORITHM", "MEMO", "SOURCE", "TOPIC"} <= kinds
    # Two principles + one algorithm + one memo + two sources + one topic = 7.
    assert snap.node_count == 7
    edge_kinds = {e.kind for e in snap.edges}
    assert "DERIVED_FROM" in edge_kinds
    assert "INVOKES" in edge_kinds
    assert "CONTRADICTS" in edge_kinds
    assert "CITES" in edge_kinds


def test_derived_from_extractor_shape():
    art = Artifact(
        id="art_x",
        uri="file:///x",
        mime_type="text/plain",
        title="x",
        byte_length=10,
    )
    p = _stub_principle(id="p_x", text="t", source_artifact_id=art.id)
    index = {
        (KGNodeKind.PRINCIPLE, "p_x"): "n_principle",
        (KGNodeKind.SOURCE, "art_x"): "n_source",
    }
    edges = edge_ex.extract_derived_from(principles=[p], index=index)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.src == "n_principle"
    assert edge.dst == "n_source"
    assert edge.kind == KGEdgeKind.DERIVED_FROM.value


def test_invokes_extractor_emits_one_per_source_principle():
    algo = SimpleNamespace(
        id="a", source_principle_ids=["p1", "p2"]
    )
    index = {
        (KGNodeKind.ALGORITHM, "a"): "n_a",
        (KGNodeKind.PRINCIPLE, "p1"): "n_p1",
        (KGNodeKind.PRINCIPLE, "p2"): "n_p2",
    }
    edges = edge_ex.extract_invokes(algorithms=[algo], index=index)
    assert {e.dst for e in edges} == {"n_p1", "n_p2"}
    assert all(e.kind == KGEdgeKind.INVOKES.value for e in edges)


def test_contradicts_carries_score_and_excludes_disputed():
    lifecycle_keep = SimpleNamespace(
        contradiction_id="cid_keep", current_status="STANDING"
    )
    lifecycle_drop = SimpleNamespace(
        contradiction_id="cid_drop", current_status="DISPUTED_AS_ERROR"
    )
    row_keep = SimpleNamespace(
        principle_a_id="p_a", principle_b_id="p_b", score=0.9, axis="x"
    )
    row_drop = SimpleNamespace(
        principle_a_id="p_a", principle_b_id="p_b", score=0.9, axis="x"
    )
    index = {
        (KGNodeKind.PRINCIPLE, "p_a"): "n_a",
        (KGNodeKind.PRINCIPLE, "p_b"): "n_b",
    }
    edges = edge_ex.extract_contradicts(
        lifecycles=[lifecycle_keep, lifecycle_drop],
        contradiction_rows_by_id={
            "cid_keep": row_keep,
            "cid_drop": row_drop,
        },
        index=index,
    )
    assert len(edges) == 1
    edge = edges[0]
    assert edge.kind == KGEdgeKind.CONTRADICTS.value
    assert edge.weight == pytest.approx(0.9)
    assert edge.attrs.get("contradiction_id") == "cid_keep"


def test_supports_filters_llm_below_threshold():
    index = {
        (KGNodeKind.PRINCIPLE, "p_a"): "n_a",
        (KGNodeKind.PRINCIPLE, "p_b"): "n_b",
    }
    manual = [
        {
            "src_kind": "PRINCIPLE",
            "src_ref": "p_a",
            "dst_kind": "PRINCIPLE",
            "dst_ref": "p_b",
            "confidence": 1.0,
            "source": "MANUAL",
        }
    ]
    llm_rows = [
        {
            "src_kind": "PRINCIPLE",
            "src_ref": "p_a",
            "dst_kind": "PRINCIPLE",
            "dst_ref": "p_b",
            "confidence": 0.5,  # below 0.7 threshold
            "source": "LLM",
        }
    ]
    edges = edge_ex.extract_supports(
        manual_supports=manual,
        llm_supports=llm_rows,
        index=index,
        confidence_threshold=0.7,
    )
    assert len(edges) == 1
    assert edges[0].attrs.get("source") == "MANUAL"


def test_snapshot_persistence_is_append_only():
    store = Store.from_database_url("sqlite:///:memory:")
    snap1 = GraphSnapshot(
        organization_id="org_1",
        nodes=[],
        edges=[],
        node_count=0,
        edge_count=0,
        snapshot_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    snap2 = GraphSnapshot(
        organization_id="org_1",
        nodes=[],
        edges=[],
        node_count=0,
        edge_count=0,
        snapshot_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    store.put_graph_snapshot(snap1)
    store.put_graph_snapshot(snap2)
    history = store.list_graph_snapshots("org_1")
    assert len(history) == 2
    latest = store.get_latest_graph_snapshot("org_1")
    assert latest is not None and latest.id == snap2.id


def test_incremental_update_applies_principle_add(fixture_corpus):
    build_for_org(fixture_corpus, "org_test")
    new_principle = _stub_principle(id="principle_new", text="freshly extracted")
    fixture_corpus._principles.append(new_principle)
    deltas = incremental_update(
        fixture_corpus,
        {
            "kind": "principle_added",
            "organization_id": "org_test",
            "payload": {"principle_id": "principle_new"},
        },
    )
    assert any(d.target == "node" and d.payload.get("ref") == "principle_new" for d in deltas)
    latest = fixture_corpus.get_latest_graph_snapshot("org_test")
    assert latest is not None
    assert any(n.ref == "principle_new" for n in latest.nodes)


def test_incremental_update_emits_contradicts_edge(fixture_corpus):
    build_for_org(fixture_corpus, "org_test")
    deltas = incremental_update(
        fixture_corpus,
        {
            "kind": "contradiction_flagged",
            "organization_id": "org_test",
            "payload": {
                "contradiction_id": "new_contradiction",
                "principle_a_id": "principle_security_dilemma",
                "principle_b_id": "principle_dark_enlightenment",
                "score": 0.66,
            },
        },
    )
    assert any(
        d.target == "edge"
        and d.payload.get("kind") == KGEdgeKind.CONTRADICTS.value
        and d.payload.get("attrs", {}).get("contradiction_id") == "new_contradiction"
        for d in deltas
    )


def test_builder_class_wrapper_delegates(fixture_corpus):
    builder = KnowledgeGraphBuilder(fixture_corpus)
    snap = builder.build_for_org("org_test")
    assert snap.node_count > 0
