"""Test: a post-cut claim must NOT appear in inverse inference results."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from noosphere.models import (
    Claim,
    InverseQuery,
    MethodRef,
    ResolvedEvent,
    Speaker,
)
from noosphere.methods.nli_scorer import NLIInput, NLIScore
from noosphere.inference.inverse import InverseInferenceEngine


CUT = datetime(2025, 6, 1, tzinfo=timezone.utc)
SPEAKER = Speaker(name="analyst")


PRE_CUT_CLAIM = Claim(
    id="c-pre",
    text="Inflation was contained at 2%",
    speaker=SPEAKER,
    episode_id="ep1",
    episode_date=date(2025, 3, 1),
    embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)

POST_CUT_CLAIM = Claim(
    id="c-post",
    text="CANARY: Inflation spiked to 8% in September",
    speaker=SPEAKER,
    episode_id="ep2",
    episode_date=date(2025, 9, 1),
    embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)


class TemporalStore:
    def __init__(self) -> None:
        self.claims = {c.id: c for c in [PRE_CUT_CLAIM, POST_CUT_CLAIM]}

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
        return [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]] * len(texts)


def _stub_nli(input_data: NLIInput) -> NLIScore:
    return NLIScore(
        entailment=0.6, neutral=0.2, contradiction=0.2,
        verdict="entailment", s1_consistency=0.8,
    )


EVENT = ResolvedEvent(
    event_id="evt-inflation",
    description="Inflation remained low throughout 2025",
    resolved_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
    evidence_refs=["ref-1"],
)


def test_post_cut_claim_excluded():
    engine = InverseInferenceEngine(
        store=TemporalStore(),
        embed_client=StubEmbed(),
        nli_fn=_stub_nli,
    )
    query = InverseQuery(
        event=EVENT,
        as_of=CUT,
        methods=[MethodRef(name="inverse_inference", version="1.0.0")],
        k=50,
    )

    result = engine.run(query)

    all_refs = (
        [i.corpus_ref for i in result.supporting]
        + [i.corpus_ref for i in result.refuted]
        + result.irrelevant
    )

    assert "c-post" not in all_refs, (
        "Post-cut claim appeared in inverse results — temporal embargo violated"
    )
    assert "c-pre" in all_refs, (
        "Pre-cut claim should appear in results"
    )
