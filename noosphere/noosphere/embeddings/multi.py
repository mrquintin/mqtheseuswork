"""Cross-model embedding adapter layer.

Wraps a fixed roster of embedding back-ends behind a uniform protocol so the
Quintin Hypothesis benchmark can be re-run on each in turn. Adapters emit
fixed metadata (``model_name``, ``dim``, ``max_tokens``) and per-call records
(``latency_ms``, ``content_hash``) so persisted vectors are auditable.

Supported back-ends (each pluggable, each opt-in):
    - OpenAI ``text-embedding-3-large`` (env: ``OPENAI_API_KEY``)
    - Voyage AI ``voyage-3`` (env: ``VOYAGE_API_KEY``)
    - Cohere ``embed-english-v3.0`` (env: ``COHERE_API_KEY``)
    - HuggingFace BGE ``BAAI/bge-large-en-v1.5`` (local sentence-transformers)
    - Sentence-Transformers ``all-MiniLM-L6-v2`` (local, no network)
    - ``hash-det`` deterministic fallback used in tests

A registry (:func:`get_adapter`) returns the configured adapter by short
name; missing API keys raise loudly rather than silently falling back.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

import numpy as np


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def content_hash(text: str) -> str:
    """SHA-256 of the input text — short prefix is enough for provenance."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class EmbeddingResult:
    vector: np.ndarray
    model_name: str
    dim: int
    latency_ms: float
    content_hash: str


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Uniform interface over embedding back-ends."""

    @property
    def model_name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    @property
    def max_tokens(self) -> int: ...

    def embed(self, text: str) -> EmbeddingResult: ...


# ---------------------------------------------------------------------------
# Concrete adapters


class _BaseAdapter:
    _model_name: str
    _dim: int
    _max_tokens: int

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _record(self, vector: np.ndarray, text: str, t0: float) -> EmbeddingResult:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        v = np.asarray(vector, dtype=float)
        if v.size != self._dim:
            self._dim = int(v.size)
        return EmbeddingResult(
            vector=v,
            model_name=self._model_name,
            dim=self._dim,
            latency_ms=float(latency_ms),
            content_hash=content_hash(text),
        )


class HashDetAdapter(_BaseAdapter):
    """Deterministic sign-hashing embedder. Network-free CI baseline."""

    def __init__(self, dim: int = 256, salt: str = "qh-cross-v1") -> None:
        self._model_name = f"hash-det:{salt}"
        self._dim = int(dim)
        self._max_tokens = 8192
        self._salt = salt

    def embed(self, text: str) -> EmbeddingResult:
        t0 = time.perf_counter()
        v = np.zeros(self._dim, dtype=float)
        for tok in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(
                f"{self._salt}:{tok}".encode("utf-8"), digest_size=8
            ).digest()
            h = int.from_bytes(digest, "big")
            idx = h % self._dim
            sign = 1.0 if (h >> 32) & 1 else -1.0
            v[idx] += sign
        n = float(np.linalg.norm(v))
        if n > 0.0:
            v = v / n
        return self._record(v, text, t0)


class _APIKeyMissing(RuntimeError):
    pass


def _require_env(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        raise _APIKeyMissing(
            f"Adapter requires environment variable {var!r}; refusing to call API."
        )
    return val


class OpenAIAdapter(_BaseAdapter):
    """OpenAI ``text-embedding-3-large`` (3072-dim)."""

    def __init__(self, model: str = "text-embedding-3-large") -> None:
        self._model_name = f"openai:{model}"
        self._raw_model = model
        self._dim = 3072
        self._max_tokens = 8191
        self._client = None  # lazy

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = _require_env("OPENAI_API_KEY")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openai package not installed; pip install openai>=1.0"
            ) from exc
        self._client = OpenAI(api_key=api_key)
        return self._client

    def embed(self, text: str) -> EmbeddingResult:
        t0 = time.perf_counter()
        client = self._get_client()
        resp = client.embeddings.create(input=text, model=self._raw_model)
        vec = np.asarray(resp.data[0].embedding, dtype=float)
        return self._record(vec, text, t0)


class VoyageAdapter(_BaseAdapter):
    """Voyage AI ``voyage-3`` (1024-dim)."""

    def __init__(self, model: str = "voyage-3") -> None:
        self._model_name = f"voyage:{model}"
        self._raw_model = model
        self._dim = 1024
        self._max_tokens = 32000
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = _require_env("VOYAGE_API_KEY")
        try:
            import voyageai  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "voyageai package not installed; pip install voyageai"
            ) from exc
        self._client = voyageai.Client(api_key=api_key)
        return self._client

    def embed(self, text: str) -> EmbeddingResult:
        t0 = time.perf_counter()
        client = self._get_client()
        resp = client.embed([text], model=self._raw_model, input_type="document")
        vec = np.asarray(resp.embeddings[0], dtype=float)
        return self._record(vec, text, t0)


class CohereAdapter(_BaseAdapter):
    """Cohere ``embed-english-v3.0`` (1024-dim)."""

    def __init__(self, model: str = "embed-english-v3.0") -> None:
        self._model_name = f"cohere:{model}"
        self._raw_model = model
        self._dim = 1024
        self._max_tokens = 512
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = _require_env("COHERE_API_KEY")
        try:
            import cohere  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "cohere package not installed; pip install cohere"
            ) from exc
        self._client = cohere.Client(api_key=api_key)
        return self._client

    def embed(self, text: str) -> EmbeddingResult:
        t0 = time.perf_counter()
        client = self._get_client()
        resp = client.embed(
            texts=[text], model=self._raw_model, input_type="search_document"
        )
        vec = np.asarray(resp.embeddings[0], dtype=float)
        return self._record(vec, text, t0)


class SentenceTransformerAdapter(_BaseAdapter):
    """Local sentence-transformers model. Downloads weights on first use."""

    def __init__(
        self,
        model: str,
        *,
        dim: int,
        max_tokens: int,
        device: str | None = None,
    ) -> None:
        self._model_name = f"st:{model}"
        self._raw_model = model
        self._dim = int(dim)
        self._max_tokens = int(max_tokens)
        self._device = device
        self._impl = None

    def _get_impl(self):
        if self._impl is not None:
            return self._impl
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers not installed; pip install sentence-transformers"
            ) from exc
        kwargs: dict[str, Any] = {}
        if self._device:
            kwargs["device"] = self._device
        self._impl = SentenceTransformer(self._raw_model, **kwargs)
        return self._impl

    def embed(self, text: str) -> EmbeddingResult:
        t0 = time.perf_counter()
        impl = self._get_impl()
        vec = impl.encode([text], convert_to_numpy=True, show_progress_bar=False)[0]
        return self._record(vec, text, t0)


# ---------------------------------------------------------------------------
# Registry

_DEFAULT_REGISTRY: dict[str, dict[str, Any]] = {
    "openai-3-large": {"factory": OpenAIAdapter, "kwargs": {}},
    "voyage-3": {"factory": VoyageAdapter, "kwargs": {}},
    "cohere-en-v3": {"factory": CohereAdapter, "kwargs": {}},
    "bge-large": {
        "factory": SentenceTransformerAdapter,
        "kwargs": {"model": "BAAI/bge-large-en-v1.5", "dim": 1024, "max_tokens": 512},
    },
    "minilm-l6": {
        "factory": SentenceTransformerAdapter,
        "kwargs": {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "dim": 384,
            "max_tokens": 256,
        },
    },
    "hash-det": {"factory": HashDetAdapter, "kwargs": {}},
}


def known_adapters() -> list[str]:
    return sorted(_DEFAULT_REGISTRY)


def get_adapter(name: str, *, registry: Mapping[str, Any] | None = None) -> EmbeddingAdapter:
    """Return an instantiated adapter by short name. Raises if unknown."""
    reg = registry if registry is not None else _DEFAULT_REGISTRY
    if name not in reg:
        raise KeyError(
            f"unknown adapter {name!r}; known: {sorted(reg)}"
        )
    spec = reg[name]
    factory = spec["factory"]
    kwargs = spec.get("kwargs", {}) or {}
    return factory(**kwargs)


# ---------------------------------------------------------------------------
# Manifest helpers — embeddings are persisted off-tree under
# ``~/.theseus/data/cross_model/`` to keep large blobs out of git.


def default_vector_root() -> Path:
    """Default off-tree location for embedding vectors. Never inside the repo."""
    root = Path(os.environ.get("THESEUS_CROSS_MODEL_ROOT", str(Path.home() / ".theseus" / "data" / "cross_model")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_manifest(
    root: Path,
    *,
    model_name: str,
    dataset_path: str,
    items_embedded: int,
    items_total: int,
    git_sha: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Persist a manifest describing what was written, alongside the vectors."""
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "model_name": model_name,
        "dataset_path": str(dataset_path),
        "items_embedded": int(items_embedded),
        "items_total": int(items_total),
        "git_sha": git_sha,
    }
    if extra:
        payload.update(dict(extra))
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_name)
    p = root / f"manifest__{safe}.json"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


__all__ = [
    "EmbeddingAdapter",
    "EmbeddingResult",
    "HashDetAdapter",
    "OpenAIAdapter",
    "VoyageAdapter",
    "CohereAdapter",
    "SentenceTransformerAdapter",
    "content_hash",
    "default_vector_root",
    "get_adapter",
    "known_adapters",
    "write_manifest",
]
