"""Test: corpus deliberately omits an entity named in the event."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from noosphere.models import (
    BlindspotReport,
    Claim,
    CorpusSelector,
    ResolvedEvent,
    ResearchSuggestion,
    Speaker,
    TemporalCut,
)
from noosphere.evaluation.slicer import CorpusSlicer
from noosphere.inference.blindspot import compute_blindspot, suggest_research


CUT = datetime(2025, 12, 1, tzinfo=timezone.utc)
SPEAKER = Speaker(name="researcher")


CLAIM_A = Claim(
    id="c-a",
    text="Machine learning models require large datasets",
    speaker=SPEAKER,
    episode_id="ep1",
    episode_date=date(2025, 2, 1),
    embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)

CLAIM_B = Claim(
    id="c-b",
    text="Data governance frameworks are essential for compliance",
    speaker=SPEAKER,
    episode_id="ep1",
    episode_date=date(2025, 3, 1),
    embedding=[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)


class BlindspotStore:
    def __init__(self) -> None:
        self.claims = {c.id: c for c in [CLAIM_A, CLAIM_B]}

    def get_claim(self, claim_id: str):
        return self.claims.get(claim_id)

    def list_claim_ids(self):
        return list(self.claims.keys())

    def get_artifact(self, artifact_id: str):
        return None

    def get_chunk(self, chunk_id: str):
        return None

    def get_conclusion(self, conclusion_id: str):
        return None

    def get_embedding_vector(self, embedding_id: str):
        return None

    def list_conclusions(self):
        return []

    def list_chunks_for_artifact(self, artifact_id: str):
        return []

    def list_drift_events(self, *, limit=500):
        return []

    def get_temporal_cut(self, cut_id: str):
        return None

    def list_outcomes_for_cut(self, cut_id: str):
        return []

    def get_drift_event(self, drift_id: str):
        return None


class StubEmbed:
    @property
    def model_name(self) -> str:
        return "stub"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]] * len(texts)


EVENT_WITH_MISSING_ENTITY = ResolvedEvent(
    event_id="evt-quantum",
    description=(
        "Anthropic released a new Quantum Computing framework that "
        "disrupted existing Bayesian Inference pipelines"
    ),
    resolved_at=datetime(2025, 11, 1, tzinfo=timezone.utc),
    evidence_refs=["ref-1"],
)


def test_missing_entities_detected():
    store = BlindspotStore()
    cut = TemporalCut(
        cut_id="bs-test",
        as_of=CUT,
        corpus_slice=CorpusSelector(as_of=CUT),
        embargoed=CorpusSelector(as_of=CUT),
        embedding_version_pin="default",
        outcomes=[],
    )
    slicer = CorpusSlicer(store, cut)

    report = compute_blindspot(
        event=EVENT_WITH_MISSING_ENTITY,
        sliced_store=slicer,
        embed_client=StubEmbed(),
    )

    missing_lower = [e.lower() for e in report.missing_entities]
    assert any("anthropic" in e for e in missing_lower), (
        f"Expected 'Anthropic' in missing_entities, got {report.missing_entities}"
    )
    assert any("quantum computing" in e for e in missing_lower), (
        f"Expected 'Quantum Computing' in missing_entities, got {report.missing_entities}"
    )
    assert any("bayesian inference" in e for e in missing_lower), (
        f"Expected 'Bayesian Inference' in missing_entities, got {report.missing_entities}"
    )


def test_suggest_research_from_blindspot():
    report = BlindspotReport(
        missing_entities=["Anthropic", "Quantum Computing"],
        missing_mechanisms=["quantum decoherence"],
        adjacent_empty_topics=["topic_dim_0042"],
    )

    suggestions = suggest_research(report)

    assert len(suggestions) == 4
    assert all(isinstance(s, ResearchSuggestion) for s in suggestions)

    titles = [s.title for s in suggestions]
    assert any("Anthropic" in t for t in titles)
    assert any("Quantum Computing" in t for t in titles)
    assert any("quantum decoherence" in t for t in titles)
    assert any("topic_dim_0042" in t for t in titles)


def test_empty_corpus_yields_all_entities_missing():
    class EmptyStore:
        def get_claim(self, claim_id):
            return None

        def list_claim_ids(self):
            return []

        def get_artifact(self, a):
            return None

        def get_chunk(self, c):
            return None

        def get_conclusion(self, c):
            return None

        def get_embedding_vector(self, e):
            return None

        def list_conclusions(self):
            return []

        def list_chunks_for_artifact(self, a):
            return []

        def list_drift_events(self, *, limit=500):
            return []

        def get_temporal_cut(self, c):
            return None

        def list_outcomes_for_cut(self, c):
            return []

        def get_drift_event(self, d):
            return None

    store = EmptyStore()
    cut = TemporalCut(
        cut_id="bs-empty",
        as_of=CUT,
        corpus_slice=CorpusSelector(as_of=CUT),
        embargoed=CorpusSelector(as_of=CUT),
        embedding_version_pin="default",
        outcomes=[],
    )
    slicer = CorpusSlicer(store, cut)

    report = compute_blindspot(
        event=EVENT_WITH_MISSING_ENTITY,
        sliced_store=slicer,
        embed_client=StubEmbed(),
    )

    assert len(report.missing_entities) > 0
