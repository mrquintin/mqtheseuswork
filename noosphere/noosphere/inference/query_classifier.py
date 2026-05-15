"""Query understanding for the public inquiry box.

First-version public retrieval ranked everything by raw embedding
similarity. That surfaces near-duplicate snippets and treats every
question the same — but a reader asking *"how did you derive this?"*
wants a methodology trail, a reader asking *"will rates fall in 2026?"*
wants the firm's dated takes, and a reader asking *"what's the strongest
case against this?"* wants the open contradictions, not five
paraphrases of the conclusion they're already doubting.

This module classifies each query into one of five classes and hands
back a :class:`RetrievalProfile` describing how that class should be
retrieved and rendered. The companion module
``noosphere/inference/public_retrieval.py`` consumes the profile;
``theseus-codex/src/lib/publicAsk.ts`` mirrors the rule layer for the
live Next.js path.

Routing is **rule-based + a light LLM judge**:

  * The rule layer is a set of regex signals per class. It is cheap,
    deterministic, and pinned by goldens — it carries the common cases
    on its own.
  * When the rule layer is *ambiguous* (low confidence, or a tie), an
    optional ``judge`` callable is consulted. In production this is a
    one-token LLM classification call; in tests it is a deterministic
    fake. The judge only ever picks among the rule layer's own
    candidate classes — it never invents a class and never rewrites the
    query. There is no freeform generation on this surface.

The module is dependency-light by design: standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence, Tuple


# ── Query classes ──────────────────────────────────────────────────────────

QUERY_CLASSES: Tuple[str, ...] = (
    "factual-claim",
    "methodology-question",
    "prediction-request",
    "counter-argument-request",
    "browse",
)

#: Class used when nothing else fits — a bare topic the reader wants to
#: skim. It is also the neutral profile: its retrieval path is the
#: original relevance-ordered behaviour.
DEFAULT_CLASS = "browse"

#: Below this rule confidence the classification is treated as
#: ambiguous and the LLM judge (if wired) is consulted.
JUDGE_THRESHOLD = 0.55


# ── Result shape ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Classification:
    """The outcome of classifying a single query.

    ``method`` records how the class was decided — ``"rule"`` when the
    regex layer was confident, ``"judge"`` when the LLM judge broke a
    tie. ``signals`` lists the named rules that fired, which keeps the
    decision auditable (and lets the goldens assert on *why* a query
    landed where it did, not just where).
    """

    query_class: str
    confidence: float
    method: str
    signals: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.query_class not in QUERY_CLASSES:
            raise ValueError(
                f"unknown query class {self.query_class!r}; "
                f"expected one of {QUERY_CLASSES}"
            )


#: A judge receives the raw query and the rule layer's ranked candidate
#: classes; it returns one of those classes, or None to defer to the
#: rule result. It must not return a class outside the candidate list.
JudgeFn = Callable[[str, Sequence[str]], Optional[str]]


# ── Rule layer ─────────────────────────────────────────────────────────────
#
# Each class owns a list of (signal_name, compiled_pattern, weight).
# The rule layer sums the weights of every pattern that fires; the
# highest-scoring class wins. Weights let a decisive phrase ("steelman")
# outvote a weak co-occurrence ("why").

_Rule = Tuple[str, "re.Pattern[str]", float]


def _r(name: str, pattern: str, weight: float = 1.0) -> _Rule:
    return (name, re.compile(pattern, re.IGNORECASE), weight)


_RULES: dict[str, list[_Rule]] = {
    "methodology-question": [
        _r("how-do-you", r"\bhow (do|did|does|was|were|are) (you|the firm|theseus|this|it|they)\b", 1.4),
        _r("methodology-word", r"\bmethodolog", 1.6),
        _r("derive", r"\bhow .{0,40}\b(derive[ds]?|determine[ds]?|conclude[ds]?|reach(ed)?|arrive[ds]?|comput)", 1.5),
        _r("process", r"\bwhat(?:'s| is| are)? (?:your|the firm'?s?) (process|method|approach|reasoning|criteria)\b", 1.5),
        _r("how-know", r"\bhow (do|did) (you|the firm) know\b", 1.4),
        _r("firm-method-terms", r"\b(six.?layer|coherence layer|provenance|audit trail|show your work)\b", 1.3),
        _r("on-what-basis", r"\b(on what basis|what evidence|what makes you (so )?(sure|confident))\b", 1.2),
    ],
    "prediction-request": [
        _r("will", r"\bwill\b(?!.*\bnot addressed\b)", 1.0),
        _r("forecast-word", r"\b(predict|forecast|projection|outlook|prognos)", 1.6),
        _r("going-to", r"\b(going to|expected to|likely to|on track to)\b", 1.1),
        _r("by-year", r"\bby (?:the )?(?:end of )?(?:19|20)\d\d\b", 1.5),
        _r("in-coming", r"\bin (?:the )?(?:next|coming) \d*\s*(year|month|decade|quarter)", 1.4),
        _r("what-happens-if", r"\bwhat (?:will|would) happen (?:if|when)\b", 1.3),
        _r("future-of", r"\bfuture of\b", 1.0),
    ],
    "counter-argument-request": [
        _r("counter-word", r"\bcounter.?(argument|point|case)", 1.7),
        _r("against", r"\b(argue|argument|case|evidence) against\b", 1.6),
        _r("steelman", r"\b(steel.?man|devil'?s advocate)\b", 1.8),
        _r("rebut", r"\b(rebut|refut|disprove|debunk)", 1.5),
        _r("objection", r"\bobjection", 1.3),
        _r("might-be-wrong", r"\b(why|where|how) (might|would|could|is|are) .{0,40}\b(wrong|mistaken|flawed|fail)", 1.5),
        _r("strongest-against", r"\bstrongest (argument|case|objection)\b", 1.6),
        _r("disagree", r"\b(disagree|pushback|push back|critique of|weakest)\b", 1.1),
        _r("contradict", r"\bcontradict", 1.2),
    ],
    "factual-claim": [
        _r("what-firm-thinks", r"\bwhat (?:does|do) the firm (?:think|believe|conclude|say|hold)\b", 1.6),
        _r("firm-view-on", r"\b(?:the firm'?s?|your) (view|position|conclusion|take|stance) on\b", 1.5),
        _r("is-it-true", r"\bis it true\b", 1.4),
        _r("interrogative-fact", r"^(is|are|does|do|did|has|have|was|were|can|should|which)\b.*\?$", 1.0),
        _r("what-is", r"\bwhat (?:is|are)\b", 0.8),
        _r("declarative", r"^[a-z0-9].{0,200}\b(is|are|was|were|drives?|causes?|funds?|leads? to)\b.{0,200}[^?]$", 0.7),
    ],
}


# A "bare topic" is a short noun-phrase query: no question mark, no
# obvious verb. These are browse intent ("land value capture",
# "monetary inflation") and should not be forced into another class by
# a stray weak signal.
_VERBISH = re.compile(
    r"\b(is|are|was|were|do|does|did|will|would|should|can|how|why|what|"
    r"when|where|which|who|predict|argue|think|believe)\b",
    re.IGNORECASE,
)


def _is_bare_topic(query: str) -> bool:
    q = query.strip()
    if not q or "?" in q:
        return False
    if _VERBISH.search(q):
        return False
    # Short noun phrase: a handful of words, no interrogative shape.
    return len(q.split()) <= 6


def _rule_scores(query: str) -> dict[str, Tuple[float, Tuple[str, ...]]]:
    """Score every class by summing the weights of the rules that fire."""
    out: dict[str, Tuple[float, Tuple[str, ...]]] = {}
    for cls, rules in _RULES.items():
        score = 0.0
        fired: list[str] = []
        for name, pattern, weight in rules:
            if pattern.search(query):
                score += weight
                fired.append(name)
        out[cls] = (score, tuple(fired))
    return out


def _confidence(top: float, second: float) -> float:
    """Map a rule score and its margin onto a [0, 1] confidence.

    A decisive winner (high score, clear margin) approaches 0.95; a
    weak or contested winner stays under the judge threshold so the
    judge gets consulted.
    """
    if top <= 0.0:
        return 0.0
    margin = top - second
    conf = 0.45 + 0.12 * top + 0.18 * margin
    return max(0.0, min(0.95, conf))


# ── Public API ─────────────────────────────────────────────────────────────


def classify_query(
    query: str,
    *,
    judge: Optional[JudgeFn] = None,
    judge_threshold: float = JUDGE_THRESHOLD,
) -> Classification:
    """Classify ``query`` into one of :data:`QUERY_CLASSES`.

    The rule layer runs first. If it is confident (confidence ≥
    ``judge_threshold``) its verdict stands. If it is ambiguous and a
    ``judge`` is supplied, the judge picks among the rule layer's
    candidate classes; a valid pick is taken with ``method="judge"``.
    With no judge wired, the ambiguous rule verdict stands as-is.
    """
    q = (query or "").strip()
    if not q:
        return Classification(DEFAULT_CLASS, 1.0, "rule", ("empty",))

    scores = _rule_scores(q)
    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    top_cls, (top_score, top_signals) = ranked[0]
    second_score = ranked[1][1][0] if len(ranked) > 1 else 0.0

    if top_score <= 0.0:
        # No class-specific signal fired. A bare topic is a confident
        # browse; anything else is an ambiguous browse the judge may
        # refine.
        if _is_bare_topic(q):
            return Classification(DEFAULT_CLASS, 0.8, "rule", ("bare-topic",))
        rule_result = Classification(DEFAULT_CLASS, 0.3, "rule", ("no-signal",))
        candidates: Sequence[str] = QUERY_CLASSES
    else:
        confidence = _confidence(top_score, second_score)
        rule_result = Classification(top_cls, confidence, "rule", top_signals)
        if confidence >= judge_threshold:
            return rule_result
        # Ambiguous: offer the judge the contested classes (anything
        # that scored, plus browse as the fallback).
        candidates = [cls for cls, (s, _) in ranked if s > 0.0]
        if DEFAULT_CLASS not in candidates:
            candidates = [*candidates, DEFAULT_CLASS]

    if judge is None:
        return rule_result

    verdict = judge(q, candidates)
    if verdict in QUERY_CLASSES and verdict in candidates:
        judged_signals = (*rule_result.signals, f"judge:{verdict}")
        return Classification(verdict, 0.8, "judge", judged_signals)
    return rule_result


# ── Retrieval profiles — one per class ─────────────────────────────────────
#
# The profile is the contract between query understanding and
# retrieval/rendering. It carries:
#   * kind_order   — the rail order the UI renders for this class.
#   * kind_boost   — multiplicative score boosts applied *for ordering
#                    and diversity selection only*, never to the
#                    no-result threshold (so honesty stays calibrated).
#   * mmr_lambda   — the Maximum Marginal Relevance tradeoff for this
#                    class. Higher = relevance-heavy; lower = surface a
#                    wider spread (counter-argument wants the spread).
#   * render_hint  — opaque id the UI keys its per-class layout off.


@dataclass(frozen=True)
class RetrievalProfile:
    """How a given query class should be retrieved and rendered."""

    query_class: str
    kind_order: Tuple[str, ...]
    kind_boost: dict = field(default_factory=dict)
    mmr_lambda: float = 0.7
    render_hint: str = "browse"


_PROFILES: dict[str, RetrievalProfile] = {
    "factual-claim": RetrievalProfile(
        query_class="factual-claim",
        kind_order=("conclusion", "article", "opinion", "open_question"),
        kind_boost={"conclusion": 1.5, "article": 1.15},
        # Relevance-heavy: the reader wants the firm's answer, tightly.
        mmr_lambda=0.78,
        render_hint="claim",
    ),
    "methodology-question": RetrievalProfile(
        query_class="methodology-question",
        kind_order=("article", "open_question", "conclusion", "opinion"),
        kind_boost={"article": 1.5, "open_question": 1.25, "conclusion": 1.1},
        mmr_lambda=0.62,
        render_hint="methodology",
    ),
    "prediction-request": RetrievalProfile(
        query_class="prediction-request",
        kind_order=("opinion", "conclusion", "open_question", "article"),
        kind_boost={"opinion": 1.5, "open_question": 1.15},
        # Surface a spread of dated takes rather than one repeated call.
        mmr_lambda=0.58,
        render_hint="prediction",
    ),
    "counter-argument-request": RetrievalProfile(
        query_class="counter-argument-request",
        kind_order=("open_question", "opinion", "conclusion", "article"),
        kind_boost={"open_question": 1.6, "opinion": 1.2},
        # Diversity-heavy: we want the disagreements and unresolved
        # contradictions, not five echoes of the conclusion.
        mmr_lambda=0.4,
        render_hint="counter",
    ),
    "browse": RetrievalProfile(
        query_class="browse",
        kind_order=("conclusion", "article", "opinion", "open_question"),
        # Neutral boosts — browse keeps the original relevance ordering
        # so the established retrieval goldens stay stable.
        kind_boost={},
        mmr_lambda=0.7,
        render_hint="browse",
    ),
}


def retrieval_profile(query_class: Optional[str]) -> RetrievalProfile:
    """Return the :class:`RetrievalProfile` for a class.

    ``None`` or an unknown class falls back to the neutral browse
    profile, so callers that have not classified yet still get
    well-defined behaviour.
    """
    return _PROFILES.get(query_class or DEFAULT_CLASS, _PROFILES[DEFAULT_CLASS])


__all__ = [
    "Classification",
    "DEFAULT_CLASS",
    "JUDGE_THRESHOLD",
    "JudgeFn",
    "QUERY_CLASSES",
    "RetrievalProfile",
    "classify_query",
    "retrieval_profile",
]
