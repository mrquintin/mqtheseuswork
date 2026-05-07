"""Automatic source embeddings for conclusions and transcript chunks."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from noosphere.embeddings import EmbeddingClient, sentence_transformers_client_from_settings
from noosphere.models import Conclusion


LOGGER = logging.getLogger(__name__)
_EMBED_CLIENT: EmbeddingClient | None = None


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _model_key(model_name: str) -> str:
    return hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:16]


def _embedding_id(source_kind: str, source_id: str, model_name: str) -> str:
    safe_kind = "".join(ch for ch in source_kind.lower() if ch.isalnum() or ch in {"_", "-"})
    return f"emb_{safe_kind}_{_model_key(model_name)}_{source_id}"


def _get_embedding_client() -> EmbeddingClient:
    global _EMBED_CLIENT
    if _EMBED_CLIENT is None:
        _EMBED_CLIENT = sentence_transformers_client_from_settings()
    return _EMBED_CLIENT


def _auto_embedding_allowed(client: EmbeddingClient | None) -> bool:
    if client is not None:
        return True
    if "PYTEST_CURRENT_TEST" not in os.environ:
        return True
    return os.environ.get("THESEUS_AUTO_EMBED_IN_TESTS", "").strip() == "1"


def _coerce_vector(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _upsert_domain_locality(
    store: Any,
    *,
    source_kind: str,
    source_id: str,
    vector: list[float],
) -> None:
    if source_kind not in {"claim", "conclusion"}:
        return
    try:
        from noosphere.coherence.locality import DomainLocalityIndex

        DomainLocalityIndex(store=store).upsert(source_id, vector)
    except Exception as exc:
        LOGGER.warning(
            "locality_index_upsert_failed source_kind=%s source_id=%s error=%s",
            source_kind,
            source_id,
            exc,
        )


def embed_text_and_store_with_store(
    store: Any,
    *,
    source_kind: str,
    source_id: str,
    text: str,
    force: bool = False,
    client: EmbeddingClient | None = None,
) -> bool:
    """Idempotently embed a source row into the canonical Store embedding table."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False

    model_name = store.active_embedding_model_name()
    text_sha256 = _text_sha256(cleaned)
    if not _auto_embedding_allowed(client):
        return False
    if not force and store.has_current_embedding(
        source_id=source_id,
        model_name=model_name,
        text_sha256=text_sha256,
    ):
        return True

    try:
        embedder = client or _get_embedding_client()
        vector = _coerce_vector(embedder.encode([cleaned])[0])
        store.put_embedding(
            embedding_id=_embedding_id(source_kind, source_id, model_name),
            model_name=model_name,
            text_sha256=text_sha256,
            vector=vector,
            ref_claim_id=source_id,
        )
        if source_kind == "conclusion":
            store.update_prisma_conclusion_embedding_json(source_id, vector)
        _upsert_domain_locality(
            store,
            source_kind=source_kind,
            source_id=source_id,
            vector=vector,
        )
        store.clear_embedding_retry(
            source_kind=source_kind,
            source_id=source_id,
            model_name=model_name,
        )
        return True
    except Exception as exc:
        LOGGER.warning(
            "embedding_source_failed source_kind=%s source_id=%s model=%s error=%s",
            source_kind,
            source_id,
            model_name,
            exc,
        )
        try:
            store.queue_embedding_retry(
                source_kind=source_kind,
                source_id=source_id,
                model_name=model_name,
                text_sha256=text_sha256,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            LOGGER.exception(
                "embedding_retry_queue_failed source_kind=%s source_id=%s",
                source_kind,
                source_id,
            )
        return False


def embed_conclusion_with_store(
    store: Any,
    conclusion: Conclusion,
    *,
    force: bool = False,
    client: EmbeddingClient | None = None,
) -> bool:
    return embed_text_and_store_with_store(
        store,
        source_kind="conclusion",
        source_id=conclusion.id,
        text=conclusion.text,
        force=force,
        client=client,
    )


def embed_chunk_with_store(
    store: Any,
    *,
    chunk_id: str,
    text: str,
    force: bool = False,
    client: EmbeddingClient | None = None,
) -> bool:
    return embed_text_and_store_with_store(
        store,
        source_kind="upload_chunk",
        source_id=chunk_id,
        text=text,
        force=force,
        client=client,
    )


def embed_and_store(conclusion: Conclusion, *, force: bool = False) -> bool:
    """Idempotent. Skips if a current-version embedding already exists unless force=True."""
    from noosphere.config import get_settings
    from noosphere.store import Store

    store = Store.from_database_url(get_settings().database_url)
    return embed_conclusion_with_store(store, conclusion, force=force)
