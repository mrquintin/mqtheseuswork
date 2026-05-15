"""Quality goldens for the Round 17 prompt 28 public-ask upgrade.

First-version public retrieval ranked purely by embedding similarity:
it surfaced near-duplicate snippets and treated every query the same.
This suite pins the four things the upgrade added:

  1. **Query understanding** — a golden set of queries classifies into
     the right class, and the light LLM judge breaks ties only when the
     rule layer is genuinely ambiguous.
  2. **Diverse retrieval** — Maximum Marginal Relevance does not return
     five paraphrases of one conclusion; lowering λ measurably lowers
     the result set's internal similarity.
  3. **Honest empty result** — a far-off-topic query flips `no_result`
     and still surfaces *both* the closest open question and the
     closest related conclusion, so the page is a pointer not a wall.
  4. **Query-log discipline** — `prune_query_log` drops raw query
     strings older than 24h while keeping the hashed bucket + class.

The fake embedder is a deterministic topic-vector projection: related
sentences cluster, unrelated sentences sit near zero. Where a test
needs an exact embedding it constructs the `PublicCorpusItem` with an
explicit vector.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from noosphere.inference.query_classifier import (
    QUERY_CLASSES,
    classify_query,
    retrieval_profile,
)
from noosphere.inference.public_retrieval import (
    NO_RESULT_THRESHOLD,
    RAW_QUERY_TTL_HOURS,
    PublicCorpusItem,
    PublicRetriever,
    QueryLogEntry,
    compute_freshness,
    cosine,
    make_query_log_entry,
    mmr_select,
    prune_query_log,
)
from noosphere.inference.public_retrieval import _Candidate  # internal: MMR input


NOW = datetime(2026, 5, 14, tzinfo=timezone.utc)


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


# ── Fake embedder ──────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+")
_DIM = 128

_TOPICS: dict[str, set[str]] = {
    "inflation": {
        "inflation", "monetary", "money", "supply", "wage", "wages",
        "price", "prices", "spiral", "spirals", "rates", "rate",
    },
    "land": {
        "land", "value", "capture", "transit", "density", "city",
        "cities", "metro", "infrastructure", "property", "tax",
    },
    "conviction": {
        "conviction", "belief", "beliefs", "geometry", "direction",
        "scalar", "analyst", "analysts",
    },
}


def _unit(idx: int) -> np.ndarray:
    rng = np.random.default_rng(0xA5_0000 + idx)
    v = rng.standard_normal(_DIM)
    return v / float(np.linalg.norm(v))


_TOPIC_VECS = {name: _unit(i) for i, name in enumerate(_TOPICS)}


def _noise(token: str) -> np.ndarray:
    rng = np.random.default_rng(
        int.from_bytes(token.encode("utf-8")[:8].ljust(8, b"\0"), "big")
    )
    return 0.04 * rng.standard_normal(_DIM)


def fake_embed(text: str) -> np.ndarray:
    toks = _TOKEN.findall((text or "").lower())
    if not toks:
        return np.zeros(_DIM)
    v = np.zeros(_DIM)
    for t in toks:
        for name, vocab in _TOPICS.items():
            if t in vocab:
                v = v + _TOPIC_VECS[name]
                break
        else:
            v = v + _noise(t)
    n = float(np.linalg.norm(v))
    return v if n < 1e-10 else v / n


def _item(*, id, kind, title, text, occurred_at=None, still_current=None,
          confidence=0.7, methodology="six_layer_coherence", is_public=True):
    return PublicCorpusItem(
        id=id, kind=kind, title=title, text=text,
        href=f"/{kind}/{id}", confidence=confidence, methodology=methodology,
        is_public=is_public, embedding=fake_embed(text),
        occurred_at=occurred_at, still_current=still_current,
    )


@pytest.fixture
def corpus() -> list[PublicCorpusItem]:
    return [
        _item(
            id="c1", kind="conclusion",
            title="Inflation is a monetary phenomenon",
            text="Inflation in the long run is a monetary phenomenon driven "
                 "by money supply growth.",
            occurred_at=_ago(40),
        ),
        _item(
            id="c2", kind="conclusion",
            title="Land value capture funds infrastructure",
            text="Capturing land value uplift around new transit pays for "
                 "the transit infrastructure itself.",
            occurred_at=_ago(900),  # old → stale
        ),
        _item(
            id="o1", kind="opinion",
            title="On the rate-hike path",
            text="A tighter monetary stance raises real rates and money "
                 "market pressure builds.",
            occurred_at=_ago(10), confidence=0.55,
        ),
        _item(
            id="a1", kind="article",
            title="The geometry of conviction",
            text="Conviction is a direction in belief space, not a scalar "
                 "an analyst can quote.",
            occurred_at=_ago(120), confidence=0.8,
        ),
        _item(
            id="q1", kind="open_question",
            title="Does land value capture work in low-density cities?",
            text="Whether the land value capture mechanism still pays for "
                 "infrastructure in low-density cities is unresolved.",
            occurred_at=_ago(30), confidence=None, methodology=None,
        ),
        _item(
            id="q2", kind="open_question",
            title="When do wage-price spirals decouple from money supply?",
            text="The conditions under which wage price spirals become "
                 "self-sustaining without monetary expansion remain open.",
            occurred_at=_ago(20), confidence=None, methodology=None,
        ),
    ]


@pytest.fixture
def retriever() -> PublicRetriever:
    return PublicRetriever(embed=fake_embed)


# ── A. Query understanding ─────────────────────────────────────────────────

# Golden queries: the query string and the class it must land in.
_CLASSIFICATION_GOLDENS: list[tuple[str, str]] = [
    ("What does the firm think about inflation?", "factual-claim"),
    ("Is land value capture effective?", "factual-claim"),
    ("the firm's position on monetary policy", "factual-claim"),
    ("How did you derive the inflation conclusion?", "methodology-question"),
    ("What methodology produced this conclusion?", "methodology-question"),
    ("How do you know land value capture works?", "methodology-question"),
    ("Will inflation fall by 2027?", "prediction-request"),
    ("What will happen if rates stay high?", "prediction-request"),
    ("forecast for monetary policy", "prediction-request"),
    ("What's the strongest argument against land value capture?",
     "counter-argument-request"),
    ("Steelman the case against inflation being monetary.",
     "counter-argument-request"),
    ("Why might the land value capture conclusion be wrong?",
     "counter-argument-request"),
    ("land value capture", "browse"),
    ("monetary inflation", "browse"),
]


def test_classification_accuracy_on_golden_queries():
    wrong = [
        (q, expected, classify_query(q).query_class)
        for q, expected in _CLASSIFICATION_GOLDENS
        if classify_query(q).query_class != expected
    ]
    assert not wrong, f"misclassified golden queries: {wrong}"


def test_every_golden_class_is_exercised():
    # The golden set covers all five classes — a regression that drops
    # a class entirely should fail loudly.
    covered = {expected for _, expected in _CLASSIFICATION_GOLDENS}
    assert covered == set(QUERY_CLASSES)


def test_confident_rule_verdict_does_not_consult_the_judge():
    judge_calls: list[str] = []

    def judge(q, candidates):
        judge_calls.append(q)
        return candidates[0]

    out = classify_query("How did you derive this conclusion?", judge=judge)
    assert out.query_class == "methodology-question"
    assert out.method == "rule"
    assert judge_calls == [], "confident rule verdict must not call the judge"


def test_judge_breaks_a_genuine_tie_among_candidates():
    # No class-specific signal fires and the query is not a bare topic,
    # so the rule layer is ambiguous and defers to the judge.
    ambiguous = "tell me about the housing situation overall right now"
    rule_only = classify_query(ambiguous)
    assert rule_only.query_class == "browse"
    assert rule_only.confidence < 0.55

    def judge(q, candidates):
        assert "factual-claim" in candidates
        return "factual-claim"

    judged = classify_query(ambiguous, judge=judge)
    assert judged.query_class == "factual-claim"
    assert judged.method == "judge"


def test_judge_cannot_invent_a_class_outside_the_candidate_set():
    def rogue_judge(q, candidates):
        return "not-a-real-class"

    out = classify_query(
        "tell me about the housing situation overall right now",
        judge=rogue_judge,
    )
    # Rogue verdict is rejected; the rule result stands.
    assert out.query_class in QUERY_CLASSES
    assert out.method == "rule"


def test_each_class_routes_to_its_own_profile(retriever, corpus):
    # A methodology question puts articles + open questions ahead of
    # conclusions; a factual claim leads with conclusions.
    method_out = retriever.retrieve(
        "How did you derive the land value capture conclusion?", corpus,
    )
    assert method_out.query_class == "methodology-question"
    assert method_out.render_hint == "methodology"
    assert retrieval_profile(method_out.query_class).kind_order[0] == "article"

    claim_out = retriever.retrieve(
        "What does the firm think about land value capture?", corpus,
    )
    assert claim_out.query_class == "factual-claim"
    assert retrieval_profile(claim_out.query_class).kind_order[0] == "conclusion"


# ── B. Diverse retrieval (MMR) ─────────────────────────────────────────────


def _near_duplicate_cluster() -> list[PublicCorpusItem]:
    """Four near-paraphrase conclusions + one distinct-but-relevant one."""
    base = _TOPIC_VECS["land"]
    perp = _unit(999)
    perp = perp - float(np.dot(perp, base)) * base
    perp = perp / float(np.linalg.norm(perp))

    cluster = []
    for i in range(4):
        # Tiny perturbations: mutual cosine ≈ 0.99 — true paraphrases.
        emb = base + 0.04 * (i + 1) * perp
        emb = emb / float(np.linalg.norm(emb))
        cluster.append(
            PublicCorpusItem(
                id=f"dup{i}", kind="conclusion",
                title=f"Land value capture paraphrase {i}",
                text="Land value capture funds transit infrastructure.",
                href=f"/c/dup{i}", confidence=0.7, methodology="x",
                embedding=emb,
            )
        )
    # Distinct conclusion: still land-topic relevant, but a real angle
    # apart from the paraphrase cluster.
    distinct_emb = 0.7 * base + 0.71 * perp
    distinct_emb = distinct_emb / float(np.linalg.norm(distinct_emb))
    cluster.append(
        PublicCorpusItem(
            id="distinct", kind="conclusion",
            title="Land value capture distorts adjacent rents",
            text="Land value capture can distort adjacent property rents.",
            href="/c/distinct", confidence=0.7, methodology="x",
            embedding=distinct_emb,
        )
    )
    return cluster


def _avg_pairwise_cosine(items: list[PublicCorpusItem]) -> float:
    embs = [it.embedding for it in items]
    pairs = [
        cosine(embs[i], embs[j])
        for i in range(len(embs))
        for j in range(i + 1, len(embs))
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0


def test_mmr_low_lambda_returns_a_less_redundant_set():
    cluster = _near_duplicate_cluster()
    query_emb = _TOPIC_VECS["land"]
    candidates = [
        _Candidate(item=it, relevance=cosine(query_emb, it.embedding),
                   embedding=it.embedding)
        for it in cluster
    ]

    relevance_only = mmr_select(candidates, lambda_=1.0, k=3)
    diverse = mmr_select(candidates, lambda_=0.3, k=3)

    rel_items = [c.item for c in relevance_only]
    div_items = [c.item for c in diverse]

    # Pure relevance pulls the paraphrase cluster; diversity must break it.
    assert all(it.id.startswith("dup") for it in rel_items)
    assert any(it.id == "distinct" for it in div_items), (
        "low-λ MMR should reach past the paraphrase cluster"
    )
    assert _avg_pairwise_cosine(div_items) < _avg_pairwise_cosine(rel_items)


def test_mmr_first_pick_is_always_the_most_relevant_item():
    cluster = _near_duplicate_cluster()
    query_emb = _TOPIC_VECS["land"]
    candidates = [
        _Candidate(item=it, relevance=cosine(query_emb, it.embedding),
                   embedding=it.embedding)
        for it in cluster
    ]
    top_relevance = max(candidates, key=lambda c: c.relevance)
    for lam in (0.0, 0.3, 0.7, 1.0):
        picked = mmr_select(candidates, lambda_=lam, k=3)
        assert picked[0].item.id == top_relevance.item.id


def test_retrieve_diversifies_a_paraphrase_heavy_rail():
    cluster = _near_duplicate_cluster()
    retr = PublicRetriever(embed=fake_embed)
    out = retr.retrieve(
        "land value capture", cluster, top_per_kind=3, mmr_lambda=0.3,
    )
    ids = [r.item.id for r in out.by_kind["conclusion"]]
    assert "distinct" in ids, (
        "the diversified rail must not be three paraphrases of one conclusion"
    )


# ── C. Honest empty result ─────────────────────────────────────────────────


def test_no_result_enrichment_surfaces_both_pointers(retriever, corpus):
    out = retriever.retrieve("favorite octopus aquarium feeding schedule", corpus)
    assert out.no_result is True
    # The page is a pointer, not a wall: closest open question AND
    # closest related conclusion are both attached for the enriched
    # no-result panel (which also hosts the research-suggestion form).
    assert out.closest_open_question is not None
    assert out.closest_open_question.item.kind == "open_question"
    assert out.closest_related_conclusion is not None
    assert out.closest_related_conclusion.item.kind == "conclusion"


def test_clear_hit_does_not_flip_no_result(retriever, corpus):
    out = retriever.retrieve("inflation monetary money supply", corpus)
    assert out.no_result is False
    assert out.by_kind["conclusion"][0].item.id == "c1"
    assert out.by_kind["conclusion"][0].score >= NO_RESULT_THRESHOLD


# ── D. Result freshness ────────────────────────────────────────────────────


def test_freshness_flag_tracks_item_age():
    recent = _item(id="r", kind="conclusion", title="t", text="x",
                   occurred_at=_ago(30))
    stale = _item(id="s", kind="conclusion", title="t", text="x",
                  occurred_at=_ago(900))
    assert compute_freshness(recent, NOW) is True
    assert compute_freshness(stale, NOW) is False


def test_explicit_still_current_flag_overrides_age():
    # Recent by date, but the firm has explicitly retired it.
    retired = _item(id="x", kind="conclusion", title="t", text="x",
                    occurred_at=_ago(5), still_current=False)
    assert compute_freshness(retired, NOW) is False
    # Old by date, but the firm has affirmatively re-endorsed it.
    reaffirmed = _item(id="y", kind="conclusion", title="t", text="x",
                       occurred_at=_ago(900), still_current=True)
    assert compute_freshness(reaffirmed, NOW) is True


def test_stale_results_are_carried_not_dropped(retriever, corpus):
    # c2 (land value capture) is 900 days old. A land query must still
    # return it — staleness is shown, never used to silently de-rank.
    out = retriever.retrieve("land value capture transit", corpus)
    land = next(r for r in out.by_kind["conclusion"] if r.item.id == "c2")
    assert land.is_current is False
    assert land.occurred_at is not None


def test_unknown_date_is_treated_as_current_not_stale():
    no_date = _item(id="n", kind="conclusion", title="t", text="x")
    # We never fabricate a stale signal we cannot back with a date.
    assert compute_freshness(no_date, NOW) is True


# ── E. Query-log discipline ────────────────────────────────────────────────


def test_prune_drops_raw_query_past_the_24h_ttl():
    entries = [
        make_query_log_entry("recent question", "factual-claim",
                             now=_ago(0.5)),                  # 12h old — keep
        make_query_log_entry("old question", "browse",
                             now=_ago(2)),                    # 48h old — drop raw
        make_query_log_entry("right on the edge", "prediction-request",
                             now=NOW - timedelta(hours=RAW_QUERY_TTL_HOURS + 1)),
    ]
    pruned, dropped = prune_query_log(entries, now=NOW)

    assert dropped == 2
    by_class = {e.query_class: e for e in pruned}
    # Fresh entry keeps its raw string.
    assert by_class["factual-claim"].raw_query == "recent question"
    # Aged entries lose the raw string but keep bucket + class forever.
    assert by_class["browse"].raw_query is None
    assert by_class["browse"].bucket  # hashed bucket id survives
    assert by_class["prediction-request"].raw_query is None
    assert by_class["prediction-request"].query_class == "prediction-request"


def test_prune_is_idempotent():
    entries = [make_query_log_entry("old", "browse", now=_ago(3))]
    once, d1 = prune_query_log(entries, now=NOW)
    twice, d2 = prune_query_log(once, now=NOW)
    assert d1 == 1 and d2 == 0
    assert twice[0].raw_query is None
    assert twice[0].bucket == entries[0].bucket


def test_retain_raw_false_never_writes_the_raw_string():
    # Staging/production surfaces that do not need same-day raw
    # inspection take the strongest form of the policy: raw is never
    # written at all.
    entry = make_query_log_entry("sensitive query", "browse",
                                 now=NOW, retain_raw=False)
    assert entry.raw_query is None
    assert entry.bucket and entry.query_class == "browse"


def test_bucket_is_stable_and_does_not_leak_the_query():
    a = make_query_log_entry("Why is the sky blue?", "factual-claim", now=NOW)
    b = make_query_log_entry("why is the sky blue?  ", "factual-claim", now=NOW)
    assert a.bucket == b.bucket  # normalised: case + whitespace
    assert len(a.bucket) == 12
    assert "sky" not in a.bucket
