"""
Public retrieval — read-only retrieval for the public-facing inquiry box.

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

What Round 17 prompt 28 added on top of the first-version retriever:

  * **Query understanding** — `query_classifier.classify_query` routes
    each query into one of five classes, each with its own
    `RetrievalProfile` (kind ordering, per-kind boosts, MMR λ).
  * **Diverse retrieval** — Maximum Marginal Relevance (`mmr_select`)
    so the top results are not five paraphrases of one conclusion.
  * **Honest empty result** — the no-result branch now surfaces both
    the closest open question *and* the closest related conclusion,
    so the page is a useful pointer rather than a dead end.
  * **Freshness** — every result carries its date and a
    "still considered current" flag. Stale conclusions are *not*
    silently de-ranked; the reader is told they are stale.
  * **Query-log discipline** — `prune_query_log` enforces the 24h raw
    query retention; only the hashed bucket + class survive longer.

The module is dependency-light by design: numpy only, no
sentence-transformers import (callers pass embeddings in). Tests
inject a deterministic fake embedder; production wiring inside the
Currents service would inject the same SBERT instance the rest of the
inference engine uses.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from noosphere.inference.query_classifier import (
    DEFAULT_CLASS,
    Classification,
    JudgeFn,
    RetrievalProfile,
    classify_query,
    retrieval_profile,
)


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

# Maximum Marginal Relevance tradeoff. λ weights pure relevance; (1-λ)
# weights dissimilarity from the items already picked. The default
# favours relevance but keeps a meaningful diversity component, so the
# top results are not paraphrases of one conclusion. Per-class profiles
# (see `query_classifier.RetrievalProfile`) override this — a
# counter-argument query, for instance, runs a much lower λ to surface
# the spread of disagreement rather than the loudest echo.
MMR_LAMBDA_DEFAULT = 0.7

# A conclusion older than this (and without an explicit still-current
# flag) is shown with a "stale" pill. It is NOT de-ranked — staleness is
# surfaced to the reader, never used to silently bury a result.
FRESHNESS_STALE_DAYS = 365

# Raw query strings logged for analytics are dropped after this many
# hours; only the hashed bucket id and the query class survive longer.
# Enforced by `prune_query_log`, on the same schedule the retention
# runner sweeps the cross-process stores.
RAW_QUERY_TTL_HOURS = 24


# ── Data shapes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PublicCorpusItem:
    """A single public-visible item the retriever can rank.

    `text` is the body the retriever scores against and pulls a snippet
    from. `title` is shown verbatim in results. `embedding` may be None
    (caller will encode lazily); callers that pre-embed the corpus
    should pass it.

    `occurred_at` is the item's public date (publishedAt for
    conclusions/articles, generatedAt for opinions, createdAt for open
    questions). `still_current` is an explicit override: when the firm
    has affirmatively reviewed an item it sets True/False here and the
    age heuristic is bypassed.
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
    occurred_at: Optional[datetime] = None
    still_current: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.kind not in ITEM_KINDS:
            raise ValueError(
                f"unknown kind {self.kind!r}; expected one of {ITEM_KINDS}"
            )


@dataclass
class RetrievedItem:
    """A scored result. `snippet` is extracted, never generated.

    `is_current` is the freshness signal the UI renders as a pill;
    `occurred_at` is the date shown alongside it.
    """

    item: PublicCorpusItem
    score: float
    snippet: str
    is_current: bool = True
    occurred_at: Optional[datetime] = None


@dataclass
class PublicRetrievalResponse:
    """The full payload the public ask box renders.

    `no_result` flips when nothing clears `NO_RESULT_THRESHOLD`. When it
    does, both `closest_open_question` and `closest_related_conclusion`
    are surfaced regardless of the threshold so the page can show "the
    firm has not addressed this directly" while still pointing the
    reader somewhere useful (and inviting a research suggestion).

    `query_class` / `render_hint` carry the query-understanding verdict
    through to the renderer so each class gets its own layout.
    """

    query: str
    by_kind: dict
    closest_open_question: Optional[RetrievedItem]
    no_result: bool
    suggested_rephrasings: List[str] = field(default_factory=list)
    query_class: str = DEFAULT_CLASS
    render_hint: str = "browse"
    closest_related_conclusion: Optional[RetrievedItem] = None


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


# ── Maximum Marginal Relevance ─────────────────────────────────────────────


@dataclass
class _Candidate:
    """An item plus the scalars MMR needs: its relevance to the query
    and the embedding used to measure item-to-item similarity."""

    item: PublicCorpusItem
    relevance: float
    embedding: np.ndarray


def mmr_select(
    candidates: Sequence[_Candidate],
    *,
    lambda_: float,
    k: int,
) -> List[_Candidate]:
    """Maximum Marginal Relevance selection.

    Greedily picks `k` items, each step maximising

        λ · relevance − (1 − λ) · max similarity-to-already-picked

    so the result set trades raw relevance against not being five
    near-duplicates. The very first pick is always the most relevant
    item (no penalty term yet) — which is why the relevance-ordered
    goldens stay stable under any λ.

    Relevance is normalised to [0, 1] across the candidate set so λ
    means the same thing regardless of the underlying score scale.
    """
    if k <= 0 or not candidates:
        return []
    lam = max(0.0, min(1.0, lambda_))

    max_rel = max((c.relevance for c in candidates), default=0.0)
    norm = max_rel if max_rel > 1e-12 else 1.0

    remaining = list(candidates)
    selected: List[_Candidate] = []
    while remaining and len(selected) < k:
        best_idx = 0
        best_val = float("-inf")
        for i, cand in enumerate(remaining):
            rel = cand.relevance / norm
            if selected:
                penalty = max(
                    cosine(cand.embedding, s.embedding) for s in selected
                )
            else:
                penalty = 0.0
            val = lam * rel - (1.0 - lam) * penalty
            if val > best_val:
                best_val = val
                best_idx = i
        selected.append(remaining.pop(best_idx))
    return selected


# ── Freshness ──────────────────────────────────────────────────────────────


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def compute_freshness(
    item: PublicCorpusItem,
    now: datetime,
    *,
    stale_after_days: int = FRESHNESS_STALE_DAYS,
) -> bool:
    """Return whether `item` is "still considered current".

    An explicit `still_current` flag on the item always wins — that is
    the firm affirmatively standing behind (or retiring) a conclusion.
    Absent that, an item with a date older than `stale_after_days` is
    stale. An item with no date at all is treated as current: we never
    fabricate a stale signal we cannot back with a date.
    """
    if item.still_current is not None:
        return bool(item.still_current)
    if item.occurred_at is not None:
        age_days = (now - _as_aware(item.occurred_at)).total_seconds() / 86400.0
        return age_days < stale_after_days
    return True


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
    passes the firm's SBERT instance. An optional `judge` callable is
    threaded through to the query classifier — production wires the
    light LLM judge here; tests pass a deterministic fake or None.
    """

    def __init__(
        self,
        embed: Callable[[str], np.ndarray],
        *,
        judge: Optional[JudgeFn] = None,
    ):
        self.embed = embed
        self.judge = judge

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
        return [(item, score) for item, score, _ in self._scored(query, corpus)]

    def _scored(
        self,
        query: str,
        corpus: Sequence[PublicCorpusItem],
    ) -> List[Tuple[PublicCorpusItem, float, np.ndarray]]:
        """Like `rank`, but also returns the embedding used per item so
        MMR can measure item-to-item similarity without re-embedding."""
        q = (query or "").strip()
        if not q:
            return []
        q_emb = self.embed(q)
        scored: List[Tuple[PublicCorpusItem, float, np.ndarray]] = []
        for item in corpus:
            if not item.is_public:
                continue
            emb = (
                item.embedding
                if item.embedding is not None
                else self.embed(item.text)
            )
            scored.append((item, cosine(q_emb, emb), np.asarray(emb, dtype=float)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def retrieve(
        self,
        query: str,
        corpus: Sequence[PublicCorpusItem],
        *,
        top_per_kind: int = DEFAULT_TOP_PER_KIND,
        query_class: Optional[str] = None,
        classification: Optional[Classification] = None,
        mmr_lambda: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> PublicRetrievalResponse:
        """Run the full public-ask retrieval pipeline.

        Steps:
          1. Drop private items, score everything by cosine.
          2. Resolve the query class (caller-supplied, or classified
             here) and its `RetrievalProfile`.
          3. Group by kind, apply the profile's per-kind boost for
             *ordering only*, and run MMR within each kind so the rail
             is diverse rather than five paraphrases.
          4. Attach extractive snippets and the per-item freshness flag.
          5. If the global top *raw* score is below the no-result
             threshold, flip `no_result` and still attach the closest
             open question AND the closest related conclusion (both
             chosen across the whole corpus, not gated by threshold).
          6. If the global top raw score sits in the borderline band,
             surface up to three "suggested rephrasings".

        Note the threshold and borderline logic run off the *raw* cosine
        score, never the boosted one — honesty about silence stays
        calibrated regardless of how a class re-weights its rails.
        """
        now = now or datetime.now(timezone.utc)

        if classification is None:
            if query_class is not None:
                classification = Classification(query_class, 1.0, "caller")
            else:
                classification = classify_query(query, judge=self.judge)
        profile = retrieval_profile(classification.query_class)
        lam = profile.mmr_lambda if mmr_lambda is None else mmr_lambda

        scored = self._scored(query, corpus)

        # Group candidates by kind. `relevance` is the boosted score
        # used for ordering + MMR; the raw cosine is kept separately for
        # the threshold and for what we show the reader.
        raw_by_id = {item.id: raw for item, raw, _ in scored}
        candidates_by_kind: dict = {kind: [] for kind in ITEM_KINDS}
        for item, raw, emb in scored:
            boost = profile.kind_boost.get(item.kind, 1.0)
            candidates_by_kind.setdefault(item.kind, []).append(
                _Candidate(item=item, relevance=raw * boost, embedding=emb)
            )

        by_kind: dict = {kind: [] for kind in ITEM_KINDS}
        for kind, cands in candidates_by_kind.items():
            picked = mmr_select(cands, lambda_=lam, k=top_per_kind)
            for cand in picked:
                by_kind.setdefault(kind, []).append(
                    self._to_retrieved(cand.item, raw_by_id[cand.item.id], query, now)
                )

        top_score = scored[0][1] if scored else 0.0
        no_result = top_score < NO_RESULT_THRESHOLD

        # Closest open question + closest related conclusion: the best
        # item of each kind across the whole corpus, surfaced regardless
        # of threshold so the no-result page is a pointer, not a wall.
        closest_oq = self._first_of_kind(scored, "open_question", query, now)
        closest_conclusion = self._first_of_kind(scored, "conclusion", query, now)

        rephrasings: List[str] = []
        if scored and BORDERLINE_LOWER <= top_score < BORDERLINE_UPPER:
            seen = {scored[0][0].id}
            for item, _, _ in scored[1:]:
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
            query_class=classification.query_class,
            render_hint=profile.render_hint,
            closest_related_conclusion=closest_conclusion,
        )

    # ── internals ──────────────────────────────────────────────────────

    def _to_retrieved(
        self,
        item: PublicCorpusItem,
        score: float,
        query: str,
        now: datetime,
    ) -> RetrievedItem:
        return RetrievedItem(
            item=item,
            score=score,
            snippet=extract_snippet(item.text, query, embed=self.embed),
            is_current=compute_freshness(item, now),
            occurred_at=item.occurred_at,
        )

    def _first_of_kind(
        self,
        scored: Sequence[Tuple[PublicCorpusItem, float, np.ndarray]],
        kind: str,
        query: str,
        now: datetime,
    ) -> Optional[RetrievedItem]:
        for item, score, _ in scored:
            if item.kind == kind:
                return self._to_retrieved(item, score, query, now)
        return None


# ── Query bucketing for safe logging ───────────────────────────────────────


def hash_query_bucket(query: str, *, salt: str = "theseus-public-ask") -> str:
    """Return a short bucket id for a query.

    Public ask is anonymous; we never log raw queries indefinitely (a
    reader could later reconstruct what a previous reader asked). When
    logging at all, we log this bucket — sha256(salt|normalized_query),
    truncated to 12 hex chars. Useful for coarse abuse / load
    aggregation; not useful for reconstruction.
    """
    norm = _WHITESPACE.sub(" ", (query or "").lower()).strip()
    h = hashlib.sha256(f"{salt}|{norm}".encode("utf-8")).hexdigest()
    return h[:12]


# ── Query-log retention discipline ─────────────────────────────────────────


@dataclass
class QueryLogEntry:
    """One logged public-ask query.

    The `bucket` (hashed) and `query_class` are kept indefinitely for
    coarse analytics — what *kinds* of question readers ask, and how
    often a bucket recurs. `raw_query` is retained only briefly (for
    same-day abuse / quality investigation) and is dropped by
    `prune_query_log` once older than `RAW_QUERY_TTL_HOURS`.
    """

    bucket: str
    query_class: str
    logged_at: datetime
    raw_query: Optional[str] = None


def make_query_log_entry(
    query: str,
    query_class: str,
    *,
    now: Optional[datetime] = None,
    retain_raw: bool = True,
) -> QueryLogEntry:
    """Build a `QueryLogEntry` from a query.

    `retain_raw=False` (the staging/production default for surfaces
    that do not need same-day raw inspection) means the raw string is
    never written at all — the strongest form of the retention policy.
    """
    now = now or datetime.now(timezone.utc)
    return QueryLogEntry(
        bucket=hash_query_bucket(query),
        query_class=query_class,
        logged_at=now,
        raw_query=(query if retain_raw else None),
    )


def prune_query_log(
    entries: Sequence[QueryLogEntry],
    *,
    now: Optional[datetime] = None,
    raw_ttl_hours: int = RAW_QUERY_TTL_HOURS,
) -> Tuple[List[QueryLogEntry], int]:
    """Enforce the public-ask query-log retention policy.

    Returns `(pruned_entries, raw_dropped_count)`. Every entry survives
    — the hashed bucket and query class are analytics data with no
    retention limit — but any `raw_query` older than `raw_ttl_hours`
    is set to None.

    This mirrors what the retention runner
    (`noosphere/decay/retention_runner.py`, Round 17 prompt 46)
    enforces for the cross-process Postgres stores. Keeping the rule
    here too means the in-process query log is pruned on the same
    schedule and is unit-testable against the same 24h boundary —
    including on staging, where the constraint still holds.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=raw_ttl_hours)
    pruned: List[QueryLogEntry] = []
    dropped = 0
    for entry in entries:
        logged_at = _as_aware(entry.logged_at)
        if entry.raw_query is not None and logged_at < cutoff:
            dropped += 1
            pruned.append(
                QueryLogEntry(
                    bucket=entry.bucket,
                    query_class=entry.query_class,
                    logged_at=entry.logged_at,
                    raw_query=None,
                )
            )
        else:
            pruned.append(entry)
    return pruned, dropped


__all__ = [
    "BORDERLINE_LOWER",
    "BORDERLINE_UPPER",
    "DEFAULT_TOP_PER_KIND",
    "FRESHNESS_STALE_DAYS",
    "ITEM_KINDS",
    "MMR_LAMBDA_DEFAULT",
    "NO_RESULT_THRESHOLD",
    "RAW_QUERY_TTL_HOURS",
    "PublicCorpusItem",
    "PublicRetrievalResponse",
    "PublicRetriever",
    "QueryLogEntry",
    "RetrievedItem",
    "compute_freshness",
    "cosine",
    "extract_snippet",
    "hash_query_bucket",
    "make_query_log_entry",
    "mmr_select",
    "prune_query_log",
]
