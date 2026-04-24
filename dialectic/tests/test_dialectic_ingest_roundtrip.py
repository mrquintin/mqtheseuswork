"""Round-trip Dialectic session JSONL through Noosphere ingest."""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from sqlmodel import select

from dialectic.session_writer import SessionJSONLWriter, _decode_b64_f32
from noosphere.ingest_artifacts import ingest_dialectic_session_jsonl
from noosphere.models import Claim
from noosphere.store import Store, StoredClaim


def test_session_jsonl_roundtrip_via_ingest(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    b64 = base64.b64encode(vec.tobytes()).decode("ascii")
    w = SessionJSONLWriter(path)
    w.append_claim(
        speaker="Alice",
        text="We should treat model drift as a first-class risk.",
        embedding=vec.tolist(),
        contradiction_pair_ids=["pair-a"],
        topic_cluster_id="topic_1",
    )
    store = Store.from_database_url("sqlite:///:memory:")
    art, n = ingest_dialectic_session_jsonl(
        path,
        store,
        episode_id="ep_test",
        episode_date=date(2026, 4, 14),
    )
    assert n == 1
    assert art.title == "session"
    with store.session() as s:
        rows = list(s.exec(select(StoredClaim)).all())
    assert len(rows) == 1
    cl = Claim.model_validate_json(rows[0].payload_json)
    assert "drift" in cl.text.lower()
    assert cl.speaker.name == "Alice"
    assert cl.embedding is not None
    assert pytest.approx(cl.embedding[0], rel=1e-5) == 0.1
    assert cl.evidence_pointers == ["pair-a"]
    tid = store.get_topic_id_for_claim(cl.id)
    assert tid == "topic_1"
    assert _decode_b64_f32(b64) == pytest.approx(vec.tolist(), rel=1e-5)
