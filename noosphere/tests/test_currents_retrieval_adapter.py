"""Tests for noosphere.currents.retrieval_adapter (prompt 04).

Embeddings are stubbed through a deterministic hash->vector function so the
tests are stable and don't touch any real model. Both the `enrich` module
name and the `retrieval_adapter`-local re-bound name are patched (the latter
is what the adapter actually calls, due to `from ... import embed_text`).

The store is a fresh in-memory SQLite instance per test. Conclusions are
seeded via `store.put_conclusion`; Claims via `store.put_claim` — both with
known embeddings so the cosine math is predictable.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pytest

from noosphere.currents import retrieval_adapter as adapter_mod
from noosphere.currents.retrieval_adapter import (
    EventRetrievalHit,
    retrieve_for_event,
    CLAIM_TEXT_CAP,
    CONCLUSION_TEXT_CAP,
    _CONCLUSION_EMBED_CACHE,
)
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    Speaker,
)
from noosphere.store import Store


# ── helpers ─────────────────────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _unit(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(arr)) or 1.0
    return (arr / n).tolist()


def _event(
    *,
    raw_text: str = "markets shake on new policy",
    topic_hint: Optional[str] = None,
    embedding: Optional[list[float]] = None,
) -> CurrentEvent:
    now = datetime.now(timezone.utc)
    return CurrentEvent(
        id="evt-under-test",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text=raw_text,
        dedupe_hash="hash-evt",
        embedding=embedding,
        topic_hint=topic_hint,
        status=CurrentEventStatus.OBSERVED,
    )


def _claim(
    *,
    cid: str,
    text: str,
    embedding: list[float],
    origin: ClaimOrigin = ClaimOrigin.FOUNDER,
) -> Claim:
    return Claim(
        id=cid,
        text=text,
        speaker=Speaker(name="Founder A"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        embedding=embedding,
        claim_origin=origin,
    )


def _conclusion(*, cid: str, text: str) -> Conclusion:
    return Conclusion(id=cid, text=text)


def _patch_embed(
    monkeypatch: pytest.MonkeyPatch,
    mapping: dict[str, list[float]],
    *,
    default: Optional[list[float]] = None,
) -> None:
    """Deterministic embed by exact-string match (with optional default)."""
    def _fn(text: str) -> list[float]:
        if text in mapping:
            return list(mapping[text])
        if default is not None:
            return list(default)
        # Fall-back: tiny deterministic per-string vector so we never get
        # a NaN cosine. Orthogonal-ish across distinct inputs.
        h = abs(hash(text)) % (2**31)
        v = np.zeros(4, dtype=np.float32)
        v[h % 4] = 1.0
        return v.tolist()

    # Patch BOTH locations: the source-of-truth in enrich, and the
    # adapter-local binding created by `from ... import embed_text`.
    monkeypatch.setattr("noosphere.currents.enrich.embed_text", _fn)
    monkeypatch.setattr("noosphere.currents.retrieval_adapter.embed_text", _fn)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _CONCLUSION_EMBED_CACHE.clear()
    yield
    _CONCLUSION_EMBED_CACHE.clear()


# ── tests ───────────────────────────────────────────────────────────────────


def test_returns_empty_when_store_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    _patch_embed(monkeypatch, {}, default=_unit([1.0, 0.0, 0.0, 0.0]))
    ev = _event(raw_text="nothing here")
    result = retrieve_for_event(store, ev)
    assert result == []


def test_returns_conclusion_hits_when_topic_aligned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()

    conc_a = _conclusion(cid="conc-A", text="AI compute demand drives chip capex")
    conc_b = _conclusion(cid="conc-B", text="Housing supply constraints persist")
    conc_c = _conclusion(cid="conc-C", text="Energy transition is capital-intensive")
    for c in (conc_a, conc_b, conc_c):
        store.put_conclusion(c)

    query_text = "chipmakers announce record AI spend"
    mapping = {
        query_text: _unit([1.0, 0.0, 0.0, 0.0]),          # aligns with A
        conc_a.text: _unit([0.98, 0.02, 0.0, 0.0]),       # near-parallel
        conc_b.text: _unit([0.0, 1.0, 0.0, 0.0]),         # orthogonal
        conc_c.text: _unit([0.0, 0.0, 1.0, 0.0]),         # orthogonal
    }
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    assert result, "expected at least one hit"
    top = result[0]
    assert top.source_kind == "conclusion"
    assert top.source_id == "conc-A"
    assert top.score >= 0.25


def test_falls_back_to_claims_when_no_conclusion_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()

    # Seed a conclusion that is orthogonal to the event — won't match.
    conc = _conclusion(cid="conc-orth", text="Unrelated conclusion body")
    store.put_conclusion(conc)

    claim_vec = _unit([1.0, 0.0, 0.0, 0.0])
    claim = _claim(
        cid="claim-F",
        text="Founders believe AI adoption accelerates compounding returns.",
        embedding=claim_vec,
        origin=ClaimOrigin.FOUNDER,
    )
    store.put_claim(claim)

    query_text = "AI adoption compounding returns news"
    mapping = {
        query_text: _unit([0.97, 0.05, 0.05, 0.05]),   # aligned with claim
        conc.text: _unit([0.0, 1.0, 0.0, 0.0]),         # orthogonal to query
    }
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    claim_hits = [h for h in result if h.source_kind == "claim"]
    assert claim_hits, f"expected a claim hit, got {result}"
    assert claim_hits[0].source_id == "claim-F"
    assert claim_hits[0].origin == "founder"


def test_excludes_external_and_adversarial_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()

    # Five claims: FOUNDER, VOICE, LITERATURE, EXTERNAL, ADVERSARIAL.
    # All share the same embedding so they'd all rank equally — the
    # adapter must filter the last two by origin.
    vec = _unit([1.0, 0.0, 0.0, 0.0])
    specs = [
        ("claim-F", "Founder belief about tech cycles", ClaimOrigin.FOUNDER),
        ("claim-V", "Voice reiterates capital discipline", ClaimOrigin.VOICE),
        ("claim-L", "Literature on reflexivity cycles", ClaimOrigin.LITERATURE),
        ("claim-E", "External commenter quoted in context", ClaimOrigin.EXTERNAL),
        ("claim-A", "Adversarial rebuttal position", ClaimOrigin.ADVERSARIAL),
    ]
    for cid, text, origin in specs:
        store.put_claim(_claim(cid=cid, text=text, embedding=vec, origin=origin))

    query_text = "tech cycles capital discipline"
    mapping = {query_text: vec}
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    origins = {h.origin for h in result if h.source_kind == "claim"}
    assert "external" not in origins
    assert "adversarial" not in origins
    kept_ids = {h.source_id for h in result if h.source_kind == "claim"}
    assert "claim-E" not in kept_ids
    assert "claim-A" not in kept_ids


def test_dedupes_claims_subsumed_by_conclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()

    vec = _unit([1.0, 0.0, 0.0, 0.0])
    conc = _conclusion(cid="conc-sub", text="AI drives capex cycle")
    store.put_conclusion(conc)

    # Near-identical embedding → should be suppressed by subsumption rule.
    twin_claim = _claim(
        cid="claim-twin",
        text="AI spending drives the capex cycle across semis.",
        embedding=_unit([0.99, 0.01, 0.0, 0.0]),
        origin=ClaimOrigin.FOUNDER,
    )
    store.put_claim(twin_claim)

    query_text = "AI capex cycle story"
    mapping = {
        query_text: vec,
        conc.text: vec,
    }
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    claim_ids = {h.source_id for h in result if h.source_kind == "claim"}
    assert "claim-twin" not in claim_ids, (
        f"subsumed claim should have been dropped, got {claim_ids}"
    )
    # But the Conclusion itself must remain.
    conc_ids = {h.source_id for h in result if h.source_kind == "conclusion"}
    assert "conc-sub" in conc_ids


def test_respects_min_score(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()

    # Seed data whose cosine with the query is low.
    conc = _conclusion(cid="conc-low", text="Unrelated body")
    store.put_conclusion(conc)

    claim = _claim(
        cid="claim-low",
        text="Unrelated claim body",
        embedding=_unit([0.0, 1.0, 0.0, 0.0]),
        origin=ClaimOrigin.FOUNDER,
    )
    store.put_claim(claim)

    query_text = "query that matches nothing semantically"
    # Query orthogonal to both sources — cosine ≈ 0 everywhere.
    mapping = {
        query_text: _unit([1.0, 0.0, 0.0, 0.0]),
        conc.text: _unit([0.0, 0.0, 1.0, 0.0]),
    }
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.8)
    assert result == []


def test_rebuilds_fts_on_cold_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """If HybridRetriever.bm25_hits returns [] on first call, the adapter
    must invoke .rebuild(...) exactly once and retry.
    """
    store = _store()

    # Seed at least one claim so rebuild() has something to write.
    claim = _claim(
        cid="claim-rebuild",
        text="Target claim surfaced only after FTS rebuild.",
        embedding=_unit([1.0, 0.0, 0.0, 0.0]),
        origin=ClaimOrigin.FOUNDER,
    )
    store.put_claim(claim)

    query_text = "target rebuild probe"
    mapping = {
        query_text: _unit([1.0, 0.0, 0.0, 0.0]),
    }
    _patch_embed(monkeypatch, mapping)

    bm_calls: list[int] = []
    rebuild_calls: list[int] = []

    class FakeRetriever:
        def bm25_hits(self, store, query_text, *, limit=25):
            bm_calls.append(1)
            # Empty on first call, populated on retry after rebuild.
            if len(bm_calls) == 1:
                return []
            return [("claim-rebuild", 1.0)]

        def rebuild(self, store, *, origins=None):
            rebuild_calls.append(1)
            return 1

    monkeypatch.setattr(
        "noosphere.currents.retrieval_adapter.HybridRetriever",
        FakeRetriever,
    )

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    assert len(rebuild_calls) == 1, (
        f"rebuild should have been invoked exactly once, got {len(rebuild_calls)}"
    )
    assert len(bm_calls) == 2, f"bm25_hits should have been retried, got {bm_calls}"
    assert any(h.source_id == "claim-rebuild" for h in result)


def test_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both conclusion and claim display text must obey the caps.

    The conclusion and the claim are deliberately embedded on distinct
    axes so the subsumption rule (cos >= 0.85) does NOT fire — both
    kinds must end up in the result for this test to exercise both
    truncation paths.
    """
    store = _store()

    # Claim text contains the query tokens so BM25 finds it after rebuild.
    long_conc_text = "long conclusion body " + ("C" * 650)
    long_claim_text = "long truncation probe payload " + ("K" * 520)

    conc = _conclusion(cid="conc-long", text=long_conc_text)
    store.put_conclusion(conc)

    claim_vec = _unit([0.0, 1.0, 0.0, 0.0])
    claim = _claim(
        cid="claim-long",
        text=long_claim_text,
        embedding=claim_vec,
        origin=ClaimOrigin.FOUNDER,
    )
    store.put_claim(claim)

    query_text = "long truncation probe"
    # Query bisects the two basis vectors so both conclusion and claim
    # score above min_score (cos ≈ 0.707 each).
    query_vec = _unit([1.0, 1.0, 0.0, 0.0])
    mapping = {
        query_text: query_vec,
        long_conc_text: _unit([1.0, 0.0, 0.0, 0.0]),   # orthogonal to claim
    }
    _patch_embed(monkeypatch, mapping)

    ev = _event(raw_text=query_text)
    result = retrieve_for_event(store, ev, min_score=0.25)

    conc_hits = [h for h in result if h.source_kind == "conclusion"]
    claim_hits = [h for h in result if h.source_kind == "claim"]

    assert conc_hits, f"expected conclusion hit, got {result}"
    ch = conc_hits[0]
    assert len(ch.text) <= CONCLUSION_TEXT_CAP
    assert ch.text.endswith("\u2026")

    assert claim_hits, f"expected claim hit, got {result}"
    kh = claim_hits[0]
    assert len(kh.text) <= CLAIM_TEXT_CAP
    assert kh.text.endswith("\u2026")
