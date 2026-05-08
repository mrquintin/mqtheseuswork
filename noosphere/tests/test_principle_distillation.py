"""Tests for the corpus-level principle distillation pipeline."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from noosphere.distillation import (
    DraftPrinciple,
    PrincipleDistillationPipeline,
    PrincipleStatus,
    compute_conviction,
    redistill,
)
from noosphere.models import Conclusion, Discipline


# ── Conviction scoring ───────────────────────────────────────────────────────


def test_conviction_zero_for_empty_cluster() -> None:
    assert compute_conviction(
        cluster_size=0, domain_breadth=0, centrality_scores=[]
    ) == 0.0


def test_conviction_single_domain_is_capped() -> None:
    # 6 conclusions, all in one domain, all very central — must
    # not approach high conviction.  The constraint: "a single
    # high-centrality conclusion does not produce conviction;
    # convergence across domains does."
    score = compute_conviction(
        cluster_size=6,
        domain_breadth=1,
        centrality_scores=[0.95] * 6,
    )
    assert score < 0.5
    # Multi-domain version with the same size + centrality must score higher.
    multi = compute_conviction(
        cluster_size=6,
        domain_breadth=4,
        centrality_scores=[0.95] * 6,
    )
    assert multi > score


def test_conviction_reflects_breadth_over_centrality() -> None:
    narrow_high_centrality = compute_conviction(
        cluster_size=4, domain_breadth=1, centrality_scores=[0.99] * 4
    )
    broad_lower_centrality = compute_conviction(
        cluster_size=4, domain_breadth=4, centrality_scores=[0.6] * 4
    )
    assert broad_lower_centrality > narrow_high_centrality


def test_conviction_in_unit_interval() -> None:
    score = compute_conviction(
        cluster_size=999, domain_breadth=999, centrality_scores=[1.0] * 16
    )
    assert 0.0 <= score <= 1.0


# ── Pipeline (with stubs) ────────────────────────────────────────────────────


class _StubEmbedder:
    """Deterministic embedder: each conclusion emits a hand-set vector."""

    def __init__(self, vectors_by_text: dict[str, list[float]]) -> None:
        self._vectors = vectors_by_text

    @property
    def model_name(self) -> str:
        return "stub"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vectors[t]) for t in texts]


class _StubDistiller:
    """Stand-in for PrincipleDistiller that the pipeline calls into."""

    def __init__(self, *, drafted: dict[tuple[str, ...], dict[str, Any]]) -> None:
        self._drafted = drafted
        self.cluster_calls = 0
        self.draft_calls = 0

    def cluster_conclusions(
        self,
        *,
        conclusions,
        embeddings,
        clustering_threshold,
        min_cluster_size,
    ):
        self.cluster_calls += 1
        # Cluster by integer label encoded in vector[0].
        groups: dict[int, list[int]] = {}
        for i, v in enumerate(embeddings):
            groups.setdefault(int(v[0]), []).append(i)
        return [g for g in groups.values() if len(g) >= min_cluster_size]

    def draft_principle_for_conclusions(self, cluster):
        self.draft_calls += 1
        key = tuple(c.id for c in cluster)
        return self._drafted.get(key)


def _conclusion(cid: str, text: str, disciplines: list[Discipline]) -> Conclusion:
    return Conclusion(id=cid, text=text, disciplines=disciplines)


def test_pipeline_produces_cross_domain_drafts() -> None:
    # 4 conclusions in cluster "0" across 2 domains, 1 stray in cluster "1".
    a = _conclusion("c1", "alpha", [Discipline.PHILOSOPHY])
    b = _conclusion("c2", "beta", [Discipline.PHILOSOPHY])
    c = _conclusion("c3", "gamma", [Discipline.AI])
    d = _conclusion("c4", "delta", [Discipline.AI])
    e = _conclusion("c5", "epsilon", [Discipline.PHILOSOPHY])

    embedder = _StubEmbedder(
        {
            "alpha": [0, 0.9],
            "beta": [0, 0.95],
            "gamma": [0, 0.92],
            "delta": [0, 0.93],
            "epsilon": [1, 0.0],
        }
    )

    distiller = _StubDistiller(
        drafted={
            ("c1", "c2", "c3", "c4"): {
                "text": "When forced to choose, the firm prefers calibration over coverage.",
                "domains": ["Philosophy", "AI"],
                "cited_conclusion_ids": ["c1", "c3"],
            }
        }
    )

    pipeline = PrincipleDistillationPipeline(
        distiller=distiller,
        embedder=embedder,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
    )
    drafts = pipeline.run([a, b, c, d, e])

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.text.startswith("When forced to choose")
    assert sorted(draft.cluster_conclusion_ids) == ["c1", "c2", "c3", "c4"]
    assert draft.cited_conclusion_ids == ["c1", "c3"]
    assert draft.domain_breadth >= 2
    assert 0.0 < draft.conviction_score <= 1.0
    assert draft.status == PrincipleStatus.DRAFT


def test_pipeline_drops_clusters_below_min_size() -> None:
    a = _conclusion("c1", "alpha", [Discipline.PHILOSOPHY])
    b = _conclusion("c2", "beta", [Discipline.AI])
    embedder = _StubEmbedder({"alpha": [0, 1.0], "beta": [0, 1.0]})
    distiller = _StubDistiller(drafted={})
    pipeline = PrincipleDistillationPipeline(
        distiller=distiller,
        embedder=embedder,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
    )
    assert pipeline.run([a, b]) == []
    # The min-cluster gate trips before the LLM is called.
    assert distiller.draft_calls == 0


def test_pipeline_skips_when_llm_returns_no_citations() -> None:
    a = _conclusion("c1", "alpha", [Discipline.PHILOSOPHY])
    b = _conclusion("c2", "beta", [Discipline.PHILOSOPHY])
    c = _conclusion("c3", "gamma", [Discipline.AI])
    d = _conclusion("c4", "delta", [Discipline.AI])
    embedder = _StubEmbedder(
        {"alpha": [0, 1], "beta": [0, 1], "gamma": [0, 1], "delta": [0, 1]}
    )
    # LLM returns None — drafts must be skipped (constraint: no free invention).
    distiller = _StubDistiller(drafted={("c1", "c2", "c3", "c4"): None})  # type: ignore[dict-item]
    pipeline = PrincipleDistillationPipeline(
        distiller=distiller,
        embedder=embedder,
        clustering_threshold=0.5,
        min_cluster_size=4,
        min_domain_breadth=2,
    )
    assert pipeline.run([a, b, c, d]) == []


# ── Re-derivation diff ──────────────────────────────────────────────────────


def test_redistill_dissolved_cluster_is_flagged() -> None:
    existing = [
        {
            "id": "p1",
            "text": "old principle",
            "domains": ["Philosophy"],
            "cluster_conclusion_ids": ["x1", "x2", "x3"],
            "conviction_score": 0.6,
        }
    ]
    # No fresh draft mentions any of those ids → full drift.
    fresh = [
        DraftPrinciple(
            text="new",
            domains=["AI"],
            cited_conclusion_ids=["c1"],
            cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
            conviction_score=0.5,
            domain_breadth=1,
            cluster_centroid_similarity=0.9,
        )
    ]
    flagged = redistill(fresh, existing_principles=existing)
    assert len(flagged) == 1
    assert flagged[0].existing_principle_id == "p1"
    assert flagged[0].drift_reason == "cluster_dissolved"
    assert flagged[0].status == PrincipleStatus.NEEDS_REREVIEW


def test_redistill_growing_cluster_marks_draft_for_rereview() -> None:
    existing = [
        {
            "id": "p1",
            "text": "old",
            "cluster_conclusion_ids": ["c1", "c2"],
            "conviction_score": 0.6,
        }
    ]
    fresh = [
        DraftPrinciple(
            text="new",
            domains=["Philosophy", "AI"],
            cited_conclusion_ids=["c1", "c3"],
            cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
            conviction_score=0.7,
            domain_breadth=2,
            cluster_centroid_similarity=0.9,
        )
    ]
    flagged = redistill(fresh, existing_principles=existing)
    # The growing case mutates the matching draft instead of adding a row.
    assert flagged == []
    assert fresh[0].status == PrincipleStatus.NEEDS_REREVIEW
    assert fresh[0].existing_principle_id == "p1"
    assert fresh[0].drift_reason == "cluster_grew"


def test_redistill_unchanged_cluster_is_not_flagged() -> None:
    existing = [
        {"id": "p1", "cluster_conclusion_ids": ["c1", "c2", "c3"]}
    ]
    fresh = [
        DraftPrinciple(
            text="x",
            domains=["AI", "Philosophy"],
            cited_conclusion_ids=["c1"],
            cluster_conclusion_ids=["c1", "c2", "c3"],
            conviction_score=0.5,
            domain_breadth=2,
            cluster_centroid_similarity=0.9,
        )
    ]
    flagged = redistill(fresh, existing_principles=existing)
    assert flagged == []
    assert fresh[0].status == PrincipleStatus.DRAFT
    assert fresh[0].existing_principle_id is None


# ── Serialization ───────────────────────────────────────────────────────────


def test_draft_to_dict_roundtrip() -> None:
    d = DraftPrinciple(
        text="abc",
        domains=["AI"],
        cited_conclusion_ids=["c1"],
        cluster_conclusion_ids=["c1", "c2"],
        conviction_score=0.42,
        domain_breadth=1,
        cluster_centroid_similarity=0.81,
    )
    payload = d.to_dict()
    # JSON-serializable.
    json.dumps(payload)
    assert payload["text"] == "abc"
    assert payload["status"] == PrincipleStatus.DRAFT
