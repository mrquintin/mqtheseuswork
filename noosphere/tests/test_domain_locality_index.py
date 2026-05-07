from __future__ import annotations

import numpy as np

from noosphere.coherence.locality import DomainLocalityIndex


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def _cap(
    center: np.ndarray,
    *,
    n: int,
    seed: int,
    scale: float = 0.035,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    out: dict[str, np.ndarray] = {}
    for index in range(n):
        vec = _unit(center + rng.normal(0.0, scale, size=center.shape))
        out[f"cap_{seed}_{index}"] = vec.astype(np.float32)
    return out


def _exact_top(vectors: dict[str, np.ndarray], query: np.ndarray, k: int) -> list[str]:
    q = _unit(query.astype(float))
    scored: list[tuple[float, str]] = []
    for pid, vec in vectors.items():
        v = _unit(vec.astype(float))
        scored.append((float(1.0 - np.dot(q, v)), pid))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [pid for _, pid in scored[:k]]


def test_upsert_remove_and_idempotent_upsert(tmp_path) -> None:
    index = DomainLocalityIndex(data_dir=tmp_path)
    index.upsert("a", np.array([1.0, 0.0], dtype=np.float32))
    index.upsert("a", np.array([1.0, 0.0], dtype=np.float32))
    assert index.ids == ["a"]

    index.upsert("a", np.array([0.0, 1.0], dtype=np.float32))
    index.upsert("b", np.array([1.0, 0.0], dtype=np.float32))
    assert index.ids == ["a", "b"]

    index.remove("a")
    result = index.neighbors(
        np.array([0.0, 1.0], dtype=np.float32),
        k=5,
        include_outside_sample=0,
    )
    assert "a" not in result.local_ids
    assert index.ids == ["b"]


def test_neighbors_are_roughly_cosine_nearest_for_spherical_cap(tmp_path) -> None:
    dim = 16
    center = np.zeros(dim, dtype=float)
    center[0] = 1.0
    far_center = np.zeros(dim, dtype=float)
    far_center[1] = 1.0

    vectors = {
        **_cap(center, n=80, seed=1),
        **_cap(far_center, n=80, seed=2),
    }
    query = _unit(center + np.array([0.0, 0.015, *([0.0] * (dim - 2))]))
    index = DomainLocalityIndex(data_dir=tmp_path, autosave=False)
    for pid, vec in vectors.items():
        index.upsert(pid, vec)

    expected = set(_exact_top(vectors, query, 12))
    result = index.neighbors(query, k=12, include_outside_sample=0)

    assert len(result.local_ids) == 12
    assert len(expected.intersection(result.local_ids)) >= 10


def test_outside_sample_is_disjoint_and_respects_size(tmp_path) -> None:
    vectors = _cap(np.array([1.0, 0.0, 0.0, 0.0]), n=30, seed=3)
    index = DomainLocalityIndex(data_dir=tmp_path, autosave=False)
    for pid, vec in vectors.items():
        index.upsert(pid, vec)

    result = index.neighbors(
        np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        k=5,
        include_outside_sample=7,
    )

    assert len(result.outside_sample_ids) == 7
    assert set(result.outside_sample_ids).isdisjoint(result.local_ids)


def test_persistence_roundtrip_returns_same_neighbors(tmp_path) -> None:
    vectors = _cap(np.array([1.0, 0.0, 0.0, 0.0]), n=25, seed=4)
    query = np.array([0.99, 0.01, 0.0, 0.0], dtype=np.float32)

    first = DomainLocalityIndex(data_dir=tmp_path, autosave=False)
    for pid, vec in vectors.items():
        first.upsert(pid, vec)
    first.persist()

    result_a = first.neighbors(query, k=6, include_outside_sample=4)
    second = DomainLocalityIndex(data_dir=tmp_path)
    result_b = second.neighbors(query, k=6, include_outside_sample=4)

    assert result_b.local_ids == result_a.local_ids
    assert result_b.outside_sample_ids == result_a.outside_sample_ids
    assert second.ids == first.ids
