"""Currents retrieval adapter for event-grounded opinion generation."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Literal

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


DEFAULT_TOP_K = 8
SUBSUMPTION_COSINE = 0.85
ALLOWED_CLAIM_ORIGINS = ("FOUNDER", "INTERNAL", "VOICE", "LITERATURE")

_ALLOWED_CLAIM_ORIGIN_NAMES = set(ALLOWED_CLAIM_ORIGINS)


def _float_vector(value: Any) -> list[float]:
    if isinstance(value, (bytes, bytearray, memoryview)):
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


def _conclusion_hits(
    store: Any,
    event: Any,
    query_embedding: Any,
    *,
    limit: int,
) -> list[tuple[EventRetrievalHit, np.ndarray]]:
    scored: list[tuple[EventRetrievalHit, np.ndarray]] = []
    topic_hint = getattr(event, "topic_hint", None)
    for conclusion in store.list_conclusions():
        embedding = _source_embedding(conclusion.text)
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
    return scored[:limit]


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

    query_embedding = _event_embedding(event)
    conclusion_pairs = _conclusion_hits(
        store,
        event,
        query_embedding,
        limit=top_k,
    )
    hits = [hit for hit, _ in conclusion_pairs]
    if len(hits) >= top_k:
        return _rank_hits(hits)[:top_k]

    conclusion_embeddings = [embedding for _, embedding in conclusion_pairs]
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

    return _rank_hits(hits)[:top_k]
