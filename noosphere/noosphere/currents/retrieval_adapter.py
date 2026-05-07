"""Currents retrieval adapter for event-grounded opinion generation."""

from __future__ import annotations

import math
import re
import struct
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Literal

from sqlalchemy import bindparam, inspect, text

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback is for broken local wheels.
    np = None  # type: ignore[assignment]

from noosphere.currents import enrich
from noosphere.models import ClaimOrigin
from noosphere.retrieval import HybridRetriever


@dataclass(frozen=True)
class EventRetrievalHit:
    source_kind: Literal["conclusion", "claim"]
    source_id: str
    text: str
    score: float
    topic_hint: str | None
    origin: str | None
    source_upload_ids: tuple[str, ...] = ()


DEFAULT_TOP_K = 8
RETRIEVAL_OVERSAMPLE = 8
MAX_CONCLUSION_CANDIDATES = 96
MAX_HITS_PER_CORPUS_SOURCE = 2
SUBSUMPTION_COSINE = 0.85
ALLOWED_CLAIM_ORIGINS = ("FOUNDER", "INTERNAL", "VOICE", "LITERATURE")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")

_ALLOWED_CLAIM_ORIGIN_NAMES = set(ALLOWED_CLAIM_ORIGINS)


def _float_vector(value: Any) -> list[float]:
    if isinstance(value, bytes | bytearray | memoryview):
        raw = bytes(value)
        if len(raw) % 4 != 0:
            return []
        return [float(x) for x in struct.unpack(f"<{len(raw) // 4}f", raw)]
    if hasattr(value, "ravel") and np is not None:
        value = value.ravel()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(x) for x in value]


def _allowed_claim_origin_enums() -> set[ClaimOrigin]:
    allowed: set[ClaimOrigin] = set()
    for origin_name in ALLOWED_CLAIM_ORIGINS:
        member = getattr(ClaimOrigin, origin_name, None)
        if member is not None:
            allowed.add(member)
    return allowed


def _origin_name(origin: Any) -> str:
    if isinstance(origin, ClaimOrigin):
        return origin.name
    raw = str(origin)
    if raw in ClaimOrigin.__members__:
        return raw
    for member in ClaimOrigin:
        if raw == member.value:
            return member.name
    return raw.upper()


def _event_embedding(event: Any) -> Any:
    existing = getattr(event, "embedding", None)
    if existing:
        if np is not None:
            return np.frombuffer(bytes(existing), dtype=np.float32).astype(float)
        return _float_vector(existing)
    embedded = enrich.embed_text(getattr(event, "text", ""))
    if np is not None:
        return np.asarray(embedded, dtype=float).ravel()
    return _float_vector(embedded)


def _source_embedding(text: str, existing: Any | None = None) -> Any:
    if existing is not None:
        if np is not None:
            arr = np.asarray(existing, dtype=float).ravel()
            if arr.size:
                return arr
        else:
            vec = _float_vector(existing)
            if vec:
                return vec
    embedded = enrich.embed_text(text)
    if np is not None:
        return np.asarray(embedded, dtype=float).ravel()
    return _float_vector(embedded)


def _cosine(a: Any, b: Any) -> float | None:
    if np is not None:
        left = np.asarray(a, dtype=float).ravel()
        right = np.asarray(b, dtype=float).ravel()
        if left.shape != right.shape:
            return None
        left_norm = float(np.linalg.norm(left))
        right_norm = float(np.linalg.norm(right))
        if left_norm == 0.0 or right_norm == 0.0:
            return None
        return float(np.dot(left, right) / (left_norm * right_norm))
    left = _float_vector(a)
    right = _float_vector(b)
    if len(left) != len(right) or not left:
        return None
    left_norm = sum(x * x for x in left) ** 0.5
    right_norm = sum(x * x for x in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return sum(x * y for x, y in zip(left, right)) / (left_norm * right_norm)


def _score(cosine: float) -> float:
    return max(0.0, min(1.0, float(cosine)))


def _rank_hits(hits: list[EventRetrievalHit]) -> list[EventRetrievalHit]:
    return sorted(
        hits,
        key=lambda hit: (
            -hit.score,
            0 if hit.source_kind == "conclusion" else 1,
            hit.source_id,
        ),
    )


def _candidate_limit(top_k: int) -> int:
    return min(max(top_k * RETRIEVAL_OVERSAMPLE, top_k), MAX_CONCLUSION_CANDIDATES)


def _conclusion_source_upload_map(
    store: Any,
    conclusion_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    """Return Conclusion -> Upload provenance from the Prisma bridge if present."""

    ids = sorted({conclusion_id for conclusion_id in conclusion_ids if conclusion_id})
    if not ids:
        return {}

    engine = getattr(store, "engine", None)
    if engine is None:
        return {}
    try:
        if not inspect(engine).has_table("ConclusionSource"):
            return {}
        stmt = text(
            'SELECT "conclusionId", "uploadId" '
            'FROM "ConclusionSource" '
            'WHERE "conclusionId" IN :ids '
            'ORDER BY "conclusionId", "createdAt", "uploadId"'
        ).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"ids": ids}).fetchall()
    except Exception:
        return {}

    out: dict[str, list[str]] = {}
    for row in rows:
        data = row._mapping if hasattr(row, "_mapping") else row
        conclusion_id = str(data["conclusionId"])
        upload_id = str(data["uploadId"])
        out.setdefault(conclusion_id, []).append(upload_id)
    return {
        conclusion_id: tuple(dict.fromkeys(upload_ids))
        for conclusion_id, upload_ids in out.items()
    }


def _with_conclusion_uploads(
    store: Any,
    pairs: list[tuple[EventRetrievalHit, Any | None]],
) -> list[tuple[EventRetrievalHit, Any | None]]:
    upload_map = _conclusion_source_upload_map(
        store,
        [hit.source_id for hit, _ in pairs if hit.source_kind == "conclusion"],
    )
    if not upload_map:
        return pairs
    return [
        (
            (
                replace(hit, source_upload_ids=upload_map.get(hit.source_id, ()))
                if hit.source_kind == "conclusion"
                else hit
            ),
            embedding,
        )
        for hit, embedding in pairs
    ]


def corpus_source_key(hit: Any) -> str:
    upload_ids = tuple(getattr(hit, "source_upload_ids", ()) or ())
    if upload_ids:
        return f"upload:{upload_ids[0]}"
    return f"{getattr(hit, 'source_kind', 'source')}:{getattr(hit, 'source_id', '')}"


def distinct_corpus_source_count(hits: list[Any]) -> int:
    return len({corpus_source_key(hit) for hit in hits})


def _diversify_hits(
    hits: list[EventRetrievalHit],
    *,
    top_k: int,
    max_per_source: int = MAX_HITS_PER_CORPUS_SOURCE,
) -> list[EventRetrievalHit]:
    if len(hits) <= top_k:
        return _rank_hits(hits)[:top_k]

    selected: list[EventRetrievalHit] = []
    deferred: list[EventRetrievalHit] = []
    counts: Counter[str] = Counter()
    for hit in _rank_hits(hits):
        key = corpus_source_key(hit)
        if counts[key] < max_per_source:
            selected.append(hit)
            counts[key] += 1
        else:
            deferred.append(hit)
        if len(selected) >= top_k:
            return selected

    for hit in deferred:
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected[:top_k]


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _bm25_conclusion_hits(
    conclusions: list[Any],
    event: Any,
    *,
    limit: int,
) -> list[tuple[EventRetrievalHit, None]]:
    query_terms = _tokens(getattr(event, "text", ""))
    if not query_terms:
        return []

    docs: list[tuple[Any, list[str]]] = [
        (conclusion, _tokens(getattr(conclusion, "text", "")))
        for conclusion in conclusions
        if getattr(conclusion, "text", "").strip()
    ]
    if not docs:
        return []

    doc_freq: Counter[str] = Counter()
    for _, terms in docs:
        doc_freq.update(set(terms))

    avg_doc_len = sum(len(terms) for _, terms in docs) / max(1, len(docs))
    k1 = 1.5
    b = 0.75
    raw_scores: list[tuple[Any, float]] = []
    for conclusion, terms in docs:
        counts = Counter(terms)
        doc_len = max(1, len(terms))
        score = 0.0
        for term in set(query_terms):
            freq = counts.get(term, 0)
            if freq <= 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / max(1.0, avg_doc_len))
            score += idf * (freq * (k1 + 1)) / denom
        if score > 0.0:
            raw_scores.append((conclusion, score))

    if not raw_scores:
        return []

    max_score = max(score for _, score in raw_scores)
    topic_hint = getattr(event, "topic_hint", None)
    hits = [
        (
            EventRetrievalHit(
                source_kind="conclusion",
                source_id=str(conclusion.id),
                text=conclusion.text,
                score=max(0.0, min(1.0, score / max_score)),
                topic_hint=topic_hint,
                origin=None,
            ),
            None,
        )
        for conclusion, score in raw_scores
    ]
    hits.sort(
        key=lambda item: (
            -item[0].score,
            0 if item[0].source_kind == "conclusion" else 1,
            item[0].source_id,
        )
    )
    return hits[:limit]


def _conclusion_hits(
    store: Any,
    event: Any,
    query_embedding: Any | None,
    *,
    limit: int,
) -> list[tuple[EventRetrievalHit, Any | None]]:
    conclusions = list(store.list_conclusions())
    if query_embedding is None:
        return _with_conclusion_uploads(
            store,
            _bm25_conclusion_hits(conclusions, event, limit=limit),
        )

    scored: list[tuple[EventRetrievalHit, Any | None]] = []
    topic_hint = getattr(event, "topic_hint", None)
    for conclusion in conclusions:
        try:
            embedding = _source_embedding(conclusion.text)
        except Exception:
            continue
        cosine = _cosine(query_embedding, embedding)
        if cosine is None:
            continue
        scored.append(
            (
                EventRetrievalHit(
                    source_kind="conclusion",
                    source_id=str(conclusion.id),
                    text=conclusion.text,
                    score=_score(cosine),
                    topic_hint=topic_hint,
                    origin=None,
                ),
                embedding,
            )
        )
    scored.sort(
        key=lambda item: (
            -item[0].score,
            0 if item[0].source_kind == "conclusion" else 1,
            item[0].source_id,
        )
    )
    if not scored:
        return _with_conclusion_uploads(
            store,
            _bm25_conclusion_hits(conclusions, event, limit=limit),
        )
    return _with_conclusion_uploads(store, scored[:limit])


def _is_subsumed_by_conclusion(
    claim_embedding: Any,
    conclusion_embeddings: list[Any],
) -> bool:
    for conclusion_embedding in conclusion_embeddings:
        cosine = _cosine(claim_embedding, conclusion_embedding)
        if cosine is not None and cosine >= SUBSUMPTION_COSINE:
            return True
    return False


def retrieve_for_event(
    store: Any,
    event: Any,
    top_k: int = DEFAULT_TOP_K,
) -> list[EventRetrievalHit]:
    """
    Stage A: top-N Conclusions matching the event text.
    Stage B: top-M Claims via HybridRetriever, filtered by origin and by
    subsumption under Stage-A Conclusions.
    """
    if top_k <= 0:
        return []

    try:
        query_embedding = _event_embedding(event)
    except Exception:
        query_embedding = None
    conclusion_pairs = _conclusion_hits(
        store,
        event,
        query_embedding,
        limit=_candidate_limit(top_k),
    )
    selected_conclusions = _diversify_hits(
        [hit for hit, _ in conclusion_pairs],
        top_k=top_k,
    )
    hits = selected_conclusions
    if len(hits) >= top_k:
        return hits[:top_k]
    if query_embedding is None:
        return hits[:top_k]

    selected_conclusion_keys = {
        (hit.source_kind, hit.source_id) for hit in selected_conclusions
    }
    conclusion_embeddings = [
        embedding
        for hit, embedding in conclusion_pairs
        if (hit.source_kind, hit.source_id) in selected_conclusion_keys
        and embedding is not None
    ]
    seen = {(hit.source_kind, hit.source_id) for hit in hits}
    allowed_origins = _allowed_claim_origin_enums()

    retriever = HybridRetriever()
    retriever.rebuild(store, origins=allowed_origins)
    claim_candidates = retriever.search(
        store,
        query_text=getattr(event, "text", ""),
        query_embedding=query_embedding,
        top_k=max(top_k * 3, 20),
        origins=allowed_origins,
    )

    topic_hint = getattr(event, "topic_hint", None)
    for candidate in claim_candidates:
        if len(hits) >= top_k:
            break
        claim = store.get_claim(candidate.claim_id)
        if claim is None:
            continue

        origin_name = _origin_name(claim.claim_origin)
        if origin_name not in _ALLOWED_CLAIM_ORIGIN_NAMES:
            continue

        key = ("claim", str(claim.id))
        if key in seen:
            continue

        claim_embedding = _source_embedding(claim.text, claim.embedding)
        if _is_subsumed_by_conclusion(claim_embedding, conclusion_embeddings):
            continue

        cosine = _cosine(query_embedding, claim_embedding)
        if cosine is None:
            continue

        hits.append(
            EventRetrievalHit(
                source_kind="claim",
                source_id=str(claim.id),
                text=claim.text,
                score=_score(cosine),
                topic_hint=topic_hint,
                origin=origin_name,
            )
        )
        seen.add(key)

    return _diversify_hits(hits, top_k=top_k)


def retrieve_conclusions_for_event(
    store: Any,
    event: Any,
    top_k: int = 12,
) -> list[EventRetrievalHit]:
    """Return conclusion-only event hits, using dense scoring or BM25 fallback."""
    if top_k <= 0:
        return []
    try:
        query_embedding = _event_embedding(event)
    except Exception:
        query_embedding = None
    conclusion_pairs = _conclusion_hits(
        store,
        event,
        query_embedding,
        limit=_candidate_limit(top_k),
    )
    return _diversify_hits([hit for hit, _ in conclusion_pairs], top_k=top_k)
