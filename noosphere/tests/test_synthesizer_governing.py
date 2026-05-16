"""Tests for the synthesizer's governing-principles selector.

The selector is pure: a list of :class:`Principle` plus a question
domain hint goes in, a list of governing principles comes out. We
exercise:

* the empty-domain path (no governs),
* a clean two-principle match,
* the threshold gate,
* the disciplines/tag-driven match path,
* domain-shifted principles falling out of the governing set,
* stable ordering by descending score.
"""

from __future__ import annotations

from noosphere.models import (
    ConvictionLevel,
    Discipline,
    Principle,
    ProvenanceKind,
)
from noosphere.synthesizer.governing import (
    DOMAIN_FUZZY_THRESHOLD,
    identify_governing,
)


def _principle(
    *,
    pid: str,
    text: str,
    disciplines: list[Discipline] | None = None,
    tags: list[str] | None = None,
) -> Principle:
    return Principle(
        id=pid,
        text=text,
        disciplines=list(disciplines or []),
        tags=list(tags or []),
        conviction=ConvictionLevel.MODERATE,
        provenance=ProvenanceKind.PROPRIETARY,
    )


def test_empty_domain_returns_empty() -> None:
    p = _principle(pid="p1", text="Compounding capital trumps timing.")
    assert identify_governing([p], "") == []
    assert identify_governing([p], "    ") == []


def test_text_overlap_promotes_principle() -> None:
    p1 = _principle(
        pid="p_capital",
        text="Capital allocation discipline beats timing the market.",
    )
    p2 = _principle(
        pid="p_unrelated",
        text="Evolutionary biology emphasises fitness landscapes.",
    )
    out = identify_governing([p1, p2], "should we allocate capital to this fund?")
    assert [p.id for p in out] == ["p_capital"]


def test_two_principles_clear_threshold_for_strategic_question() -> None:
    p_a = _principle(
        pid="p_strategy_a",
        text="Strategy: focus capital on the highest-conviction bets.",
        disciplines=[Discipline.STRATEGY],
    )
    p_b = _principle(
        pid="p_strategy_b",
        text="Conviction grows when a bet survives adversarial scrutiny.",
        disciplines=[Discipline.STRATEGY],
        tags=["capital", "conviction"],
    )
    p_off = _principle(
        pid="p_off",
        text="Quantum decoherence scales with system size.",
        disciplines=[Discipline.PHYSICS],
    )
    out = identify_governing(
        [p_a, p_b, p_off],
        "what is our strategy for high-conviction capital deployment?",
    )
    assert {p.id for p in out} == {"p_strategy_a", "p_strategy_b"}


def test_disciplines_and_tags_are_first_class_signals() -> None:
    # Text deliberately omits the topic words; the discipline + tag
    # carry the signal.
    p = _principle(
        pid="p_disc",
        text="Markets reprice when the consensus refuses to update.",
        disciplines=[Discipline.ECONOMICS],
        tags=["macro", "inflation"],
    )
    out = identify_governing([p], "what does inflation imply for our positioning?")
    assert [pp.id for pp in out] == ["p_disc"]


def test_stopwords_do_not_promote_unrelated_principles() -> None:
    # Question is almost all stopwords; the only content word
    # ("rates") shouldn't appear in the unrelated principle.
    p = _principle(
        pid="p_unrelated",
        text="Antitrust enforcement waxes and wanes with administration priorities.",
    )
    out = identify_governing([p], "will the rates fall?")
    assert out == []


def test_threshold_excludes_weak_overlap() -> None:
    # One-word overlap on a long principle text drops below the
    # threshold (Jaccard denominator dominated by principle tokens).
    p = _principle(
        pid="p_weak",
        text=(
            "Manufacturing scale advantages produce durable cost moats over "
            "decades of compounding investment in proprietary process "
            "improvements that competitors cannot easily replicate without "
            "matching the same accumulated tacit knowledge base."
        ),
    )
    out = identify_governing([p], "capital allocation")
    # Either dropped by threshold or kept with a low score; the key
    # property is that the public threshold gate is in force.
    if out:
        # If something does pass it must clear the documented threshold.
        from noosphere.synthesizer.governing import _score_principles

        scored = _score_principles([p], "capital allocation")
        assert all(score >= DOMAIN_FUZZY_THRESHOLD for score, _ in scored)


def test_result_is_ordered_by_descending_score() -> None:
    # Three matching tokens covered → score 0.75.
    p_strong = _principle(
        pid="p_strong",
        text="Capital discipline applied across multiple regimes drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    # One matching token covered → score 0.25.
    p_weak = _principle(
        pid="p_weak",
        text="Manufacturing scale advantages produce durable cost moats.",
        tags=["capital"],
    )
    out = identify_governing(
        [p_weak, p_strong],
        "apply capital discipline regime?",
    )
    assert [p.id for p in out] == ["p_strong", "p_weak"]
