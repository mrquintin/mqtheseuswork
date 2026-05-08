"""Goldens + ranking-stability tests for `public_retrieval`.

Three things we pin:

  1. Synthetic-corpus rankings — given a small fixed corpus, the
     expected item is on top for each canonical query.
  2. Stability under small perturbation — re-asking with a synonym or
     punctuation swap does not reorder the top result.
  3. The no-result fallback fires below the threshold and the
     borderline band surfaces rephrasings.

The fake embedder is a deterministic bag-of-words projection: each
unique token gets a stable random vector, the document/query embedding
is the L2-normalised sum. This is enough to give "plus epsilon" cosine
shifts under perturbation while still keeping clearly-related-versus-
clearly-unrelated documents far apart — exactly what the threshold
logic needs to be exercised against.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from noosphere.inference.public_retrieval import (
    BORDERLINE_LOWER,
    BORDERLINE_UPPER,
    NO_RESULT_THRESHOLD,
    PublicCorpusItem,
    PublicRetriever,
    cosine,
    extract_snippet,
    hash_query_bucket,
)


# ── Fake embedder ──────────────────────────────────────────────────────────
#
# We deliberately model SBERT-like behaviour rather than literal bag of
# words: related sentences cluster (cosine ≈ 0.6–0.9), unrelated
# sentences sit near zero (cosine ≈ 0.0–0.15). Every token is mapped to
# one of a small set of topic vectors plus a tiny per-token noise
# component so identical-topic sentences get high but not unit cosine.


_TOKEN = re.compile(r"[a-z0-9]+")
_DIM = 256

# Topic vocabularies. A token in any of these contributes its topic
# vector to the embedding; tokens absent from all topics fall through to
# the per-token noise channel.
_TOPICS: dict[str, set[str]] = {
    "inflation": {
        "inflation", "monetary", "money", "supply", "wage", "wages",
        "price", "prices", "spiral", "spirals", "fed", "rates", "rate",
        "hawkish", "dovish", "transmission",
    },
    "land": {
        "land", "value", "capture", "transit", "density", "city",
        "cities", "metro", "metros", "station", "stations",
        "infrastructure", "property", "tax",
    },
    "conviction": {
        "conviction", "belief", "beliefs", "geometry", "direction",
        "scalar", "analyst", "analysts", "mind",
    },
}


def _topic_vec(name: str, idx: int) -> np.ndarray:
    rng = np.random.default_rng(0xC0DE_0000 + idx)
    v = rng.standard_normal(_DIM)
    return v / float(np.linalg.norm(v))


_TOPIC_VECS = {name: _topic_vec(name, i) for i, name in enumerate(_TOPICS)}


def _noise_vec(token: str) -> np.ndarray:
    rng = np.random.default_rng(int.from_bytes(
        token.encode("utf-8")[:8].ljust(8, b"\0"), "big",
    ))
    v = 0.05 * rng.standard_normal(_DIM)  # small — unrelated tokens stay near zero
    return v


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def fake_embed(text: str) -> np.ndarray:
    toks = _tokens(text)
    if not toks:
        return np.zeros(_DIM)
    v = np.zeros(_DIM)
    matched = 0
    for t in toks:
        for topic_name, vocab in _TOPICS.items():
            if t in vocab:
                v = v + _TOPIC_VECS[topic_name]
                matched += 1
                break
        else:
            v = v + _noise_vec(t)
    n = float(np.linalg.norm(v))
    if n < 1e-10:
        return v
    return v / n


# ── Corpus ─────────────────────────────────────────────────────────────────


def _item(
    *, id: str, kind: str, title: str, text: str,
    confidence: float | None = 0.7, methodology: str | None = "six_layer_coherence",
    is_public: bool = True,
) -> PublicCorpusItem:
    return PublicCorpusItem(
        id=id,
        kind=kind,
        title=title,
        text=text,
        href=f"/{kind}/{id}",
        confidence=confidence,
        methodology=methodology,
        is_public=is_public,
        embedding=fake_embed(text),
    )


@pytest.fixture
def corpus() -> list[PublicCorpusItem]:
    return [
        _item(
            id="c1",
            kind="conclusion",
            title="Inflation is a monetary phenomenon",
            text=(
                "Inflation in the long run is a monetary phenomenon driven by "
                "money supply growth outpacing real output. Wage-price spirals "
                "are a transmission mechanism, not the source."
            ),
        ),
        _item(
            id="c2",
            kind="conclusion",
            title="Land value capture funds infrastructure",
            text=(
                "Capturing land value uplift around new transit pays for the "
                "transit itself. Property tax base expansion follows station "
                "openings within five years."
            ),
        ),
        _item(
            id="o1",
            kind="opinion",
            title="On the Fed's hawkish pivot",
            text=(
                "A hawkish Fed pivot raises real rates and tightens monetary "
                "conditions; equity duration shortens and growth multiples "
                "compress."
            ),
            confidence=0.55,
        ),
        _item(
            id="a1",
            kind="article",
            title="The geometry of conviction",
            text=(
                "Conviction is not a scalar; it is a direction in belief space. "
                "Two analysts with the same numerical confidence may disagree "
                "about what would change their mind."
            ),
            confidence=0.8,
        ),
        _item(
            id="q1",
            kind="open_question",
            title="Does land value capture work in low-density cities?",
            text=(
                "The firm's land value capture conclusion was derived from "
                "transit-rich metros. Whether the mechanism still pays for "
                "infrastructure in low-density cities is unresolved."
            ),
            confidence=None,
            methodology=None,
        ),
        _item(
            id="q2",
            kind="open_question",
            title="When do wage-price spirals decouple from money supply?",
            text=(
                "Standard theory says wage-price spirals are transmission, not "
                "source. The conditions under which they become self-sustaining "
                "in the absence of monetary expansion remain open."
            ),
            confidence=None,
            methodology=None,
        ),
        _item(
            id="priv1",
            kind="conclusion",
            title="Private founder draft on inflation",
            text=(
                "Inflation drafts kept inside the founder workspace must never "
                "leak to the public surface."
            ),
            is_public=False,
        ),
    ]


@pytest.fixture
def retriever() -> PublicRetriever:
    return PublicRetriever(embed=fake_embed)


# ── Goldens ────────────────────────────────────────────────────────────────


def test_inflation_query_ranks_inflation_conclusion_first(retriever, corpus):
    out = retriever.retrieve("What does the firm think about inflation?", corpus)

    top_conclusions = out.by_kind["conclusion"]
    assert top_conclusions, "expected at least one conclusion result"
    assert top_conclusions[0].item.id == "c1"
    assert not out.no_result
    assert top_conclusions[0].score >= NO_RESULT_THRESHOLD


def test_land_value_query_ranks_land_conclusion_first(retriever, corpus):
    out = retriever.retrieve("How does land value capture pay for transit?", corpus)
    top = out.by_kind["conclusion"][0]
    assert top.item.id == "c2"
    assert top.snippet  # extractive snippet is set


def test_open_questions_surface_matching_topic(retriever, corpus):
    out = retriever.retrieve("low-density city transit funding mechanism", corpus)
    oq_ids = [r.item.id for r in out.by_kind["open_question"]]
    assert "q1" in oq_ids
    assert oq_ids[0] == "q1"


def test_closest_open_question_is_present_even_when_top_is_a_conclusion(
    retriever, corpus,
):
    out = retriever.retrieve("inflation wage price spiral", corpus)
    assert out.closest_open_question is not None
    assert out.closest_open_question.item.kind == "open_question"
    # q2 is the matching open question for this query.
    assert out.closest_open_question.item.id == "q2"


# ── Visibility ─────────────────────────────────────────────────────────────


def test_private_items_never_appear(retriever, corpus):
    out = retriever.retrieve("inflation", corpus)
    all_ids = [r.item.id for items in out.by_kind.values() for r in items]
    assert "priv1" not in all_ids


# ── Ranking stability under small query perturbations ──────────────────────


@pytest.mark.parametrize(
    "perturbation",
    [
        "What does the firm think about inflation?",
        "what does the firm think about inflation",  # case + trailing punct
        "What does the firm think about inflation??",  # double punct
        "What does the firm think about inflation in the long run?",  # extra clause
    ],
)
def test_ranking_stable_under_perturbation(retriever, corpus, perturbation):
    out = retriever.retrieve(perturbation, corpus)
    assert out.by_kind["conclusion"][0].item.id == "c1"


# ── No-result fallback ────────────────────────────────────────────────────


def test_no_result_fires_for_far_off_topic_query(retriever, corpus):
    # Query is intentionally disjoint from the synthetic corpus tokens.
    out = retriever.retrieve("favorite octopus aquarium feeding schedule", corpus)
    assert out.no_result is True
    # Closest open question is still surfaced for the fallback UI.
    assert out.closest_open_question is not None


def test_no_result_does_not_fire_for_clear_hit(retriever, corpus):
    out = retriever.retrieve("inflation monetary phenomenon money supply", corpus)
    assert out.no_result is False


def test_borderline_band_yields_rephrasing_suggestions():
    # Tight construct: top score sits in [BORDERLINE_LOWER, BORDERLINE_UPPER).
    # We force it by making the top item only partially overlap with the
    # query and ensuring there are nearby alternatives.
    corpus = [
        PublicCorpusItem(
            id="t1", kind="conclusion", title="Topic alpha",
            text="alpha beta gamma", href="/t1",
            confidence=0.5, methodology="x",
            embedding=np.array([1.0, 0.0, 0.0] + [0.0] * 61),
        ),
        PublicCorpusItem(
            id="t2", kind="conclusion", title="Topic alpha refined",
            text="alpha beta", href="/t2",
            confidence=0.5, methodology="x",
            embedding=np.array([0.95, 0.05, 0.0] + [0.0] * 61),
        ),
        PublicCorpusItem(
            id="t3", kind="conclusion", title="Topic alpha extended",
            text="alpha gamma", href="/t3",
            confidence=0.5, methodology="x",
            embedding=np.array([0.9, 0.0, 0.1] + [0.0] * 61),
        ),
    ]
    # Build a query embedding whose cosine to t1 lands in the borderline band.
    target = (BORDERLINE_LOWER + BORDERLINE_UPPER) / 2.0
    base = np.array([1.0, 0.0, 0.0] + [0.0] * 61)
    perp = np.zeros(64)
    perp[10] = 1.0
    q_vec = target * base + math_sqrt(1 - target ** 2) * perp

    def embed(text: str) -> np.ndarray:
        if text == "QUERY":
            return q_vec
        # Map item.text strings back to their embeddings via prefix.
        for item in corpus:
            if text == item.text:
                assert item.embedding is not None
                return item.embedding
        # Fallback for snippet sentence reads: return zero so cosine=0.
        return np.zeros(64)

    retriever = PublicRetriever(embed=embed)
    out = retriever.retrieve("QUERY", corpus)
    assert BORDERLINE_LOWER <= out.by_kind["conclusion"][0].score < BORDERLINE_UPPER
    assert out.suggested_rephrasings, "borderline band should surface rephrasings"


def math_sqrt(x: float) -> float:
    import math

    return math.sqrt(max(0.0, x))


# ── Snippet extraction is extractive ──────────────────────────────────────


def test_snippet_returns_substring_of_source(retriever):
    text = (
        "First sentence is a distractor. Second sentence directly answers "
        "the inflation question with monetary supply mechanics. Third "
        "sentence is unrelated."
    )
    snippet = extract_snippet(text, "inflation monetary supply", embed=fake_embed)
    # Extractive: every word of the snippet appears in the source.
    for word in re.findall(r"[A-Za-z]+", snippet):
        assert word in text, f"{word!r} not in source — snippet must be extractive"


def test_snippet_truncates_long_text():
    text = "alpha beta gamma. " * 200
    snippet = extract_snippet(text, "alpha", embed=fake_embed, max_chars=120)
    assert len(snippet) <= 121  # +1 for the ellipsis character


# ── Cosine sanity ──────────────────────────────────────────────────────────


def test_cosine_zero_vector_safe():
    assert cosine(np.zeros(8), np.ones(8)) == 0.0
    assert cosine(np.ones(8), np.zeros(8)) == 0.0


# ── Logging bucket is one-way ──────────────────────────────────────────────


def test_hash_query_bucket_is_stable_and_short():
    a = hash_query_bucket("Why is the sky blue?")
    b = hash_query_bucket("why is the sky blue?")  # case-only diff
    c = hash_query_bucket("Why is the sky blue?  ")  # trailing whitespace
    assert a == b == c
    assert len(a) == 12
    assert all(ch in "0123456789abcdef" for ch in a)


def test_hash_query_bucket_changes_with_content():
    a = hash_query_bucket("Why is the sky blue?")
    b = hash_query_bucket("Why is the sky red?")
    assert a != b
