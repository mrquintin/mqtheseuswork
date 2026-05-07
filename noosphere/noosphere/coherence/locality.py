"""Domain-local ANN index for scoped coherence checks.

The production path uses hnswlib with cosine distance. A dense NumPy cosine
scan is retained only as a safety net for small corpora and test fixtures when
hnswlib is unavailable; it refuses corpora at or above ``DENSE_FALLBACK_LIMIT``
because that would reintroduce the scaling failure this module is meant to fix.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import inspect, text
from sqlmodel import select

from noosphere.config import get_settings
from noosphere.observability import get_logger

try:  # pragma: no cover - exercised where the optional wheel is installed.
    import hnswlib
except ImportError:  # pragma: no cover - local fallback is covered instead.
    hnswlib = None  # type: ignore[assignment]


logger = get_logger(__name__)

DENSE_FALLBACK_LIMIT = 5_000
METADATA_VERSION = 1


class LocalityIndexUnavailable(RuntimeError):
    """Raised when no ANN backend is available for a corpus that is too large."""


@dataclass(frozen=True)
class NeighborResult:
    local_ids: list[str]
    outside_sample_ids: list[str]
    local_distances: dict[str, float] = field(default_factory=dict)
    outside_sample_distances: dict[str, float] = field(default_factory=dict)
    methodology: dict[str, Any] = field(default_factory=dict)
    contradiction_probe: dict[str, Any] = field(default_factory=dict)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_vector(value: Any) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise ValueError("locality embeddings must be non-empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError("locality embeddings must contain only finite values")
    return arr


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape or a.size == 0:
        return 1.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-12 or nb <= 1e-12:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def _matrix_for(ids: list[str], vectors: dict[str, np.ndarray]) -> np.ndarray:
    if not ids:
        return np.empty((0, 0), dtype=np.float32)
    return np.stack([vectors[item] for item in ids], axis=0).astype(np.float32)


class DomainLocalityIndex:
    """Approximate nearest-neighbor index over claim/conclusion embeddings."""

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        store: Any | None = None,
        space: str = "cosine",
        dim: int | None = None,
        m: int = 16,
        ef_construction: int = 200,
        ef_search: int = 128,
        random_seed: int = 17,
        autosave: bool = True,
    ) -> None:
        if space != "cosine":
            raise ValueError("DomainLocalityIndex currently supports cosine space only")
        base = Path(data_dir) if data_dir is not None else get_settings().data_dir
        self.root = base / "coherence"
        self.index_path = self.root / "locality.bin"
        self.metadata_path = self.root / "locality.json"
        self.vectors_path = self.root / "locality_vectors.npz"
        self.store = store
        self.space = space
        self.dim = dim
        self.m = int(m)
        self.ef_construction = int(ef_construction)
        self.ef_search = int(ef_search)
        self.random_seed = int(random_seed)
        self.autosave = bool(autosave)

        self._loaded = False
        self._backend = "hnswlib" if hnswlib is not None else "dense_numpy"
        self._index: Any | None = None
        self._vectors: dict[str, np.ndarray] = {}
        self._active_ids: set[str] = set()
        self._id_to_label: dict[str, int] = {}
        self._label_to_id: list[str] = []

    @property
    def ids(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._active_ids)

    @property
    def backend(self) -> str:
        self._ensure_loaded()
        return self._backend

    def upsert(self, proposition_id: str, embedding: np.ndarray) -> None:
        self._ensure_loaded()
        pid = str(proposition_id)
        vec = _coerce_vector(embedding)
        self._ensure_dim(vec)
        existing = self._vectors.get(pid)
        if existing is not None and np.allclose(existing, vec, rtol=1e-6, atol=1e-7):
            return

        if pid in self._active_ids and self._backend == "hnswlib":
            self._replace_hnsw(pid, vec)
        elif self._backend == "hnswlib":
            self._add_hnsw(pid, vec)

        self._vectors[pid] = vec
        self._active_ids.add(pid)
        if self._backend == "dense_numpy":
            self._guard_dense_limit()
        if self.autosave:
            self.persist()

    def remove(self, proposition_id: str) -> None:
        self._ensure_loaded()
        pid = str(proposition_id)
        if pid not in self._active_ids:
            return
        if self._backend == "hnswlib" and self._index is not None:
            label = self._id_to_label.get(pid)
            if label is not None:
                try:
                    self._index.mark_deleted(label)
                except RuntimeError:
                    logger.warning("locality_mark_deleted_failed", proposition_id=pid)
        self._active_ids.discard(pid)
        self._vectors.pop(pid, None)
        self._id_to_label.pop(pid, None)
        self._rebuild_hnsw_if_available()
        if self.autosave:
            self.persist()

    def neighbors(
        self,
        query_embedding: np.ndarray,
        *,
        k: int = 64,
        radius: float | None = None,
        include_outside_sample: int = 8,
    ) -> NeighborResult:
        self._ensure_loaded()
        query = _coerce_vector(query_embedding)
        self._ensure_dim(query)
        if not self._active_ids:
            return NeighborResult(
                local_ids=[],
                outside_sample_ids=[],
                methodology=self._methodology(
                    k=k,
                    radius=radius,
                    include_outside_sample=include_outside_sample,
                    local_count=0,
                    outside_count=0,
                ),
            )

        requested_k = max(0, int(k))
        if self._backend == "hnswlib" and self._index is not None and requested_k > 0:
            local_ids, distances = self._neighbors_hnsw(query, requested_k, radius)
        else:
            local_ids, distances = self._neighbors_dense(query, requested_k, radius)

        outside_ids = self._outside_sample(
            query,
            exclude=set(local_ids),
            include_outside_sample=max(0, int(include_outside_sample)),
            k=requested_k,
            radius=radius,
        )
        outside_distances = {
            pid: _cosine_distance(query, self._vectors[pid])
            for pid in outside_ids
            if pid in self._vectors
        }
        return NeighborResult(
            local_ids=local_ids,
            outside_sample_ids=outside_ids,
            local_distances=distances,
            outside_sample_distances=outside_distances,
            methodology=self._methodology(
                k=requested_k,
                radius=radius,
                include_outside_sample=include_outside_sample,
                local_count=len(local_ids),
                outside_count=len(outside_ids),
            ),
        )

    def vector_for(self, proposition_id: str) -> np.ndarray | None:
        self._ensure_loaded()
        vec = self._vectors.get(str(proposition_id))
        if vec is None:
            return None
        return vec.astype(float)

    def rebuild_from_store(self, store: Any | None = None) -> int:
        st = store or self.store
        if st is None:
            raise ValueError("rebuild_from_store requires a Store-like object")
        self._reset_loaded_state()
        vectors = self._vectors_from_store(st)
        for pid in sorted(vectors):
            self._insert_without_persist(pid, vectors[pid])
        self._loaded = True
        self.persist()
        return len(self._active_ids)

    def persist(self) -> None:
        self._ensure_loaded()
        self.root.mkdir(parents=True, exist_ok=True)
        self._guard_dense_limit()
        metadata_backend = self._backend
        if self._backend == "hnswlib" and self._index is not None:
            self._index.save_index(str(self.index_path))
            self._persist_vectors(self.vectors_path)
        else:
            metadata_backend = "dense_numpy"
            self._persist_dense_index(self.index_path)
        self.metadata_path.write_text(
            json.dumps(
                self._metadata(backend=metadata_backend),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.metadata_path.is_file() and self.index_path.is_file():
            self._load_from_disk()
            self._loaded = True
            return
        if self.store is not None:
            self.rebuild_from_store(self.store)
            return
        self._reset_loaded_state()
        self._loaded = True

    def _reset_loaded_state(self) -> None:
        self._index = None
        self._vectors = {}
        self._active_ids = set()
        self._id_to_label = {}
        self._label_to_id = []
        self._backend = "hnswlib" if hnswlib is not None else "dense_numpy"

    def _load_from_disk(self) -> None:
        meta = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        ids = [str(item) for item in meta.get("ids", [])]
        self.dim = int(meta["dimension"]) if meta.get("dimension") else self.dim
        params = meta.get("params", {})
        self.m = int(params.get("m", self.m))
        self.ef_construction = int(params.get("ef_construction", self.ef_construction))
        self.ef_search = int(params.get("ef_search", self.ef_search))
        self.random_seed = int(params.get("random_seed", self.random_seed))
        stored_backend = str(meta.get("backend") or "dense_numpy")
        self._active_ids = set(ids)

        if stored_backend == "hnswlib" and hnswlib is not None and self.dim:
            self._backend = "hnswlib"
            self._index = hnswlib.Index(space=self.space, dim=self.dim)
            self._index.load_index(str(self.index_path), max_elements=max(1, len(ids)))
            self._index.set_ef(self.ef_search)
            self._label_to_id = ids
            self._id_to_label = {pid: label for label, pid in enumerate(ids)}
            self._load_vectors_sidecar(ids)
            return

        self._backend = "dense_numpy"
        if stored_backend == "dense_numpy":
            self._load_dense_index(self.index_path)
        else:
            self._load_vectors_sidecar(ids)
        self._guard_dense_limit()

    def _ensure_dim(self, vec: np.ndarray) -> None:
        if self.dim is None:
            self.dim = int(vec.size)
        if int(vec.size) != int(self.dim):
            raise ValueError(
                f"embedding dimension mismatch: got {vec.size}, expected {self.dim}"
            )

    def _guard_dense_limit(self) -> None:
        if self._backend != "dense_numpy":
            return
        if len(self._active_ids) >= DENSE_FALLBACK_LIMIT:
            raise LocalityIndexUnavailable(
                "hnswlib is required for locality corpora with "
                f"{DENSE_FALLBACK_LIMIT} or more vectors"
            )

    def _insert_without_persist(
        self, proposition_id: str, embedding: np.ndarray
    ) -> None:
        pid = str(proposition_id)
        vec = _coerce_vector(embedding)
        self._ensure_dim(vec)
        self._vectors[pid] = vec
        self._active_ids.add(pid)
        if self._backend == "hnswlib":
            self._add_hnsw(pid, vec)
        else:
            self._guard_dense_limit()

    def _ensure_hnsw_initialized(self) -> None:
        if self._backend != "hnswlib":
            return
        if hnswlib is None:
            self._backend = "dense_numpy"
            return
        if self.dim is None:
            return
        if self._index is None:
            self._index = hnswlib.Index(space=self.space, dim=self.dim)
            self._index.init_index(
                max_elements=max(1, len(self._active_ids) + 1),
                ef_construction=self.ef_construction,
                M=self.m,
                random_seed=self.random_seed,
                allow_replace_deleted=True,
            )
            self._index.set_ef(self.ef_search)

    def _add_hnsw(self, proposition_id: str, vec: np.ndarray) -> None:
        self._ensure_hnsw_initialized()
        if self._backend != "hnswlib" or self._index is None:
            self._guard_dense_limit()
            return
        label = len(self._label_to_id)
        self._label_to_id.append(proposition_id)
        self._id_to_label[proposition_id] = label
        if len(self._label_to_id) > self._index.get_max_elements():
            self._index.resize_index(len(self._label_to_id) * 2)
        self._index.add_items(vec.reshape(1, -1), np.asarray([label], dtype=np.int64))

    def _replace_hnsw(self, proposition_id: str, vec: np.ndarray) -> None:
        if self._index is None:
            self._rebuild_hnsw_if_available()
            return
        label = self._id_to_label.get(proposition_id)
        if label is None:
            self._add_hnsw(proposition_id, vec)
            return
        try:
            self._index.mark_deleted(label)
            self._index.add_items(
                vec.reshape(1, -1),
                np.asarray([label], dtype=np.int64),
                replace_deleted=True,
            )
        except RuntimeError:
            self._vectors[proposition_id] = vec
            self._rebuild_hnsw_if_available()

    def _rebuild_hnsw_if_available(self) -> None:
        if hnswlib is None:
            self._backend = "dense_numpy"
            self._index = None
            self._guard_dense_limit()
            return
        active_ids = sorted(self._active_ids)
        vectors = {
            pid: self._vectors[pid]
            for pid in active_ids
            if pid in self._vectors
        }
        self._backend = "hnswlib"
        self._index = None
        self._id_to_label = {}
        self._label_to_id = []
        self._ensure_hnsw_initialized()
        for pid in active_ids:
            vec = vectors.get(pid)
            if vec is not None:
                self._add_hnsw(pid, vec)

    def _neighbors_hnsw(
        self, query: np.ndarray, k: int, radius: float | None
    ) -> tuple[list[str], dict[str, float]]:
        assert self._index is not None
        count = len(self._active_ids)
        query_k = min(count, max(k, self.ef_search if radius is not None else k))
        labels, distances = self._index.knn_query(query.reshape(1, -1), k=query_k)
        pairs: list[tuple[str, float]] = []
        for label, distance in zip(labels[0], distances[0]):
            label_i = int(label)
            if label_i < 0 or label_i >= len(self._label_to_id):
                continue
            pid = self._label_to_id[label_i]
            if pid not in self._active_ids:
                continue
            dist = float(distance)
            if radius is not None and dist > float(radius):
                continue
            pairs.append((pid, dist))
            if radius is None and len(pairs) >= k:
                break
        return [pid for pid, _ in pairs], {pid: dist for pid, dist in pairs}

    def _neighbors_dense(
        self, query: np.ndarray, k: int, radius: float | None
    ) -> tuple[list[str], dict[str, float]]:
        self._guard_dense_limit()
        ids = sorted(pid for pid in self._active_ids if pid in self._vectors)
        if not ids or k <= 0 and radius is None:
            return [], {}
        matrix = _matrix_for(ids, self._vectors).astype(np.float64)
        q = query.astype(np.float64)
        q_norm = np.linalg.norm(q)
        row_norms = np.linalg.norm(matrix, axis=1)
        if q_norm <= 1e-12:
            sims = np.zeros(len(ids), dtype=float)
        else:
            denom = np.maximum(row_norms * q_norm, 1e-12)
            sims = matrix @ q / denom
        distances = 1.0 - sims
        order = np.argsort(distances, kind="mergesort")
        pairs: list[tuple[str, float]] = []
        for idx in order:
            dist = float(distances[idx])
            if radius is not None and dist > float(radius):
                continue
            pairs.append((ids[int(idx)], dist))
            if radius is None and len(pairs) >= k:
                break
        return [pid for pid, _ in pairs], {pid: dist for pid, dist in pairs}

    def _outside_sample(
        self,
        query: np.ndarray,
        *,
        exclude: set[str],
        include_outside_sample: int,
        k: int,
        radius: float | None,
    ) -> list[str]:
        if include_outside_sample <= 0:
            return []
        rest = sorted(self._active_ids - exclude)
        if not rest:
            return []
        seed_blob = hashlib.sha256()
        seed_blob.update(np.asarray(query, dtype=np.float32).tobytes())
        seed_blob.update("\n".join(rest).encode("utf-8"))
        seed_blob.update(
            str((self.random_seed, k, radius, include_outside_sample)).encode()
        )
        rng = random.Random(int(seed_blob.hexdigest()[:16], 16))
        return rng.sample(rest, k=min(include_outside_sample, len(rest)))

    def _vectors_from_store(self, store: Any) -> dict[str, np.ndarray]:
        from noosphere.store import StoredEmbedding

        vectors: dict[str, np.ndarray] = {}
        model_name = store.active_embedding_model_name()
        with store.session() as session:
            rows = session.exec(
                select(StoredEmbedding)
                .where(StoredEmbedding.model_name == model_name)
                .order_by(StoredEmbedding.ref_claim_id, StoredEmbedding.id)
            ).all()
        for row in rows:
            pid = str(row.ref_claim_id or "")
            if not pid:
                continue
            vectors[pid] = np.frombuffer(row.vector, dtype=np.float32).astype(
                np.float32
            )

        for cid in getattr(store, "list_claim_ids", lambda: [])():
            if cid in vectors:
                continue
            claim = store.get_claim(cid)
            if claim is not None and claim.embedding:
                vectors[str(cid)] = _coerce_vector(claim.embedding)

        vectors.update(self._prisma_conclusion_vectors(store, skip=set(vectors)))
        return vectors

    def _prisma_conclusion_vectors(
        self, store: Any, *, skip: set[str]
    ) -> dict[str, np.ndarray]:
        try:
            inspector = inspect(store.engine)
            if not inspector.has_table("Conclusion"):
                return {}
            columns = {column["name"] for column in inspector.get_columns("Conclusion")}
            if not {"id", "embeddingJson"}.issubset(columns):
                return {}
            with store.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        'SELECT id, "embeddingJson" FROM "Conclusion" '
                        'WHERE "embeddingJson" IS NOT NULL'
                    )
                ).fetchall()
        except Exception:
            return {}

        vectors: dict[str, np.ndarray] = {}
        for row in rows:
            data = row._mapping if hasattr(row, "_mapping") else row
            pid = str(data["id"])
            if pid in skip:
                continue
            try:
                raw = json.loads(data["embeddingJson"])
                vectors[pid] = _coerce_vector(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return vectors

    def _persist_vectors(self, path: Path) -> None:
        ids = sorted(pid for pid in self._active_ids if pid in self._vectors)
        matrix = _matrix_for(ids, self._vectors)
        np.savez_compressed(
            path,
            ids=np.asarray(ids, dtype=str),
            vectors=matrix.astype(np.float32),
        )

    def _load_vectors_sidecar(self, ids_hint: list[str]) -> None:
        if not self.vectors_path.is_file():
            return
        with np.load(self.vectors_path, allow_pickle=False) as payload:
            ids = [str(item) for item in payload["ids"].tolist()]
            matrix = np.asarray(payload["vectors"], dtype=np.float32)
        self._vectors = {
            pid: matrix[index].astype(np.float32)
            for index, pid in enumerate(ids)
            if pid in self._active_ids
        }
        if ids_hint and set(ids_hint) != self._active_ids:
            logger.warning(
                "locality_vector_sidecar_id_mismatch",
                metadata_ids=len(ids_hint),
                vector_ids=len(ids),
            )

    def _persist_dense_index(self, path: Path) -> None:
        ids = sorted(pid for pid in self._active_ids if pid in self._vectors)
        matrix = _matrix_for(ids, self._vectors)
        with path.open("wb") as handle:
            np.savez_compressed(
                handle,
                ids=np.asarray(ids, dtype=str),
                vectors=matrix.astype(np.float32),
            )

    def _load_dense_index(self, path: Path) -> None:
        with np.load(path, allow_pickle=False) as payload:
            ids = [str(item) for item in payload["ids"].tolist()]
            matrix = np.asarray(payload["vectors"], dtype=np.float32)
        self._vectors = {pid: matrix[index] for index, pid in enumerate(ids)}
        self._active_ids = set(ids)
        if matrix.size and self.dim is None:
            self.dim = int(matrix.shape[1])

    def _metadata(self, *, backend: str | None = None) -> dict[str, Any]:
        ids = sorted(self._active_ids)
        vector_hash = hashlib.sha256()
        for pid in ids:
            vector_hash.update(pid.encode("utf-8"))
            vec = self._vectors.get(pid)
            if vec is not None:
                vector_hash.update(np.asarray(vec, dtype=np.float32).tobytes())
        return {
            "schema_version": METADATA_VERSION,
            "backend": backend or self._backend,
            "ids": ids,
            "corpus_size": len(ids),
            "dimension": self.dim,
            "space": self.space,
            "params": self._params(),
            "dense_fallback_limit": DENSE_FALLBACK_LIMIT,
            "vectors_sha256": vector_hash.hexdigest(),
            "updated_at": _utc_iso(),
        }

    def _params(self) -> dict[str, int]:
        return {
            "m": self.m,
            "ef_construction": self.ef_construction,
            "ef_search": self.ef_search,
            "random_seed": self.random_seed,
        }

    def _methodology(
        self,
        *,
        k: int,
        radius: float | None,
        include_outside_sample: int,
        local_count: int,
        outside_count: int,
    ) -> dict[str, Any]:
        return {
            "index_backend": self._backend,
            "index_path": str(self.index_path),
            "k": int(k),
            "radius": radius,
            "outside_sample": int(include_outside_sample),
            "local_count": int(local_count),
            "outside_count": int(outside_count),
            "corpus_size": len(self._active_ids),
            "space": self.space,
            "params": self._params(),
            "dense_fallback_limit": DENSE_FALLBACK_LIMIT,
        }
