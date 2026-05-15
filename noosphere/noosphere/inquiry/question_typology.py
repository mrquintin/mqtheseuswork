"""Question typology — the firm's taxonomy of *what a question is asking for*.

THE_META_METHOD.md §2.3 (Aim-Method Fit) asks whether a method "is actually
capable of answering the question being asked". To operationalize that, the
question has to be a typed object, not a free-text blob the LLM eyeballs.
This module is that type.

A *question type* names the **shape of the answer the question demands** —
not its topic, not its domain. "Will rates fall in 2026?" and "Will this
methodology survive replication?" are both ``predictive`` even though their
domains share nothing. Keeping the typology about *answer shape* is what
keeps Aim-Method Fit from collapsing into Domain Sensitivity (§2.5), which
is about *topic boundaries*.

Six types — the closed set the firm encounters:

  * ``descriptive``     — what is the case?      → a characterization
  * ``predictive``      — what will happen?      → a forecast with a horizon
  * ``normative``       — what is good / sound?  → an evaluation vs a standard
  * ``strategic``       — what should *we* do?   → a recommended action / rule
  * ``methodological``  — how is this reasoned?  → a procedure / derivation
  * ``classificatory``  — what kind of thing?    → a category / label

The module owns three relations over those types:

  * :data:`ADJACENT` — "same family, different question". A method whose
    outputs land in an *adjacent* type answers a *related* question, not the
    one asked (rubric level 1).
  * :data:`DECOMPOSES_INTO` — the sub-questions whose answers are *directly
    reusable* as part of answering the parent. A method serving one of those
    answers *part* of the question (rubric level 2). The relation is kept
    deliberately tight — only ``descriptive``/``classificatory`` are broadly
    reusable constituents — so that, e.g., a valuation method is *not*
    credited with partially answering a product-strategy question.
  * the method registry :data:`METHOD_QUESTION_TYPES` — every method
    ``pattern_type`` declares which question types it serves.

Shared with the public-query classifier from the ``/ask`` surface
(``noosphere.inference.query_classifier``): :func:`question_type_for_query_class`
maps that module's five public-query classes onto this six-type taxonomy, so
the firm has *one* notion of question shape, used both for retrieval routing
and for methodology scoring.

The module is dependency-light by design: standard library plus a single
import of the query-classifier's class vocabulary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple

from noosphere.inference.query_classifier import QUERY_CLASSES


# ── The taxonomy ───────────────────────────────────────────────────────────


class QuestionType(str, Enum):
    """The shape of the answer a question demands. ``str`` mixin so the
    value round-trips through JSON evidence blobs as a plain string."""

    DESCRIPTIVE = "descriptive"
    PREDICTIVE = "predictive"
    NORMATIVE = "normative"
    STRATEGIC = "strategic"
    METHODOLOGICAL = "methodological"
    CLASSIFICATORY = "classificatory"


QUESTION_TYPES: Tuple[QuestionType, ...] = tuple(QuestionType)

#: One-line gloss per type. ``answer_form`` is the *kind of object* a
#: well-fitted method hands back; it is what the rubric checks against.
QUESTION_TYPE_DESCRIPTIONS: Dict[QuestionType, str] = {
    QuestionType.DESCRIPTIVE: (
        "What is the case? Establishes facts, states, structures, mechanisms, "
        "magnitudes. Answer form: a characterization of what is."
    ),
    QuestionType.PREDICTIVE: (
        "What will happen? Establishes future states, probabilities, "
        "trajectories. Answer form: a forecast with a horizon."
    ),
    QuestionType.NORMATIVE: (
        "What is good, sound, or valuable? Establishes a quality judgment "
        "against a standard, independent of any particular actor's choices. "
        "Answer form: an evaluation."
    ),
    QuestionType.STRATEGIC: (
        "What should *we* do? Establishes a recommended action for an actor "
        "with goals and constraints. Answer form: a decision rule or course "
        "of action."
    ),
    QuestionType.METHODOLOGICAL: (
        "How should this be reasoned about, or how was it derived? "
        "Establishes a procedure, reasoning move, or evidentiary standard. "
        "Answer form: a method or derivation trail."
    ),
    QuestionType.CLASSIFICATORY: (
        "What kind of thing is this? Establishes category membership or "
        "type assignment. Answer form: a label or category."
    ),
}


def _symmetric(pairs: List[Tuple[QuestionType, QuestionType]]) -> Dict[QuestionType, FrozenSet[QuestionType]]:
    """Build a symmetric neighbour map from a list of unordered pairs."""
    out: Dict[QuestionType, set] = {t: set() for t in QUESTION_TYPES}
    for a, b in pairs:
        out[a].add(b)
        out[b].add(a)
    return {t: frozenset(v) for t, v in out.items()}


#: "Same family, different question." Symmetric. A method whose outputs land
#: in a type adjacent to the question's type answers something *related* but
#: not the thing asked — rubric level 1.
ADJACENT: Dict[QuestionType, FrozenSet[QuestionType]] = _symmetric(
    [
        (QuestionType.DESCRIPTIVE, QuestionType.CLASSIFICATORY),
        (QuestionType.DESCRIPTIVE, QuestionType.PREDICTIVE),
        (QuestionType.PREDICTIVE, QuestionType.STRATEGIC),
        (QuestionType.NORMATIVE, QuestionType.STRATEGIC),
        (QuestionType.NORMATIVE, QuestionType.CLASSIFICATORY),
        (QuestionType.METHODOLOGICAL, QuestionType.DESCRIPTIVE),
        (QuestionType.METHODOLOGICAL, QuestionType.CLASSIFICATORY),
    ]
)

#: Sub-questions whose answers are *directly reusable* as a constituent of
#: answering the parent. Deliberately tight: only ``descriptive`` and
#: ``classificatory`` answers are broad enough to be genuine constituents of
#: other questions. A method serving one of these answers *part* of the
#: question — rubric level 2. NOT symmetric.
DECOMPOSES_INTO: Dict[QuestionType, FrozenSet[QuestionType]] = {
    QuestionType.STRATEGIC: frozenset({QuestionType.DESCRIPTIVE}),
    QuestionType.PREDICTIVE: frozenset({QuestionType.DESCRIPTIVE}),
    QuestionType.NORMATIVE: frozenset(
        {QuestionType.DESCRIPTIVE, QuestionType.CLASSIFICATORY}
    ),
    QuestionType.METHODOLOGICAL: frozenset({QuestionType.CLASSIFICATORY}),
    QuestionType.DESCRIPTIVE: frozenset({QuestionType.CLASSIFICATORY}),
    QuestionType.CLASSIFICATORY: frozenset(),
}


# ── Inference: question text → question type ───────────────────────────────
#
# A regex signal layer, in the same spirit as
# noosphere/inference/query_classifier.py. Each type owns a list of
# (signal_name, compiled_pattern, weight). The conclusion's *target* text is
# scored against every type; the topic hint is scored too, at 3x weight,
# because the firm's own topic tag is a strong, deliberate signal of what the
# conclusion is about. Highest total wins.

_Signal = Tuple[str, "re.Pattern[str]", float]


def _s(name: str, pattern: str, weight: float = 1.0) -> _Signal:
    return (name, re.compile(pattern, re.IGNORECASE), weight)


_TOPIC_HINT_MULTIPLIER = 3.0

_SIGNALS: Dict[QuestionType, List[_Signal]] = {
    QuestionType.DESCRIPTIVE: [
        _s("what-is-the", r"\bwhat (?:is|are|was|were) (?:the|its|their|a|an)\b", 1.3),
        _s("what-is", r"\bwhat (?:is|are|was|were)\b", 0.9),
        _s("how-does-work", r"\bhow (?:does|do) .{0,40}\b(?:work|operate|function|consist)", 1.2),
        _s("describe", r"\bdescrib(?:e|es|ing)\b", 1.4),
        _s("consists-of", r"\b(?:consists? of|composed of|made up of|comprises?)\b", 1.3),
        _s("what-drives", r"\bwhat (?:drives|causes|explains|underlies)\b", 1.2),
        _s("structure-of", r"\b(?:structure|composition|mechanism|magnitude|breakdown) of\b", 1.1),
        _s("how-much", r"\bhow (?:much|many)\b", 1.2),
        _s("current-state", r"\bcurrent (?:headcount|revenue|state|status|size|level|mix|posture)\b", 1.3),
    ],
    QuestionType.PREDICTIVE: [
        _s("will", r"\bwill\b", 1.2),
        _s("forecast-word", r"\b(?:predict|forecast|projection|projected|outlook|prognos)", 1.7),
        _s("by-year", r"\bby (?:the )?(?:end of )?(?:19|20)\d\d\b", 1.5),
        _s("through-year", r"\bthrough (?:19|20)\d\d\b", 1.3),
        _s("next-period", r"\b(?:next|coming|following) (?:year|quarter|month|decade)\b", 1.4),
        _s("going-to", r"\b(?:going to|expected to|likely to|on track to|set to)\b", 1.1),
        _s("trend-verb", r"\b(?:grow|growth|rise|fall|decline|increase|decrease|exceed|reach|clear|flatten|plateau)\b", 0.8),
        _s("threshold-move", r"\b(?:falls?|drops?|rises?|climbs?|stays?) (?:below|above|under|over|past|to)\b", 1.2),
        _s("future-of", r"\bfuture of\b", 1.0),
    ],
    QuestionType.NORMATIVE: [
        _s("is-it-quality", r"\bis (?:it|this|that|the|a|an)\b.{0,60}\b(?:sound|good|bad|valid|flawed|robust|weak|strong|reliable|sensible|defensible|rigorous)\b", 1.6),
        _s("is-a-quality", r"\bis .{0,40}\ba (?:sound|good|poor|bad|strong|weak)\b", 1.5),
        _s("should-be", r"\b(?:should be|ought to be|ought to)\b", 1.1),
        _s("over-under-valued", r"\b(?:over|under)valued\b", 1.6),
        _s("worth-valuable", r"\b(?:worth|valuable|desirable)\b", 1.0),
        _s("quality-noun", r"\b(?:soundness|rigor|quality|validity)\b", 1.1),
        _s("sound-x", r"\b(?:sound|flawed|rigorous|defensible) (?:methodology|approach|argument|reasoning|holding|investment)\b", 1.5),
        _s("the-right", r"\bthe (?:right|best|correct) (?:way|choice|approach|standard)\b", 1.2),
        _s("valuation-topic", r"\bvaluation\b", 1.2),
    ],
    QuestionType.STRATEGIC: [
        _s("we-should", r"\b(?:we|the firm|the company|the team) (?:should|must|will|ought to|need to)\b", 1.6),
        _s("well-contraction", r"\bwe['’]ll\b", 1.4),
        _s("act-if", r"\b(?:exit|enter|buy|sell|hold|allocate|invest|divest) (?:if|when)\b", 1.7),
        _s("what-should-we", r"\bwhat (?:should|must) (?:we|the firm|the company|i)\b", 1.7),
        _s("what-should-build", r"\bwhat .{0,30}\bshould .{0,20}\b(?:build|do|pursue|prioriti|choose|make)\b", 1.6),
        _s("strategy-noun", r"\b(?:capital allocation|go.?to.?market|product strategy|our strategy)\b", 1.4),
        _s("recommend", r"\b(?:recommend|recommendation|decision rule|course of action)\b", 1.3),
        _s("should-actor", r"\bshould (?:we|the firm|the company|they|it)\b", 1.5),
        _s("if-then-we", r"\bif .{0,40} then (?:we|the firm|i)\b", 1.3),
    ],
    QuestionType.METHODOLOGICAL: [
        _s("how-did-derive", r"\bhow (?:did|do|does|was|were) (?:you|the firm|theseus|we|they|it) .{0,30}\b(?:derive|determine|conclude|reach|arrive|comput|establish|reason)", 1.8),
        _s("how-was-derived", r"\bhow (?:was|were) .{0,40}\b(?:derived|determined|reached|computed|established)\b", 1.7),
        _s("methodology-word", r"\bmethodolog", 1.6),
        _s("what-method", r"\bwhat (?:method|procedure|approach|process|technique)\b", 1.5),
        _s("what-evidence-would", r"\bwhat evidence would\b", 1.5),
        _s("how-do-you-know", r"\bhow (?:do|did) (?:you|the firm|we) know\b", 1.5),
        _s("reasoning-trail", r"\b(?:reasoning move|reasoning trail|audit trail|derivation)\b", 1.4),
        _s("how-should-reason", r"\bhow (?:should|would) .{0,30}\bbe (?:analy|reason|approach|assess)", 1.3),
    ],
    QuestionType.CLASSIFICATORY: [
        _s("what-kind-of", r"\bwhat (?:kind|type|sort|category|class) of\b", 1.8),
        _s("classify-word", r"\b(?:classif|categor|taxonom)", 1.6),
        _s("is-a-member", r"\bis .{0,40}\b(?:empirical or normative|a member of|an example of|an instance of|a kind of|a type of)\b", 1.6),
        _s("belongs-to", r"\b(?:belongs? to|counts? as|falls? under)\b", 1.4),
        _s("which-category", r"\bwhich (?:category|class|type|bucket)\b", 1.5),
        _s("pattern-type", r"\b(?:pattern type|reasoning pattern)\b", 1.2),
    ],
}


@dataclass(frozen=True)
class QuestionTypeInference:
    """The outcome of typing one question.

    ``signals`` lists the named rules that fired (``topic:`` prefix for
    rules that fired on the topic hint), so a reviewer can audit *why* a
    conclusion was typed the way it was. ``scores`` is the full per-type
    tally for the same reason.
    """

    question_type: QuestionType
    confidence: float
    signals: Tuple[str, ...]
    scores: Dict[QuestionType, float]


def _score_text(text: str, weight: float, prefix: str) -> Tuple[Dict[QuestionType, float], List[str]]:
    scores: Dict[QuestionType, float] = {t: 0.0 for t in QUESTION_TYPES}
    fired: List[str] = []
    if not text:
        return scores, fired
    for qtype, signals in _SIGNALS.items():
        for name, pattern, w in signals:
            if pattern.search(text):
                scores[qtype] += w * weight
                fired.append(f"{prefix}{name}")
    return scores, fired


def infer_question_type(text: str, topic_hint: str = "") -> QuestionTypeInference:
    """Infer the :class:`QuestionType` a conclusion's target demands.

    ``text`` is the conclusion text (optionally with its rationale appended
    by the caller). ``topic_hint`` is the firm's own topic tag; it is scored
    against the same signal set at 3x weight because it is a deliberate
    signal of what the conclusion is about.

    Falls back to ``descriptive`` with confidence 0.0 when nothing fires —
    most conclusions describe something, and a confidence of 0.0 tells the
    caller the type is a guess.
    """
    body_scores, body_signals = _score_text(text or "", 1.0, "")
    topic_scores, topic_signals = _score_text(
        topic_hint or "", _TOPIC_HINT_MULTIPLIER, "topic:"
    )
    scores = {t: body_scores[t] + topic_scores[t] for t in QUESTION_TYPES}
    signals = tuple(body_signals + topic_signals)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_type, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if top_score <= 0.0:
        return QuestionTypeInference(
            QuestionType.DESCRIPTIVE, 0.0, ("no-signal",), scores
        )

    margin = top_score - second_score
    confidence = 0.35 + 0.10 * min(top_score, 4.0) + 0.20 * min(margin, 3.0)
    confidence = max(0.0, min(0.98, confidence))
    return QuestionTypeInference(top_type, confidence, signals, scores)


# ── Method registry: which question types each method serves ───────────────
#
# Every method declares the question types its outputs can answer. The
# registry is keyed by the method's `pattern_type` (normalized: lowercased,
# hyphens folded to underscores). A method may *also* declare its served
# types directly on its MethodologyProfile (`question_types_served`); the
# rubric prefers the profile declaration and falls back to this registry.
#
# Unregistered methods return None — the rubric treats "undeclared" as
# "cannot verify fit", not as "fits nothing". (Constraint from §2.3: a
# method is not retired on this rubric alone.)


def normalize_pattern_type(pattern_type: str) -> str:
    """Fold a method ``pattern_type`` to its registry key."""
    return (pattern_type or "").strip().lower().replace("-", "_").replace(" ", "_")


_QT = QuestionType

METHOD_QUESTION_TYPES: Dict[str, FrozenSet[QuestionType]] = {
    # ── methods present in the firm's method graph ──────────────────────
    "empirical_calibration": frozenset({_QT.PREDICTIVE, _QT.DESCRIPTIVE}),
    "empirical": frozenset({_QT.DESCRIPTIVE, _QT.PREDICTIVE}),
    "bayesian_update": frozenset({_QT.PREDICTIVE, _QT.DESCRIPTIVE}),
    "first_principles_decomposition": frozenset(
        {_QT.DESCRIPTIVE, _QT.METHODOLOGICAL}
    ),
    "adversarial_audit": frozenset({_QT.METHODOLOGICAL, _QT.NORMATIVE}),
    "adversarial_revision": frozenset({_QT.METHODOLOGICAL, _QT.NORMATIVE}),
    "representational_geometry": frozenset(
        {_QT.CLASSIFICATORY, _QT.DESCRIPTIVE}
    ),
    "retraction_cascade": frozenset({_QT.METHODOLOGICAL, _QT.DESCRIPTIVE}),
    "analogical_transfer": frozenset({_QT.CLASSIFICATORY, _QT.DESCRIPTIVE}),
    "dialogic_unfolding": frozenset({_QT.DESCRIPTIVE, _QT.METHODOLOGICAL}),
    "normative_to_institutional_design": frozenset(
        {_QT.NORMATIVE, _QT.STRATEGIC}
    ),
    # ── illustrative methods used by the rubric's worked examples ───────
    # (the firm's example of a misfit: a valuation answers a normative /
    # predictive question, never a strategic one.)
    "valuation": frozenset({_QT.NORMATIVE, _QT.PREDICTIVE}),
    "dcf": frozenset({_QT.NORMATIVE, _QT.PREDICTIVE}),
    "comparables": frozenset({_QT.NORMATIVE, _QT.PREDICTIVE}),
    "product_strategy": frozenset({_QT.STRATEGIC}),
    "product_thesis": frozenset({_QT.STRATEGIC}),
    "market_sizing": frozenset({_QT.DESCRIPTIVE, _QT.PREDICTIVE}),
}


def register_method_question_types(
    pattern_type: str, types: FrozenSet[QuestionType]
) -> None:
    """Register (or override) the question types a method serves.

    Lets a new method declare its served types in code without editing this
    file. Idempotent; last write wins."""
    METHOD_QUESTION_TYPES[normalize_pattern_type(pattern_type)] = frozenset(types)


def question_types_for_method(
    pattern_type: str,
) -> Optional[FrozenSet[QuestionType]]:
    """Return the question types a method's ``pattern_type`` serves, or
    ``None`` when the method is not in the registry."""
    return METHOD_QUESTION_TYPES.get(normalize_pattern_type(pattern_type))


# ── Bridge to the public-query classifier (the /ask surface) ───────────────
#
# noosphere.inference.query_classifier types *public search queries* into
# five retrieval classes. Those classes map onto this taxonomy so the firm
# has one notion of question shape across both surfaces.

QUESTION_TYPE_FOR_QUERY_CLASS: Dict[str, QuestionType] = {
    "factual-claim": QuestionType.DESCRIPTIVE,
    "methodology-question": QuestionType.METHODOLOGICAL,
    "prediction-request": QuestionType.PREDICTIVE,
    # "what is the strongest case against this?" asks for an evaluation of
    # soundness — a normative question about the conclusion.
    "counter-argument-request": QuestionType.NORMATIVE,
    "browse": QuestionType.DESCRIPTIVE,
}

#: Any query class the bridge does not name explicitly is treated as
#: ``descriptive`` — the neutral, lowest-commitment shape.
_DEFAULT_QUERY_CLASS_TYPE = QuestionType.DESCRIPTIVE

# Keep the bridge honest: every class the classifier emits must have a
# mapping. Folded into the dict (rather than asserted) so a classifier-side
# addition degrades to the neutral type instead of crashing import.
for _qc in QUERY_CLASSES:
    QUESTION_TYPE_FOR_QUERY_CLASS.setdefault(_qc, _DEFAULT_QUERY_CLASS_TYPE)


def question_type_for_query_class(query_class: Optional[str]) -> QuestionType:
    """Map a public-query class (prompt 29's classifier) onto a
    :class:`QuestionType`. Unknown / ``None`` → ``descriptive``."""
    return QUESTION_TYPE_FOR_QUERY_CLASS.get(
        query_class or "", _DEFAULT_QUERY_CLASS_TYPE
    )


__all__ = [
    "ADJACENT",
    "DECOMPOSES_INTO",
    "METHOD_QUESTION_TYPES",
    "QUESTION_TYPES",
    "QUESTION_TYPE_DESCRIPTIONS",
    "QUESTION_TYPE_FOR_QUERY_CLASS",
    "QuestionType",
    "QuestionTypeInference",
    "infer_question_type",
    "normalize_pattern_type",
    "question_type_for_query_class",
    "question_types_for_method",
    "register_method_question_types",
]
