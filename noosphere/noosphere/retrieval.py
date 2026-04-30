"""
Hybrid retrieval over stored claims: BM25-style FTS5 + dense embedding similarity.

Coverage is limited to what is indexed in SQLite and which claims have embeddings;
callers must surface empty hits honestly (no invented literature).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Any, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback is for broken local wheels.
    np = None  # type: ignore[assignment]
from sqlalchemy import text

from noosphere.models import Claim, ClaimOrigin
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


def _float_vector(value: Any) -> list[float]:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        if len(raw) % 4 != 0:
            return []
        return [float(x) for x in struct.unpack(f"<{len(raw) // 4}f", raw)]
    if hasattr(value, "ravel") and np is not None:
        value = value.ravel()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(x) for x in value]


def _cosine(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    left_norm = sum(x * x for x in left) ** 0.5
    right_norm = sum(x * x for x in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _fts_safe_query(q: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]{2,}", q)[:12]
    if not tokens:
        return "empty"
    return " OR ".join(tokens)


@dataclass(frozen=True)
class RetrievalHit:
    claim_id: str
    text: str
    artifact_id: str
    chunk_id: str
    score: float
    claim_origin: str


class HybridRetriever:
    """Rebuildable FTS5 table + optional embedding rerank over ``Store`` claims."""

    fts_table = "retrieval_claim_fts"

    def _supports_fts5(self, store: Store) -> bool:
        return store.engine.dialect.name == "sqlite"

    def rebuild(self, store: Store, *, origins: Optional[set[ClaimOrigin]] = None) -> int:
        """Drop/recreate FTS index and populate from claims (optional origin filter)."""
        if not self._supports_fts5(store):
            logger.info(
                "retrieval_fts_skipped",
                dialect=store.engine.dialect.name,
            )
            return 0

        origins = origins or {
            ClaimOrigin.FOUNDER,
            ClaimOrigin.VOICE,
            ClaimOrigin.LITERATURE,
            ClaimOrigin.SYSTEM,
        }
        n = 0
        with store.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {self.fts_table}"))
            conn.execute(
                text(
                    f"CREATE VIRTUAL TABLE {self.fts_table} USING fts5(claim_id UNINDEXED, body)"
                )
            )
            for cid in store.list_claim_ids():
                c = store.get_claim(cid)
                if c is None or c.claim_origin not in origins:
                    continue
                body = (c.text or "")[:12000]
                if len(body.strip()) < 8:
                    continue
                conn.execute(
                    text(f"INSERT INTO {self.fts_table}(claim_id, body) VALUES (:id, :b)"),
                    {"id": cid, "b": body},
                )
                n += 1
        logger.info("retrieval_fts_rebuilt", rows=n)
        return n

    def bm25_hits(self, store: Store, query_text: str, *, limit: int = 25) -> list[tuple[str, float]]:
        if not self._supports_fts5(store):
            return []

        q = _fts_safe_query(query_text)
        if q == "empty":
            return []
        sql = text(
            f"SELECT claim_id, bm25({self.fts_table}) AS rank "
            f"FROM {self.fts_table} WHERE {self.fts_table} MATCH :m "
            "ORDER BY rank ASC LIMIT :lim"
        )
        with store.engine.connect() as conn:
            try:
                rows = conn.execute(sql, {"m": q, "lim": limit}).fetchall()
            except Exception as e:
                logger.warning("retrieval_fts_query_failed", error=str(e))
                return []
        out: list[tuple[str, float]] = []
        for claim_id, rank in rows:
            try:
                r = float(rank)
            except (TypeError, ValueError):
                r = 0.0
            out.append((str(claim_id), r))
        return out

    def dense_scores(
        self,
        store: Store,
        query_embedding: Any,
        claim_ids: list[str],
        *,
        limit: int = 40,
    ) -> dict[str, float]:
        if np is not None:
            q = np.asarray(query_embedding, dtype=float).ravel()
            qn = float(np.linalg.norm(q) + 1e-9)
        else:
            q_fallback = _float_vector(query_embedding)
        scores: dict[str, float] = {}
        for cid in claim_ids[:800]:
            c = store.get_claim(cid)
            if c is None or not c.embedding:
                continue
            if np is not None:
                v = np.asarray(c.embedding, dtype=float).ravel()
                if v.shape != q.shape:
                    continue
                sim = float(np.dot(q, v) / (qn * (np.linalg.norm(v) + 1e-9)))
            else:
                maybe_sim = _cosine(q_fallback, _float_vector(c.embedding))
                if maybe_sim is None:
                    continue
                sim = maybe_sim
            scores[cid] = sim
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return dict(top)

    def search(
        self,
        store: Store,
        *,
        query_text: str,
        query_embedding: Any | None,
        top_k: int = 12,
        origins: Optional[set[ClaimOrigin]] = None,
    ) -> list[RetrievalHit]:
        """
        Hybrid merge: FTS candidates union dense top-K (when embedding provided), RRF-style fuse.
        """
        origins = origins or {ClaimOrigin.FOUNDER, ClaimOrigin.VOICE, ClaimOrigin.LITERATURE}
        bm = self.bm25_hits(store, query_text, limit=40)
        bm_ids = [c for c, _ in bm]
        dense_map: dict[str, float] = {}
        if query_embedding is not None:
            pool = list(dict.fromkeys(bm_ids + store.list_claim_ids()[:400]))
            dense_map = self.dense_scores(store, query_embedding, pool, limit=30)

        rrf: dict[str, float] = {}
        for i, (cid, _) in enumerate(bm):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (60 + i)
        for i, cid in enumerate(sorted(dense_map, key=lambda x: dense_map[x], reverse=True)):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (40 + i)

        ranked = sorted(rrf.keys(), key=lambda c: rrf[c], reverse=True)[: max(top_k * 3, 20)]
        hits: list[RetrievalHit] = []
        for cid in ranked:
            if len(hits) >= top_k:
                break
            c = store.get_claim(cid)
            if c is None or c.claim_origin not in origins:
                continue
            hits.append(
                RetrievalHit(
                    claim_id=c.id,
                    text=c.text[:1200],
                    artifact_id=c.source_id or "",
                    chunk_id=c.chunk_id or "",
                    score=float(rrf.get(cid, 0.0)),
                    claim_origin=c.claim_origin.value,
                )
            )
        return hits
