"""Governing-principles selection.

Pure function over a list of retrieved principles. A principle
*governs* a question when its declared scope or disciplines fuzzy-match
the question's domain hint. The synthesizer requires at least two
governing principles before it will try to construct a reasoning chain;
fewer governs → ABSTAIN.

This module is intentionally dependency-light so tests can exercise
the selection without spinning the LLM or the store.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from noosphere.models import Principle


# Tunables ---------------------------------------------------------------

#: Below this question-coverage fraction, the principle is *not*
#: considered to govern the question. Coverage = intersection over
#: question tokens; one shared topic keyword on a typical 4–8 token
#: question clears the threshold, but a principle that shares only
#: stopwords or one weak token does not.
DOMAIN_FUZZY_THRESHOLD: float = 0.15

#: Words that are stripped from a domain hint before scoring. The
#: question's domain is operator-typed prose — articles and connectives
#: would otherwise inflate the Jaccard denominator and make every
#: principle match the empty topic.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "their",
        "they",
        "this",
        "to",
        "we",
        "what",
        "when",
        "which",
        "will",
        "with",
        "would",
    }
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")


def _tokens(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    return {
        tok.lower()
        for tok in _WORD_RE.findall(text)
        if tok.lower() not in _STOPWORDS and len(tok) > 2
    }


def _principle_domain_tokens(principle: Principle) -> set[str]:
    """Tokens that describe the principle's domain of applicability.

    A :class:`Principle` does not carry a free-form
    ``domain_of_applicability`` field — its surface area lives in
    ``disciplines``, ``tags``, and the principle ``text`` itself. We
    union those into a single token set so a question whose domain
    overlaps any of them counts as covered.
    """

    tokens: set[str] = set()
    for disc in principle.disciplines or []:
        # Discipline enum carries human-readable values like "Political
        # Philosophy" — split on whitespace so the question word
        # "philosophy" matches without needing the exact phrase.
        value = getattr(disc, "value", str(disc))
        tokens |= _tokens(value)
    for tag in principle.tags or []:
        tokens |= _tokens(tag)
    tokens |= _tokens(principle.text)
    return tokens


def _coverage(question_tokens: set[str], principle_tokens: set[str]) -> float:
    """How much of the *question* the principle's domain covers.

    Asymmetric on purpose: a principle text of any length should not
    be penalised for being thorough. The question is the anchor.
    """

    if not question_tokens or not principle_tokens:
        return 0.0
    overlap = question_tokens & principle_tokens
    if not overlap:
        return 0.0
    return len(overlap) / len(question_tokens)


def identify_governing(
    principles: Iterable[Principle],
    question_domain: str,
    *,
    threshold: float = DOMAIN_FUZZY_THRESHOLD,
) -> list[Principle]:
    """Return principles whose domain fuzzy-matches the question.

    ``question_domain`` is the operator's domain hint (or the question
    text itself when no separate hint was provided). Principles are
    scored by Jaccard overlap between their domain tokens and the
    question's tokens, and any principle scoring at or above
    ``threshold`` is returned. The result is sorted by descending score
    so the strongest fit is first — the engine uses the head of the
    list when it needs a stable ordering.

    Returns an empty list when ``question_domain`` is empty or no
    principle clears the threshold. The engine treats an empty result
    as ``ABSTAINED_NO_PRINCIPLES``.
    """

    question_tokens = _tokens(question_domain)
    if not question_tokens:
        return []

    scored: list[tuple[float, Principle]] = []
    for principle in principles:
        domain = _principle_domain_tokens(principle)
        score = _coverage(question_tokens, domain)
        if score >= threshold:
            scored.append((score, principle))

    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [p for _, p in scored]


__all__ = [
    "DOMAIN_FUZZY_THRESHOLD",
    "identify_governing",
]


# Re-exported helpers for tests that want to assert the underlying
# tokenisation. Not part of the documented public API.
def _question_tokens(text: Optional[str]) -> set[str]:  # pragma: no cover
    return _tokens(text)


def _principle_tokens(principle: Principle) -> set[str]:  # pragma: no cover
    return _principle_domain_tokens(principle)


def _score_principles(
    principles: Sequence[Principle], question_domain: str
) -> list[tuple[float, Principle]]:  # pragma: no cover - debug helper
    question_tokens = _tokens(question_domain)
    out: list[tuple[float, Principle]] = []
    for principle in principles:
        out.append(
            (
                _coverage(question_tokens, _principle_domain_tokens(principle)),
                principle,
            )
        )
    return out
