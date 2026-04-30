"""Hybrid FTS retrieval over in-memory store."""

from __future__ import annotations

from datetime import date

from noosphere.models import Claim, ClaimOrigin, Speaker
from noosphere.retrieval import HybridRetriever
from noosphere.store import Store


def test_hybrid_retriever_rebuild_and_bm25() -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    c1 = Claim(
        id="r1",
        text="This claim discusses political liberalism and public reason in democratic theory at length here.",
        speaker=Speaker(name="A"),
        episode_id="e",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )
    c2 = Claim(
        id="r2",
        text="Another claim about liberalism and justice as fairness in political philosophy continues.",
        speaker=Speaker(name="B"),
        episode_id="e",
        episode_date=date(2024, 1, 2),
        claim_origin=ClaimOrigin.LITERATURE,
    )
    st.put_claim(c1)
    st.put_claim(c2)
    r = HybridRetriever()
    n = r.rebuild(st)
    assert n == 2
    hits = r.search(st, query_text="liberalism political philosophy", query_embedding=None, top_k=5)
    ids = {h.claim_id for h in hits}
    assert "r1" in ids or "r2" in ids


def test_hybrid_retriever_skips_fts_for_non_sqlite(monkeypatch) -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    monkeypatch.setattr(st.engine.dialect, "name", "postgresql")

    r = HybridRetriever()

    assert r.rebuild(st) == 0
    assert r.bm25_hits(st, "liberalism") == []
