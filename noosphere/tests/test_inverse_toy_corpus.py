"""Test: hand-built corpus with known supporting and refuting claims."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from noosphere.models import (
    Claim,
    CorpusSelector,
    InverseQuery,
    MethodRef,
    ResolvedEvent,
    Speaker,
    TemporalCut,
)
from noosphere.methods.nli_scorer import NLIInput, NLIScore
from noosphere.inference.inverse import InverseInferenceEngine


CUT = datetime(2025, 12, 1, tzinfo=timezone.utc)
SPEAKER = Speaker(name="alice")


def _make_claim(cid: str, text: str, ep_date: date, emb: list[float]) -> Claim:
    return Claim(
        id=cid,
        text=text,
        speaker=SPEAKER,
        episode_id="ep1",
        episode_date=ep_date,
        embedding=emb,
    )


SUPPORTING_CLAIM = _make_claim(
    "c-support",
    "Tax cuts lead to higher growth",
    date(2025, 3, 1),
    [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)

REFUTING_CLAIM = _make_claim(
    "c-refute",
    "Tax cuts cause revenue shortfalls and recession",
    date(2025, 4, 1),
    [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)

NEUTRAL_CLAIM = _make_claim(
    "c-neutral",
    "Ocean tides are governed by lunar gravity",
    date(2025, 5, 1),
    [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
)


class ToyStore:
    def __init__(self) -> None:
        self.claims = {
            c.id: c
            for c in [SUPPORTING_CLAIM, REFUTING_CLAIM, NEUTRAL_CLAIM]
        }

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


class StubEmbedClient:
    @property
    def model_name(self) -> str:
        return "stub"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]] * len(texts)


def _stub_nli(input_data: NLIInput) -> NLIScore:
    """Return high entailment for the supporting claim, high contradiction
    for the refuting claim, and neutral for everything else."""
    if "higher growth" in input_data.premise:
        return NLIScore(
            entailment=0.9, neutral=0.05, contradiction=0.05,
            verdict="entailment", s1_consistency=0.95,
        )
    if "shortfalls" in input_data.premise:
        return NLIScore(
            entailment=0.05, neutral=0.05, contradiction=0.9,
            verdict="contradiction", s1_consistency=0.1,
        )
    return NLIScore(
        entailment=0.1, neutral=0.8, contradiction=0.1,
        verdict="neutral", s1_consistency=0.9,
    )


EVENT = ResolvedEvent(
    event_id="evt-tax",
    description="Tax cuts boosted GDP growth by 2%",
    resolved_at=datetime(2025, 11, 1, tzinfo=timezone.utc),
    evidence_refs=["ref-1"],
)


def test_supporting_and_refuting_surface_in_top_k():
    engine = InverseInferenceEngine(
        store=ToyStore(),
        embed_client=StubEmbedClient(),
        nli_fn=_stub_nli,
    )
    query = InverseQuery(
        event=EVENT,
        as_of=CUT,
        methods=[MethodRef(name="inverse_inference", version="1.0.0")],
        k=10,
    )

    result = engine.run(query)

    supporting_refs = {i.corpus_ref for i in result.supporting}
    refuted_refs = {i.corpus_ref for i in result.refuted}

    assert "c-support" in supporting_refs, (
        f"Expected supporting claim in result.supporting, got {supporting_refs}"
    )
    assert "c-refute" in refuted_refs, (
        f"Expected refuting claim in result.refuted, got {refuted_refs}"
    )


def test_nli_scores_preserved():
    engine = InverseInferenceEngine(
        store=ToyStore(),
        embed_client=StubEmbedClient(),
        nli_fn=_stub_nli,
    )
    query = InverseQuery(
        event=EVENT,
        as_of=CUT,
        methods=[MethodRef(name="inverse_inference", version="1.0.0")],
        k=10,
    )

    result = engine.run(query)

    support = [i for i in result.supporting if i.corpus_ref == "c-support"][0]
    assert support.entailment_score == pytest.approx(0.9)
    assert support.refutation_score == pytest.approx(0.05)

    refute = [i for i in result.refuted if i.corpus_ref == "c-refute"][0]
    assert refute.entailment_score == pytest.approx(0.05)
    assert refute.refutation_score == pytest.approx(0.9)
