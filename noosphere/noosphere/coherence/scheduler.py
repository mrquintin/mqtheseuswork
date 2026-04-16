"""
Decide which claim pairs to evaluate for coherence (neighbors, same topic/author, firm conclusions).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from noosphere.models import Claim, Conclusion, Speaker
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    if va.shape != vb.shape or va.size == 0:
        return -1.0
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na < 1e-12 or nb < 1e-12:
        return -1.0
    return float(np.dot(va, vb) / (na * nb))


def conclusion_to_claim(c: Conclusion) -> Claim:
    """Represent a firm conclusion as a Claim-shaped node for pairwise checks."""
    return Claim(
        id=c.id,
        text=c.text,
        speaker=Speaker(id="firm", name="firm"),
        episode_id="",
        episode_date=date.today(),
    )


def schedule_pairs_for_new_claim(
    store: Store,
    claim: Claim,
    *,
    k_neighbors: int = 20,
) -> list[tuple[str, str]]:
    """
    Return canonical (id_a, id_b) pairs to evaluate for ``claim`` (id always first = claim.id).

    Strategy:
    (a) ``k_neighbors`` nearest claims by embedding on in-memory claim payloads.
    (b) Prior claims by same speaker name on the same topic cluster.
    (c) All firm-level conclusions from the conclusion store.
    """
    if not claim.embedding:
        logger.warning("schedule_pairs_no_embedding", claim_id=claim.id)

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_pair(other_id: str) -> None:
        if other_id == claim.id:
            return
        a, b = (claim.id, other_id) if claim.id < other_id else (other_id, claim.id)
        key = (a, b)
        if key in seen:
            return
        seen.add(key)
        pairs.append((a, b))

    # (a) Nearest neighbors by embedding
    scored: list[tuple[float, str]] = []
    for cid in store.list_claim_ids():
        if cid == claim.id:
            continue
        oc = store.get_claim(cid)
        if oc is None or not oc.embedding or not claim.embedding:
            continue
        sim = _cosine_sim(claim.embedding, oc.embedding)
        scored.append((sim, cid))
    scored.sort(key=lambda x: -x[0])
    for _, oid in scored[:k_neighbors]:
        add_pair(oid)

    # (b) Same author + same topic
    topic = store.get_topic_id_for_claim(claim.id)
    author = claim.speaker.name.strip().lower()
    if topic and author:
        for cid in store.list_claim_ids():
            if cid == claim.id:
                continue
            oc = store.get_claim(cid)
            if oc is None:
                continue
            if oc.speaker.name.strip().lower() != author:
                continue
            if store.get_topic_id_for_claim(cid) != topic:
                continue
            add_pair(cid)

    # (c) Firm conclusions
    for conc in store.list_conclusions():
        add_pair(conc.id)

    return pairs


def pair_key_sorted(id_a: str, id_b: str) -> tuple[str, str]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)
