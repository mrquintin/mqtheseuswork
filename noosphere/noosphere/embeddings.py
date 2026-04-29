"""
Injectable embedding clients with on-disk cache keyed by (model, text hash).
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback is for broken local wheels.
    np = None  # type: ignore[assignment]


def _text_hash(model: str, text: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


@runtime_checkable
class EmbeddingClient(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def model_name(self) -> str: ...


class DiskEmbeddingCache:
    """On-disk cache: one JSON file per (model, exact text)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, model: str, text: str) -> Path:
        return self.root / f"{_text_hash(model, text)}.json"

    def get(self, model: str, text: str) -> list[float] | None:
        p = self.path(model, text)
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        vec = data.get("embedding")
        if isinstance(vec, list):
            return [float(x) for x in vec]
        return None

    def put(self, model: str, text: str, vector: list[float]) -> None:
        p = self.path(model, text)
        p.write_text(
            json.dumps({"model": model, "embedding": vector}, separators=(",", ":")),
            encoding="utf-8",
        )


class SentenceTransformersClient:
    """Local sentence-transformers backend."""

    def __init__(
        self,
        model_name: str,
        *,
        device: str | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name
        self._cache = DiskEmbeddingCache(cache_dir) if cache_dir is not None else None
        kwargs: dict[str, Any] = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(model_name, **kwargs)

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            if self._cache is not None:
                hit = self._cache.get(self._model_name, t)
                if hit is not None:
                    out.append(hit)
                    continue
            vec_np = self._model.encode(
                [t],
                convert_to_numpy=np is not None,
                show_progress_bar=False,
            )
            if np is not None:
                vec = np.asarray(vec_np[0], dtype=float).tolist()
            else:
                vec = [float(x) for x in vec_np[0]]
            if self._cache is not None:
                self._cache.put(self._model_name, t, vec)
            out.append(vec)
        return out


class MockEmbeddingClient:
    """Deterministic fake vectors for tests (no model download)."""

    def __init__(self, model_name: str = "mock-embed", dim: int = 8) -> None:
        self._model_name = model_name
        self._dim = dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
            if np is not None:
                rng = np.random.default_rng(seed)
                out.append(rng.standard_normal(self._dim).astype(float).tolist())
            else:
                rng = random.Random(seed)
                out.append([rng.gauss(0.0, 1.0) for _ in range(self._dim)])
        return out


def default_cache_dir() -> Path:
    from noosphere.config import get_settings

    d = get_settings().data_dir / "embedding_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sentence_transformers_client_from_settings() -> SentenceTransformersClient:
    from noosphere.config import get_settings

    s = get_settings()
    return SentenceTransformersClient(
        s.embedding_model_name,
        device=s.embedding_device or None,
        cache_dir=default_cache_dir(),
    )
