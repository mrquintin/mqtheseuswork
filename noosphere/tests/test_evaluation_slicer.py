"""Tests for CorpusSlicer — out-of-slice reads raise EmbargoViolation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.models import (
    Artifact,
    Chunk,
    Claim,
    Conclusion,
    CorpusSelector,
    Outcome,
    OutcomeKind,
    Speaker,
    TemporalCut,
)
from noosphere.evaluation.slicer import CorpusSlicer, EmbargoViolation


CUT_DATE = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _make_cut(as_of: datetime | None = None) -> TemporalCut:
    dt = as_of or CUT_DATE
    return TemporalCut(
        cut_id="test-cut",
        as_of=dt,
        corpus_slice=CorpusSelector(as_of=dt),
        embargoed=CorpusSelector(as_of=dt),
        embedding_version_pin="default",
        outcomes=[],
    )


class FakeStore:
    def __init__(self):
        self.artifacts: dict[str, Artifact] = {}
        self.claims: dict[str, Claim] = {}
        self.chunks: dict[str, Chunk] = {}
        self.conclusions: dict[str, Conclusion] = {}

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def get_claim(self, claim_id: str):
        return self.claims.get(claim_id)

    def get_chunk(self, chunk_id: str):
        return self.chunks.get(chunk_id)

    def get_conclusion(self, conclusion_id: str):
        return self.conclusions.get(conclusion_id)

    def get_embedding_vector(self, embedding_id: str):
        return None

    def list_claim_ids(self):
        return list(self.claims.keys())

    def list_conclusions(self):
        return list(self.conclusions.values())

    def list_chunks_for_artifact(self, artifact_id: str):
        return [c for c in self.chunks.values() if c.artifact_id == artifact_id]

    def list_drift_events(self, *, limit=500):
        return []

    def get_temporal_cut(self, cut_id: str):
        return None

    def list_outcomes_for_cut(self, cut_id: str):
        return []


def test_artifact_before_cut_passes():
    store = FakeStore()
    store.artifacts["a1"] = Artifact(
        id="a1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    slicer = CorpusSlicer(store, _make_cut())
    result = slicer.get_artifact("a1")
    assert result is not None
    assert result.id == "a1"


def test_artifact_after_cut_raises():
    store = FakeStore()
    store.artifacts["a2"] = Artifact(
        id="a2", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc)
    )
    slicer = CorpusSlicer(store, _make_cut())
    with pytest.raises(EmbargoViolation, match="a2"):
        slicer.get_artifact("a2")


def test_missing_artifact_returns_none():
    store = FakeStore()
    slicer = CorpusSlicer(store, _make_cut())
    assert slicer.get_artifact("missing") is None


def test_claim_before_cut_passes():
    from datetime import date

    store = FakeStore()
    store.claims["c1"] = Claim(
        id="c1",
        text="test",
        speaker=Speaker(name="alice"),
        episode_id="ep1",
        episode_date=date(2025, 3, 1),
    )
    slicer = CorpusSlicer(store, _make_cut())
    result = slicer.get_claim("c1")
    assert result is not None


def test_claim_after_cut_raises():
    from datetime import date

    store = FakeStore()
    store.claims["c2"] = Claim(
        id="c2",
        text="future claim",
        speaker=Speaker(name="bob"),
        episode_id="ep2",
        episode_date=date(2025, 9, 1),
    )
    slicer = CorpusSlicer(store, _make_cut())
    with pytest.raises(EmbargoViolation, match="c2"):
        slicer.get_claim("c2")


def test_conclusion_after_cut_raises():
    store = FakeStore()
    store.conclusions["con1"] = Conclusion(
        id="con1",
        text="future conclusion",
        created_at=datetime(2025, 8, 1, tzinfo=timezone.utc),
    )
    slicer = CorpusSlicer(store, _make_cut())
    with pytest.raises(EmbargoViolation, match="con1"):
        slicer.get_conclusion("con1")


def test_write_methods_raise_attribute_error():
    store = FakeStore()
    slicer = CorpusSlicer(store, _make_cut())
    with pytest.raises(AttributeError, match="does not proxy"):
        slicer.put_artifact(None)


def test_list_claim_ids_filters():
    from datetime import date

    store = FakeStore()
    store.claims["early"] = Claim(
        id="early",
        text="early",
        speaker=Speaker(name="a"),
        episode_id="ep1",
        episode_date=date(2025, 1, 1),
    )
    store.claims["late"] = Claim(
        id="late",
        text="late",
        speaker=Speaker(name="b"),
        episode_id="ep2",
        episode_date=date(2025, 9, 1),
    )
    slicer = CorpusSlicer(store, _make_cut())
    ids = slicer.list_claim_ids()
    assert "early" in ids
    assert "late" not in ids


def test_list_conclusions_filters():
    store = FakeStore()
    store.conclusions["old"] = Conclusion(
        id="old", text="old", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    store.conclusions["new"] = Conclusion(
        id="new", text="new", created_at=datetime(2025, 8, 1, tzinfo=timezone.utc)
    )
    slicer = CorpusSlicer(store, _make_cut())
    concs = slicer.list_conclusions()
    ids = [c.id for c in concs]
    assert "old" in ids
    assert "new" not in ids
