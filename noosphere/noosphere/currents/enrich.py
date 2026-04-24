"""Post-ingestion enrichment for CurrentEvents.

For each OBSERVED event:
  - embed the raw text
  - mark near-duplicates (against the last 24h window) as SUPPRESSED
  - assign a `topic_hint` via nearest-neighbor against Topic embeddings
    (or, as a fallback, against labels drawn from Conclusions embedded
    on-the-fly). Falls back silently to `None` if no topic source exists.

No new Store methods are added here — all auxiliary lookups are guarded with
`hasattr()`, so the degraded path (topic_hint=None) is the intended behavior
in environments that do not yet expose Topic/Conclusion listers.

The embedding helper is indirected through the module-level `embed_text`
callable so tests can monkeypatch it without touching the real model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np

from noosphere.models import CurrentEvent, CurrentEventStatus
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)

NEAR_DUPLICATE_COSINE = 0.92
TOPIC_ASSIGNMENT_COSINE = 0.35


def _default_embed_text(text: str) -> list[float]:
    """Lazy default — imports and constructs the sentence-transformers
    client only on first real call. Tests monkeypatch `embed_text` and
    never exercise this path.
    """
    from noosphere.embeddings import sentence_transformers_client_from_settings

    client = sentence_transformers_client_from_settings()
    return client.encode([text])[0]


# Module-level indirection: tests override this.
embed_text: Callable[[str], list[float]] = _default_embed_text


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


@dataclass
class EnrichmentResult:
    event_id: str
    was_duplicate_of: Optional[str]
    topic_hint: Optional[str]


def enrich_event(
    store: Store,
    event: CurrentEvent,
    *,
    now: Optional[datetime] = None,
) -> EnrichmentResult:
    """Embed, check near-duplicates in last 24h, assign topic hint, persist."""
    now = now or datetime.now(timezone.utc)
    if event.embedding is not None:
        logger.info("enrich_skip_already_enriched event_id=%s", event.id)
        return EnrichmentResult(event.id, None, event.topic_hint)

    # NOTE: call via module attribute so monkeypatching works.
    import noosphere.currents.enrich as _self  # self-import for patchability
    vec = np.asarray(_self.embed_text(event.raw_text), dtype=np.float32)

    lookback = now - timedelta(hours=24)
    recent_ids = store.list_current_event_ids(since=lookback, limit=500)
    for other_id in recent_ids:
        if other_id == event.id:
            continue
        other = store.get_current_event(other_id)
        if other is None or other.embedding is None:
            continue
        sim = _cosine(vec, np.asarray(other.embedding, dtype=np.float32))
        if sim >= NEAR_DUPLICATE_COSINE:
            store.update_current_event_status(
                event.id,
                CurrentEventStatus.SUPPRESSED,
                reason=f"near_duplicate_of:{other_id}",
            )
            logger.info(
                "enrich_near_duplicate event_id=%s of=%s sim=%.4f",
                event.id, other_id, sim,
            )
            return EnrichmentResult(event.id, other_id, other.topic_hint)

    topic_hint = _assign_topic_hint(store, vec)
    store.set_current_event_topic_and_embedding(
        event.id,
        topic_hint=topic_hint or "",
        embedding=vec.tolist(),
    )
    logger.info("enrich_ok event_id=%s topic=%s", event.id, topic_hint)
    return EnrichmentResult(event.id, None, topic_hint)


def _assign_topic_hint(store: Store, event_vec: np.ndarray) -> Optional[str]:
    topics = _load_topics_with_embeddings(store)
    if not topics:
        return None
    best_label: Optional[str] = None
    best_sim = -1.0
    for label, tvec in topics:
        sim = _cosine(event_vec, tvec)
        if sim > best_sim:
            best_sim = sim
            best_label = label
    return best_label if best_sim >= TOPIC_ASSIGNMENT_COSINE else None


def _load_topics_with_embeddings(store: Store) -> list[tuple[str, np.ndarray]]:
    """Return (topic_label, embedding) pairs.

    Preferred source: `Topic` rows with stored embeddings (via
    `store.list_topics()` if exposed). Fallback: distinct topic labels
    sourced from Conclusions, embedded on-the-fly. Cached on the Store
    instance via a private attribute to avoid re-embedding per event in
    the same ingestion pass.
    """
    cached = getattr(store, "_currents_topic_vectors_cache", None)
    if cached is not None:
        return cached

    out: list[tuple[str, np.ndarray]] = []

    # Preferred: Topic rows with embeddings.
    try:
        if hasattr(store, "list_topics"):
            topics = store.list_topics() or []  # type: ignore[attr-defined]
            for topic in topics:
                label = getattr(topic, "label", "") or getattr(topic, "name", "")
                emb = getattr(topic, "embedding", None)
                if label and emb:
                    out.append((label, np.asarray(emb, dtype=np.float32)))
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("topic_list_failed error=%s", e)

    # Fallback: distinct Conclusion.topic_hint labels (if any).
    if not out:
        try:
            labels: list[str] = []
            if hasattr(store, "list_conclusion_topic_hints"):
                labels = [
                    h for h in (store.list_conclusion_topic_hints() or []) if h  # type: ignore[attr-defined]
                ]
            elif hasattr(store, "list_conclusions"):
                conclusions = store.list_conclusions() or []
                labels = sorted(
                    {
                        (getattr(c, "topic_hint", "") or getattr(c, "topic_id", ""))
                        for c in conclusions
                        if (getattr(c, "topic_hint", "") or getattr(c, "topic_id", ""))
                    }
                )
            import noosphere.currents.enrich as _self  # self-import for patchability
            for label in labels:
                out.append(
                    (label, np.asarray(_self.embed_text(label), dtype=np.float32))
                )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("conclusion_topic_fallback_failed error=%s", e)

    try:
        store._currents_topic_vectors_cache = out  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover — defensive
        pass
    return out
