"""SQLite store CRUD (in-memory)."""

from __future__ import annotations

from datetime import date, timezone

from sqlalchemy import text

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
from noosphere.store import Store, _engine_kwargs_for_url, _psycopg2_compatible_url


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def test_postgres_pooler_url_is_psycopg2_safe_and_connection_capped(
    monkeypatch,
) -> None:
    url = (
        "postgresql://postgres.ref:secret@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
        "?pgbouncer=true&connection_limit=1&pool_timeout=10&sslmode=require"
    )

    safe_url = _psycopg2_compatible_url(url)
    kwargs = _engine_kwargs_for_url(safe_url)

    assert "pgbouncer" not in safe_url
    assert "connection_limit" not in safe_url
    assert "pool_timeout" not in safe_url
    assert "sslmode=require" in safe_url
    assert kwargs["pool_size"] == 1
    assert kwargs["max_overflow"] == 0

    monkeypatch.setenv("NOOSPHERE_DB_POOL_SIZE", "3")
    assert _engine_kwargs_for_url(safe_url)["pool_size"] == 3

    transaction_url = safe_url.replace(":5432/", ":6543/")
    assert _engine_kwargs_for_url(transaction_url)["poolclass"].__name__ == "NullPool"


def test_store_session_rolls_back_read_only_transaction() -> None:
    st = _store()

    with st.session() as s:
        s.exec(text("SELECT 1")).all()
        assert s.in_transaction()

    assert not s.in_transaction()


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
