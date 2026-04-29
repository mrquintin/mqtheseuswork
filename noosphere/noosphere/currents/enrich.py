"""Embedding enrichment, near-duplicate detection, and topic assignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback is for broken local wheels.
    np = None  # type: ignore[assignment]

from noosphere.embeddings import (
    EmbeddingClient,
    sentence_transformers_client_from_settings,
)
from noosphere.models import CurrentEventStatus

NEAR_DUPLICATE_COSINE = 0.92
TOPIC_ASSIGNMENT_COSINE = 0.35

_EMBED_CLIENT: EmbeddingClient | None = None


@dataclass
class EnrichmentResult:
    event_id: str
    embedding_set: bool
    is_near_duplicate: bool
    topic_id: str | None


def _as_float_vector(value: Any) -> Any:
    if np is not None:
        return np.asarray(value, dtype=float)
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def embed_text(text: str) -> Any:
    """Embed text using the configured local embedding client."""
    global _EMBED_CLIENT
    if _EMBED_CLIENT is None:
        _EMBED_CLIENT = sentence_transformers_client_from_settings()
    return _as_float_vector(_EMBED_CLIENT.encode([text])[0])


def enrich_event(store, event_id: str) -> EnrichmentResult:
    ev = store.get_current_event(event_id)
    if ev is None:
        raise KeyError(f"unknown current event: {event_id}")

    vec = embed_text(ev.text)
    store.set_event_embedding(event_id, vec)
    near = store.find_near_duplicates(
        vec,
        since_days=7,
        cosine_min=NEAR_DUPLICATE_COSINE,
        exclude_id=event_id,
    )
    is_near = bool(near)
    if is_near:
        store.set_event_status(
            event_id,
            CurrentEventStatus.REVOKED,
            note="near_duplicate_of:" + near[0].id,
        )

    topic_id = store.nearest_topic(vec, cosine_min=TOPIC_ASSIGNMENT_COSINE)
    if topic_id:
        store.set_event_topic(event_id, topic_id)

    if not is_near:
        store.set_event_status(event_id, CurrentEventStatus.ENRICHED)

    return EnrichmentResult(event_id, True, is_near, topic_id)
