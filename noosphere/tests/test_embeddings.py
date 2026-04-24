"""Embedding client + on-disk cache."""

from __future__ import annotations

from pathlib import Path

from noosphere.embeddings import DiskEmbeddingCache, MockEmbeddingClient


def test_disk_cache_hit(tmp_path: Path) -> None:
    c = DiskEmbeddingCache(tmp_path / "ec")
    assert c.get("model-a", "hello") is None
    c.put("model-a", "hello", [0.25, 0.5])
    assert c.get("model-a", "hello") == [0.25, 0.5]
    # Different model → miss
    assert c.get("model-b", "hello") is None


def test_mock_embedding_deterministic() -> None:
    m = MockEmbeddingClient(dim=4)
    v1 = m.encode(["alpha"])[0]
    v2 = m.encode(["alpha"])[0]
    assert v1 == v2
    assert len(v1) == 4
