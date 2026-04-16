"""Deterministic content-addressed IDs."""

from __future__ import annotations

from pathlib import Path

from noosphere.ids import (
    artifact_id_from_bytes,
    artifact_id_from_file,
    chunk_id,
    claim_id,
    normalize_claim_text,
)


def test_artifact_id_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "doc.txt"
    p.write_bytes(b"same-bytes")
    a1 = artifact_id_from_file(p)
    a2 = artifact_id_from_bytes(b"same-bytes")
    assert a1 == a2
    p.write_bytes(b"same-bytes")
    assert artifact_id_from_file(p) == a1


def test_chunk_id_stable() -> None:
    aid = artifact_id_from_bytes(b"x")
    c1 = chunk_id(aid, 0, 10)
    c2 = chunk_id(aid, 0, 10)
    assert c1 == c2
    assert chunk_id(aid, 0, 11) != c1


def test_claim_id_stable() -> None:
    cid = chunk_id("art_1", 5, 20)
    text = normalize_claim_text("  Hello   world  ")
    k1 = claim_id(cid, text)
    k2 = claim_id(cid, normalize_claim_text("Hello world"))
    assert k1 == k2
