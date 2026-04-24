"""Hybrid retrieval adapter for CurrentEvents.

Returns a heterogeneous set of `Conclusion` hits (preferred) and `Claim`
hits (fallback / complement) scored against a CurrentEvent's embedding.

Stage A — Conclusions:
    Rank the most recent N=500 stored `Conclusion` rows by cosine against
    the query embedding. Conclusions do not carry persisted embeddings,
    so their display text is embedded on-the-fly and cached per-process
    by conclusion id.

Stage B — Claims (via HybridRetriever):
    BM25 candidate fetch restricted to firm-belief origins
    (FOUNDER, VOICE, LITERATURE, SYSTEM). EXTERNAL and ADVERSARIAL are
    excluded — they are not firm beliefs. Candidates are reranked by
    dense cosine against the query embedding and trimmed to the top-k.
    If the FTS index is cold, `HybridRetriever.rebuild` is called once
    and we retry.

Cross-stage dedupe:
    A Claim whose embedding cosine against any kept Conclusion embedding
    is >= 0.85 is dropped (the Conclusion subsumes it).

Callers (prompt 05/06) depend on the module path, function name, and
return-shape being stable. `EventRetrievalHit`'s existing fields do not
move; new optional fields with defaults may be added compatibly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from noosphere.currents.enrich import embed_text  # reuse shared embedding hook
from noosphere.models import ClaimOrigin, CurrentEvent
from noosphere.observability import get_logger
from noosphere.retrieval import HybridRetriever
from noosphere.store import Store

logger = get_logger(__name__)

CONCLUSION_TEXT_CAP = 400
CLAIM_TEXT_CAP = 300
CLAIM_SUBSUMED_BY_CONCLUSION_COSINE = 0.85
QUERY_TEXT_CAP = 1500
RECENT_CONCLUSIONS_LIMIT = 500
BM25_CANDIDATE_LIMIT = 50
FIRM_BELIEF_ORIGINS: set[ClaimOrigin] = {
    ClaimOrigin.FOUNDER,
    ClaimOrigin.VOICE,
    ClaimOrigin.LITERATURE,
    ClaimOrigin.SYSTEM,
}

# Keyed by conclusion id. Per-process cache so we don't re-embed the same
# conclusion text on every event.
_CONCLUSION_EMBED_CACHE: dict[str, list[float]] = {}


@dataclass(frozen=True)
class EventRetrievalHit:
    source_kind: str          # "conclusion" or "claim"
    source_id: str
    text: str                 # truncated display text
    score: float              # comparable within one call
    topic_hint: Optional[str] = None
    origin: Optional[str] = None  # ClaimOrigin value for claims; None for conclusions


def _truncate(text: str, cap: int) -> str:
    if text is None:
        return ""
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "\u2026"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    if a.shape != b.shape or a.size == 0:
        return 0.0
    denom = (float(np.linalg.norm(a)) * float(np.linalg.norm(b))) or 1e-9
    return float(np.dot(a, b) / denom)


def _embed_via_hook(text: str) -> np.ndarray:
    """Embed via the module-level indirection so tests can patch either
    `noosphere.currents.enrich.embed_text` (the source) or
    `noosphere.currents.retrieval_adapter.embed_text` (the re-bound
    name). We resolve through our own module to honor a local patch.
    """
    import noosphere.currents.retrieval_adapter as _self
    return np.asarray(_self.embed_text(text), dtype=np.float32)


def _conclusion_embedding(conc) -> Optional[np.ndarray]:
    """Return cached/computed embedding for a Conclusion.

    Conclusions may carry an `embedding` attribute in the future; honor
    it when present. Otherwise embed the conclusion's `text` on the fly
    and cache by id.
    """
    emb = getattr(conc, "embedding", None)
    if emb:
        return np.asarray(emb, dtype=np.float32)
    cid = getattr(conc, "id", None) or ""
    cached = _CONCLUSION_EMBED_CACHE.get(cid)
    if cached is not None:
        return np.asarray(cached, dtype=np.float32)
    body = (getattr(conc, "text", "") or "").strip()
    if not body:
        return None
    vec = _embed_via_hook(body)
    _CONCLUSION_EMBED_CACHE[cid] = vec.tolist()
    return vec


def _retrieve_conclusions(
    store: Store,
    query_vec: np.ndarray,
    *,
    k: int,
    min_score: float,
) -> list[EventRetrievalHit]:
    try:
        conclusions = store.list_conclusions() or []
    except Exception as e:
        logger.warning("retrieval_conclusions_list_failed", error=str(e))
        return []

    if not conclusions:
        return []

    # Prefer the most recent N by created_at if available; otherwise keep
    # insertion order and cap.
    try:
        conclusions = sorted(
            conclusions,
            key=lambda c: getattr(c, "created_at", None) or 0,
            reverse=True,
        )
    except Exception:
        pass
    conclusions = conclusions[:RECENT_CONCLUSIONS_LIMIT]

    scored: list[tuple[float, object]] = []
    for conc in conclusions:
        cvec = _conclusion_embedding(conc)
        if cvec is None:
            continue
        sim = _cosine(query_vec, cvec)
        if sim >= min_score:
            scored.append((sim, conc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits: list[EventRetrievalHit] = []
    for sim, conc in scored[:k]:
        hits.append(
            EventRetrievalHit(
                source_kind="conclusion",
                source_id=getattr(conc, "id", ""),
                text=_truncate(getattr(conc, "text", "") or "", CONCLUSION_TEXT_CAP),
                score=float(sim),
                topic_hint=None,
                origin=None,
            )
        )
    return hits


def _bm25_with_cold_start(
    retriever: HybridRetriever,
    store: Store,
    query: str,
) -> list[tuple[str, float]]:
    """Run BM25. If empty, attempt a one-time rebuild and retry."""
    bm = retriever.bm25_hits(store, query, limit=BM25_CANDIDATE_LIMIT)
    if bm:
        return bm
    try:
        retriever.rebuild(store, origins=FIRM_BELIEF_ORIGINS)
        logger.info("retrieval_fts_cold_start_rebuilt")
    except Exception as e:
        logger.warning("retrieval_fts_rebuild_failed", error=str(e))
        return []
    return retriever.bm25_hits(store, query, limit=BM25_CANDIDATE_LIMIT)


def _retrieve_claims(
    store: Store,
    query: str,
    query_vec: np.ndarray,
    *,
    k: int,
    min_score: float,
) -> list[EventRetrievalHit]:
    retriever = HybridRetriever()
    try:
        bm = _bm25_with_cold_start(retriever, store, query)
    except Exception as e:
        logger.warning("retrieval_claims_bm25_failed", error=str(e))
        return []
    if not bm:
        return []

    scored: list[tuple[float, object]] = []
    seen_ids: set[str] = set()
    for claim_id, _rank in bm:
        if claim_id in seen_ids:
            continue
        seen_ids.add(claim_id)
        try:
            claim = store.get_claim(claim_id)
        except Exception as e:
            logger.warning("retrieval_claim_fetch_failed", claim_id=claim_id, error=str(e))
            continue
        if claim is None:
            continue
        origin = getattr(claim, "claim_origin", None)
        if origin not in FIRM_BELIEF_ORIGINS:
            continue
        emb = getattr(claim, "embedding", None)
        if not emb:
            continue
        sim = _cosine(query_vec, np.asarray(emb, dtype=np.float32))
        if sim >= min_score:
            scored.append((sim, claim))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits: list[EventRetrievalHit] = []
    for sim, claim in scored[:k]:
        origin = getattr(claim, "claim_origin", None)
        origin_value = getattr(origin, "value", None) if origin is not None else None
        hits.append(
            EventRetrievalHit(
                source_kind="claim",
                source_id=getattr(claim, "id", ""),
                text=_truncate(getattr(claim, "text", "") or "", CLAIM_TEXT_CAP),
                score=float(sim),
                topic_hint=None,
                origin=origin_value,
            )
        )
    return hits


def _claim_embedding(store: Store, claim_id: str) -> Optional[np.ndarray]:
    try:
        claim = store.get_claim(claim_id)
    except Exception:
        return None
    if claim is None:
        return None
    emb = getattr(claim, "embedding", None)
    if not emb:
        return None
    return np.asarray(emb, dtype=np.float32)


def _conclusion_embedding_by_id(store: Store, conclusion_id: str) -> Optional[np.ndarray]:
    cached = _CONCLUSION_EMBED_CACHE.get(conclusion_id)
    if cached is not None:
        return np.asarray(cached, dtype=np.float32)
    try:
        conc = store.get_conclusion(conclusion_id)
    except Exception:
        return None
    if conc is None:
        return None
    return _conclusion_embedding(conc)


def retrieve_for_event(
    store: Store,
    event: CurrentEvent,
    *,
    k_conclusions: int = 6,
    k_claims: int = 10,
    min_score: float = 0.25,
) -> list[EventRetrievalHit]:
    """Hybrid retrieval: conclusions (preferred) + claims (fallback/complement).

    Returns up to ``k_conclusions + k_claims`` hits sorted by score desc.
    Claims are dropped if an embedding-cosine near-match exists in the
    returned conclusions (subsumption dedupe).
    """
    raw = event.raw_text or ""
    topic = event.topic_hint or ""
    query = (raw + (" " + topic if topic else ""))[:QUERY_TEXT_CAP]

    # Embedding provider failures re-raise by design — the scheduler
    # handles backoff. Do not swallow.
    query_vec = _embed_via_hook(query)

    conc_hits: list[EventRetrievalHit] = []
    claim_hits: list[EventRetrievalHit] = []

    try:
        conc_hits = _retrieve_conclusions(
            store, query_vec, k=k_conclusions, min_score=min_score
        )
    except Exception as e:  # defensive — never raise out of retrieval
        logger.warning("retrieval_conclusions_failed", error=str(e))
        conc_hits = []

    try:
        claim_hits = _retrieve_claims(
            store, query, query_vec, k=k_claims, min_score=min_score
        )
    except Exception as e:
        logger.warning("retrieval_claims_failed", error=str(e))
        claim_hits = []

    # Honest-empty signal for observability.
    if not conc_hits and not claim_hits:
        logger.info("retrieval_empty_store", event_id=getattr(event, "id", ""))
        return []

    # Dedupe: drop claims subsumed by any conclusion.
    kept_claims: list[EventRetrievalHit] = []
    conc_vecs: list[np.ndarray] = []
    for c in conc_hits:
        v = _conclusion_embedding_by_id(store, c.source_id)
        if v is not None:
            conc_vecs.append(v)

    for ch in claim_hits:
        subsumed = False
        cemb = _claim_embedding(store, ch.source_id)
        if cemb is not None and conc_vecs:
            for cv in conc_vecs:
                if _cosine(cemb, cv) >= CLAIM_SUBSUMED_BY_CONCLUSION_COSINE:
                    subsumed = True
                    break
        if not subsumed:
            kept_claims.append(ch)

    merged = sorted(conc_hits + kept_claims, key=lambda h: h.score, reverse=True)
    return merged[: k_conclusions + k_claims]
