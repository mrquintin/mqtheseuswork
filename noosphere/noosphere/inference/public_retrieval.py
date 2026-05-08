"""
Public retrieval — read-only, embedding-driven retrieval for the
public-facing inquiry box.

This is the Python-side companion to
`theseus-codex/src/lib/publicAsk.ts`. The TS layer owns the live
Postgres reads and the snippet/visibility plumbing the Next.js route
returns to readers; this module owns the ranking semantics that the
firm's tests pin down.

Why a Python module at all? Two reasons:

1. The firm already owns a sentence-transformer-driven retriever
   (`PrincipleRetriever` in `_engine.py`). The public surface should
   share its embedding contract — same cosine metric, same borderline
   threshold logic — so a future cutover to the Currents Python
   service is a wire-level change, not a re-derivation of ranking.

2. The honesty constraints (extractive snippets, no LLM rewriting,
   no-result fallback to the closest open question, borderline
   "suggested rephrasings") are testable against synthetic embeddings
   here. Pinning them in pytest lets us assert ranking stability
   under small query perturbations and verify the no-result threshold
   fires at the right boundary — the goldens the spec asks for.

The module is dependency-light by design: numpy only, no
sentence-transformers import (callers pass embeddings in). Tests
inject a deterministic fake embedder; production wiring inside the
Currents service would inject the same SBERT instance the rest of the
inference engine uses.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# ── Item kinds the public surface returns ──────────────────────────────────

ITEM_KINDS = ("conclusion", "opinion", "article", "open_question")


# ── Tunables ───────────────────────────────────────────────────────────────

# Cosine score below which we treat the corpus as effectively silent on
# the question and render the no-result fallback. Picked above the 0.25
# noise floor we see between unrelated SBERT vectors and below the 0.40
# band where genuine topical overlap starts to register.
NO_RESULT_THRESHOLD = 0.32

# Band where the top result is suggestive but not a clean hit. We render
# it but also surface "did you mean…" rephrasings sourced from the
# next-nearest items.
BORDERLINE_LOWER = NO_RESULT_THRESHOLD
BORDERLINE_UPPER = 0.45

# Per-kind cap returned to the client. The UI is keyboard-navigated and
# information-dense, so a small N keeps the page legible.
DEFAULT_TOP_PER_KIND = 5

# Snippet width in characters. Extractive — we cut a window around the
# best-matching sentence; we never paraphrase.
SNIPPET_CHARS = 240


# ── Data shapes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PublicCorpusItem:
    """A single public-visible item the retriever can rank.

    `text` is the body the retriever scores against and pulls a snippet
    from. `title` is shown verbatim in results. `embedding` may be None
    (caller will encode lazily); callers that pre-embed the corpus
    should pass it.
    """

    id: str
    kind: str
    title: str
    text: str
    href: str
    confidence: Optional[float] = None
    methodology: Optional[str] = None
    is_public: bool = True
    embedding: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        if self.kind not in ITEM_KINDS:
            raise ValueError(
                f"unknown kind {self.kind!r}; expected one of {ITEM_KINDS}"
            )


@dataclass
class RetrievedItem:
    """A scored result. `snippet` is extracted, never generated."""

    item: PublicCorpusItem
    score: float
    snippet: str


@dataclass
class PublicRetrievalResponse:
    """The full payload the public ask box renders.

    `no_result` flips when nothing clears `NO_RESULT_THRESHOLD`. The
    closest open question is surfaced regardless so the page can show
    "the firm has not addressed this directly" without going silent.
    """

    query: str
    by_kind: dict
    closest_open_question: Optional[RetrievedItem]
    no_result: bool
    suggested_rephrasings: List[str] = field(default_factory=list)


# ── Embedding helpers ──────────────────────────────────────────────────────


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity. Returns 0 on either zero vector."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── Snippet extraction (extractive, no rewriting) ──────────────────────────


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WHITESPACE = re.compile(r"\s+")


def extract_snippet(
    text: str,
    query: str,
    *,
    embed: Callable[[str], np.ndarray],
    max_chars: int = SNIPPET_CHARS,
) -> str:
    """Return the best-matching contiguous window from `text`.

    Strategy: split into sentences, score each by cosine to the query,
    and return the top sentence (plus a small amount of trailing
    context, never exceeding `max_chars`). No paraphrasing happens — we
    only choose a window of the original.
    """
    cleaned = _WHITESPACE.sub(" ", text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    if not sentences:
        return cleaned[:max_chars].rstrip() + "…"

    q_emb = embed(query)
    best_idx = 0
    best_score = -1.0
    for i, sent in enumerate(sentences):
        score = cosine(q_emb, embed(sent))
        if score > best_score:
            best_score = score
            best_idx = i

    chosen = sentences[best_idx]
    j = best_idx + 1
    while j < len(sentences) and len(chosen) + 1 + len(sentences[j]) <= max_chars:
        chosen = chosen + " " + sentences[j]
        j += 1
    if len(chosen) > max_chars:
        chosen = chosen[:max_chars].rstrip() + "…"
    return chosen


# ── Retriever ──────────────────────────────────────────────────────────────


class PublicRetriever:
    """Embedding-similarity retriever for the public ask box.

    Construction takes an `embed` callable (any string -> 1D ndarray)
    so tests can inject a deterministic fake while production wiring
    passes the firm's SBERT instance.
    """

    def __init__(self, embed: Callable[[str], np.ndarray]):
        self.embed = embed

    # ── public API ─────────────────────────────────────────────────────

    def rank(
        self,
        query: str,
        corpus: Sequence[PublicCorpusItem],
    ) -> List[Tuple[PublicCorpusItem, float]]:
        """Score every public item by cosine to the query.

        Private items (`is_public=False`) are dropped before ranking.
        Returns a list sorted descending by score.
        """
        q = (query or "").strip()
        if not q:
            return []
        q_emb = self.embed(q)
        scored: List[Tuple[PublicCorpusItem, float]] = []
        for item in corpus:
            if not item.is_public:
                continue
            emb = item.embedding if item.embedding is not None else self.embed(item.text)
            scored.append((item, cosine(q_emb, emb)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def retrieve(
        self,
        query: str,
        corpus: Sequence[PublicCorpusItem],
        *,
        top_per_kind: int = DEFAULT_TOP_PER_KIND,
    ) -> PublicRetrievalResponse:
        """Run the full public-ask retrieval pipeline.

        Steps:
          1. Drop private items, score everything by cosine.
          2. Group by kind, keep top-K each.
          3. Attach extractive snippets.
          4. If the global top score is below the no-result threshold,
             flip `no_result` and still attach the closest open question
             (chosen across the whole corpus, not gated by threshold).
          5. If the global top score sits in the borderline band,
             surface up to three "suggested rephrasings" — the next
             items' titles, which are usually adjacent topics.
        """
        scored = self.rank(query, corpus)

        by_kind: dict = {kind: [] for kind in ITEM_KINDS}
        for item, score in scored:
            bucket = by_kind.setdefault(item.kind, [])
            if len(bucket) >= top_per_kind:
                continue
            snippet = extract_snippet(item.text, query, embed=self.embed)
            bucket.append(RetrievedItem(item=item, score=score, snippet=snippet))

        top_score = scored[0][1] if scored else 0.0
        no_result = top_score < NO_RESULT_THRESHOLD

        # Closest open question: best-scoring item with kind=open_question.
        # Always present in the response so the page can fall back to
        # "the firm has not addressed this directly — but here's what's
        # still open."
        closest_oq: Optional[RetrievedItem] = None
        for item, score in scored:
            if item.kind == "open_question":
                snippet = extract_snippet(item.text, query, embed=self.embed)
                closest_oq = RetrievedItem(item=item, score=score, snippet=snippet)
                break

        rephrasings: List[str] = []
        if scored and BORDERLINE_LOWER <= top_score < BORDERLINE_UPPER:
            seen = {scored[0][0].id}
            for item, _ in scored[1:]:
                if item.id in seen:
                    continue
                seen.add(item.id)
                rephrasings.append(item.title)
                if len(rephrasings) >= 3:
                    break

        return PublicRetrievalResponse(
            query=query,
            by_kind=by_kind,
            closest_open_question=closest_oq,
            no_result=no_result,
            suggested_rephrasings=rephrasings,
        )


# ── Query bucketing for safe logging ───────────────────────────────────────


def hash_query_bucket(query: str, *, salt: str = "theseus-public-ask") -> str:
    """Return a short bucket id for a query.

    Public ask is anonymous; we never log raw queries (a reader could
    later reconstruct what a previous reader asked). When logging at
    all, we log this bucket instead — sha256(salt|normalized_query),
    truncated to 12 hex chars. Useful for coarse abuse / load
    aggregation; not useful for reconstruction.
    """
    norm = _WHITESPACE.sub(" ", (query or "").lower()).strip()
    h = hashlib.sha256(f"{salt}|{norm}".encode("utf-8")).hexdigest()
    return h[:12]


__all__ = [
    "BORDERLINE_LOWER",
    "BORDERLINE_UPPER",
    "DEFAULT_TOP_PER_KIND",
    "ITEM_KINDS",
    "NO_RESULT_THRESHOLD",
    "PublicCorpusItem",
    "PublicRetrievalResponse",
    "PublicRetriever",
    "RetrievedItem",
    "cosine",
    "extract_snippet",
    "hash_query_bucket",
]
