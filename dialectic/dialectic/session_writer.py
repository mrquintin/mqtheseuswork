"""Append-only JSONL session log for Noosphere dialectic ingest."""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np


def _b64_f32(vec: list[float] | np.ndarray) -> str:
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _decode_b64_f32(s: str) -> list[float]:
    raw = base64.b64decode(s.encode("ascii"))
    return np.frombuffer(raw, dtype=np.float32).astype(float).tolist()


@dataclass
class FinalizedClaimLine:
    """One JSONL record (native Noosphere dialectic ingest)."""

    timestamp: str  # ISO-8601 UTC
    speaker: str
    text: str
    embedding_b64: str
    contradiction_pair_ids: list[str] = field(default_factory=list)
    topic_cluster_id: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "speaker": self.speaker,
                "text": self.text,
                "embedding": self.embedding_b64,
                "contradictions": self.contradiction_pair_ids,
                "topic_cluster_id": self.topic_cluster_id,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FinalizedClaimLine:
        return cls(
            timestamp=str(d["timestamp"]),
            speaker=str(d["speaker"]),
            text=str(d["text"]),
            embedding_b64=str(d.get("embedding", "")),
            contradiction_pair_ids=list(d.get("contradictions", [])),
            topic_cluster_id=str(d.get("topic_cluster_id", "")),
        )


class SessionJSONLWriter:
    """Thread-safe append to ``session.jsonl``."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append_claim(
        self,
        *,
        speaker: str,
        text: str,
        embedding: list[float] | np.ndarray,
        contradiction_pair_ids: list[str],
        topic_cluster_id: str,
        at: Optional[datetime] = None,
    ) -> None:
        ts = (at or datetime.now(timezone.utc)).isoformat()
        line = FinalizedClaimLine(
            timestamp=ts,
            speaker=speaker,
            text=text,
            embedding_b64=_b64_f32(embedding),
            contradiction_pair_ids=contradiction_pair_ids,
            topic_cluster_id=topic_cluster_id,
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line.to_jsonl() + "\n")


def iter_session_claims(path: Path | str) -> list[FinalizedClaimLine]:
    out: list[FinalizedClaimLine] = []
    p = Path(path)
    if not p.is_file():
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(FinalizedClaimLine.from_dict(json.loads(line)))
    return out


__all__ = [
    "SessionJSONLWriter",
    "FinalizedClaimLine",
    "iter_session_claims",
    "_decode_b64_f32",
]
