"""SQLite store CRUD (in-memory)."""

from __future__ import annotations

from datetime import date, timezone

from noosphere.models import (
    Artifact,
    Chunk,
    Claim,
    CoherenceEvaluationPayload,
    CoherenceVerdict,
    Conclusion,
    ConfidenceTier,
    DriftEvent,
    ResearchSuggestion,
    ReviewItem,
    SixLayerScore,
    Speaker,
)
from noosphere.store import Store


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def test_artifact_chunk_claim_crud() -> None:
    st = _store()
    a = Artifact(
        id="art_test",
        uri="u",
        mime_type="text/plain",
        byte_length=1,
        content_sha256="0" * 64,
    )
    st.put_artifact(a)
    loaded = st.get_artifact("art_test")
    assert loaded is not None
    assert loaded.id == a.id and loaded.uri == a.uri
    assert loaded.effective_at is not None
    assert loaded.effective_at_inferred is True
    assert loaded.effective_at.tzinfo == timezone.utc

    ch = Chunk(
        id="chk_test",
        artifact_id=a.id,
        start_offset=0,
        end_offset=1,
        text="x",
    )
    st.put_chunk(ch)
    assert st.get_chunk("chk_test") == ch

    c = Claim(
        text="A proposition.",
        speaker=Speaker(name="Bob"),
        episode_id="e1",
        episode_date=date(2024, 1, 2),
    )
    st.put_claim(c)
    got = st.get_claim(c.id)
    assert got is not None
    assert got.text == c.text
    assert st.list_claim_ids() == [c.id]


def test_embedding_coherence_drift_conclusion_research() -> None:
    st = _store()
    st.put_embedding(
        embedding_id="emb1",
        model_name="m",
        text_sha256="abc",
        vector=[0.0, 1.0, 2.0],
    )
    assert st.get_embedding_vector("emb1") == [0.0, 1.0, 2.0]

    st.put_coherence_pair(
        pair_id="pair1",
        claim_a_id="a",
        claim_b_id="b",
        verdict=CoherenceVerdict.UNRESOLVED,
        scores=SixLayerScore(),
        confidence=0.4,
    )
    row = st.get_coherence_pair("pair1")
    assert row is not None
    assert row[2] == CoherenceVerdict.UNRESOLVED

    d = DriftEvent(
        target_id="p1",
        observed_at=date(2024, 3, 3),
        drift_score=0.05,
    )
    st.put_drift_event(d)
    assert st.get_drift_event(d.id) == d

    con = Conclusion(
        text="Tiered output",
        confidence_tier=ConfidenceTier.FOUNDER,
    )
    st.put_conclusion(con)
    assert st.get_conclusion(con.id) == con

    rs = ResearchSuggestion(title="Next read", summary="Why")
    st.put_research_suggestion(rs)
    assert st.get_research_suggestion(rs.id) == rs

    assert st.list_conclusions() == [con]

    payload = CoherenceEvaluationPayload(
        final_verdict=CoherenceVerdict.COHERE,
        aggregator_verdict=CoherenceVerdict.COHERE,
        prior_scores=SixLayerScore(),
        layer_verdicts={"nli": "cohere"},
    )
    st.put_coherence_evaluation(
        evaluation_key="ek1",
        claim_a_id="a",
        claim_b_id="b",
        content_hash="h1",
        versions_json='{"nli":"v1"}',
        payload=payload,
    )
    gotp = st.get_coherence_evaluation("ek1")
    assert gotp is not None
    assert gotp.final_verdict == CoherenceVerdict.COHERE

    ri = ReviewItem(claim_a_id="a", claim_b_id="b", reason="disagree")
    st.put_review_item(ri)
    open_items = st.list_open_review_items()
    assert len(open_items) == 1
    assert open_items[0].id == ri.id
