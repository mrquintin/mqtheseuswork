"""Aim-Method Fit — the third working criterion (THE_META_METHOD.md §2.3).

Aim-Method Fit asks one question: **does this method actually answer THIS
question?** A valuation method gives valuations; pointed at a product-
strategy question it has poor fit — not because it is unreliable (that is
Severity, §2.2) and not because it is outside its domain (that is Domain
Sensitivity, §2.5), but because the *shape of its output* is not the shape
the question demands.

Until now the MQS scored this as a soft LLM judgment with no precise rubric.
This module replaces that with a deterministic five-level rubric driven by
the question typology in :mod:`noosphere.inquiry.question_typology`.

The rubric
----------

Five levels, mapped to the MQS sub-score by ``level / 4``:

  * **0** — the method's outputs cannot answer the question type.
  * **1** — the outputs answer a related but different question.
  * **2** — the outputs answer part of the question.
  * **3** — the outputs answer the question, but with caveats the method
    cannot articulate.
  * **4** — the outputs answer the question with explicit caveats within
    the method's competence.

How the level is computed
-------------------------

From three inputs, exactly as §2.3 specifies:

  (a) the **question type** inferred from the conclusion's target text +
      topic hint (:func:`question_typology.infer_question_type`);
  (b) the **question types the producing method serves** — from the
      method's profile declaration, or the registry keyed on its
      ``pattern_type``;
  (c) the **worked-example match** — whether ``(question_type, pattern_type)``
      corresponds to a documented worked example in :data:`WORKED_EXAMPLES`.

The structural decision (a)+(b):

  * question type ∈ served types → the method answers the question.
    Level **4** if a serving method has an articulated boundary (declared
    failure modes); level **3** otherwise.
  * served types intersect ``DECOMPOSES_INTO[question_type]`` → the method
    answers a *reusable part* of the question → level **2**.
  * served types intersect ``ADJACENT[question_type]`` → the method answers
    a *related* question → level **1**.
  * otherwise → level **0**.
  * a conclusion whose every method is unregistered/undeclared → level **2**
    ("cannot verify fit", not "fits nothing" — §2.3 forbids retiring a
    method on this rubric alone).

(c) is a cross-check, not an override: the worked-example registry is the
rubric's labelled ground truth. The scorer records which worked example a
case corresponds to and whether the structural level *agrees* with the
labelled level. A disagreement is a rubric bug, and the test suite asserts
there are none.

The module is deterministic and dependency-light — standard library plus
:mod:`noosphere.inquiry.question_typology`. No LLM is consulted. That is the
point: Aim-Method Fit is now auditable and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Sequence, Tuple

from noosphere.inquiry.question_typology import (
    ADJACENT,
    DECOMPOSES_INTO,
    QuestionType,
    QuestionTypeInference,
    infer_question_type,
    normalize_pattern_type,
    question_types_for_method,
)


# ── Levels ─────────────────────────────────────────────────────────────────

#: Level → MQS sub-score. Evenly spaced: ``level / 4``.
LEVEL_SCORES: Dict[int, float] = {0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}

#: Short machine-readable name per level (used in evidence blobs).
LEVEL_NAMES: Dict[int, str] = {
    0: "cannot-answer",
    1: "related-different",
    2: "answers-part",
    3: "answers-implicit-caveats",
    4: "answers-explicit-caveats",
}

#: The rubric text, verbatim from §2.3 / docs/methods/Aim_Method_Fit_Rubric.md.
LEVEL_DESCRIPTIONS: Dict[int, str] = {
    0: "The method's outputs cannot answer the question type.",
    1: "The outputs answer a related but different question.",
    2: "The outputs answer part of the question.",
    3: (
        "The outputs answer the question, but with caveats the method "
        "cannot articulate."
    ),
    4: (
        "The outputs answer the question with explicit caveats within the "
        "method's competence."
    ),
}


# ── Inputs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MethodView:
    """What the rubric needs to know about one producing method.

    ``declared_question_types`` is the method's own declaration (from its
    MethodologyProfile); when empty the rubric falls back to the
    ``pattern_type`` registry. ``has_articulated_boundary`` is true when the
    method declares failure modes — i.e. it can say *when* it should not be
    trusted, which is what separates rubric level 4 from level 3.
    """

    pattern_type: str = ""
    declared_question_types: Tuple[QuestionType, ...] = ()
    has_articulated_boundary: bool = False


def served_by(method: MethodView) -> FrozenSet[QuestionType]:
    """The question types a method serves: its own declaration if it has
    one, otherwise the registry lookup, otherwise the empty set."""
    if method.declared_question_types:
        return frozenset(method.declared_question_types)
    registry = question_types_for_method(method.pattern_type)
    return registry if registry is not None else frozenset()


def is_registered(method: MethodView) -> bool:
    """True when the method declares its served types (directly or via the
    registry). An unregistered method contributes nothing to the fit
    computation but is not itself penalised to level 0."""
    if method.declared_question_types:
        return True
    return question_types_for_method(method.pattern_type) is not None


# ── Worked examples — the rubric's labelled ground truth ───────────────────


@dataclass(frozen=True)
class WorkedExample:
    """One labelled (question, method) → level pairing.

    Every level has at least two. The test suite runs each through
    :func:`score_aim_method_fit` and asserts the structural rubric
    reproduces ``level`` and ``expected_question_type`` — that is what keeps
    the prose rubric and the code from drifting.
    """

    id: str
    level: int
    question_text: str
    topic_hint: str
    method_pattern_type: str
    method_has_boundary: bool
    expected_question_type: QuestionType
    note: str

    def method_view(self) -> MethodView:
        return MethodView(
            pattern_type=self.method_pattern_type,
            has_articulated_boundary=self.method_has_boundary,
        )


WORKED_EXAMPLES: Tuple[WorkedExample, ...] = (
    # ── Level 4: serves the question type, articulated boundary ─────────
    WorkedExample(
        id="WE-4a",
        level=4,
        question_text=(
            "Will the company's monthly active users stay above 10k "
            "through 2026?"
        ),
        topic_hint="forecasting",
        method_pattern_type="empirical_calibration",
        method_has_boundary=True,
        expected_question_type=QuestionType.PREDICTIVE,
        note=(
            "Empirical calibration serves predictive questions and declares "
            "its failure modes; it answers this with explicit caveats."
        ),
    ),
    WorkedExample(
        id="WE-4b",
        level=4,
        question_text="Is this method's reasoning internally sound?",
        topic_hint="reasoning quality",
        method_pattern_type="adversarial_audit",
        method_has_boundary=True,
        expected_question_type=QuestionType.NORMATIVE,
        note=(
            "An adversarial audit serves normative questions about soundness "
            "and declares where its own audit is unreliable."
        ),
    ),
    WorkedExample(
        id="WE-4c",
        level=4,
        question_text="What kind of reasoning pattern does this method use?",
        topic_hint="method classification",
        method_pattern_type="representational_geometry",
        method_has_boundary=True,
        expected_question_type=QuestionType.CLASSIFICATORY,
        note=(
            "Representational geometry serves classificatory questions and "
            "declares its failure modes."
        ),
    ),
    # ── Level 3: serves the question type, no articulated boundary ──────
    WorkedExample(
        id="WE-3a",
        level=3,
        question_text="Will inflation exceed 3% next year?",
        topic_hint="forecasting",
        method_pattern_type="bayesian_update",
        method_has_boundary=False,
        expected_question_type=QuestionType.PREDICTIVE,
        note=(
            "Bayesian update serves predictive questions, but with no "
            "declared failure modes it cannot articulate its own caveats."
        ),
    ),
    WorkedExample(
        id="WE-3b",
        level=3,
        question_text="What is the composition of the firm's asset base?",
        topic_hint="",
        method_pattern_type="first_principles_decomposition",
        method_has_boundary=False,
        expected_question_type=QuestionType.DESCRIPTIVE,
        note=(
            "First-principles decomposition serves descriptive questions; "
            "without declared failure modes the caveats stay implicit."
        ),
    ),
    # ── Level 2: serves a reusable part (DECOMPOSES_INTO) of the question ─
    WorkedExample(
        id="WE-2a",
        level=2,
        question_text="Will the new market clear by 2026?",
        topic_hint="forecasting",
        method_pattern_type="first_principles_decomposition",
        method_has_boundary=True,
        expected_question_type=QuestionType.PREDICTIVE,
        note=(
            "A predictive question reuses a description of current state. "
            "First-principles decomposition serves the descriptive part, "
            "not the forecast itself."
        ),
    ),
    WorkedExample(
        id="WE-2b",
        level=2,
        question_text="Is this asset a sound long-term holding?",
        topic_hint="",
        method_pattern_type="representational_geometry",
        method_has_boundary=True,
        expected_question_type=QuestionType.NORMATIVE,
        note=(
            "A normative judgment reuses what-is and what-kind. "
            "Representational geometry serves the classificatory/descriptive "
            "part, not the value judgment."
        ),
    ),
    # ── Level 1: serves only an adjacent (related-but-different) type ────
    WorkedExample(
        id="WE-1a",
        level=1,
        question_text="What product should the company build next?",
        topic_hint="product strategy",
        method_pattern_type="valuation",
        method_has_boundary=True,
        expected_question_type=QuestionType.STRATEGIC,
        note=(
            "The firm's anchor misfit: a valuation serves normative and "
            "predictive questions — adjacent to strategic, but it does not "
            "answer 'what should we build'."
        ),
    ),
    WorkedExample(
        id="WE-1b",
        level=1,
        question_text="Will this product line grow next year?",
        topic_hint="growth forecast",
        method_pattern_type="product_strategy",
        method_has_boundary=True,
        expected_question_type=QuestionType.PREDICTIVE,
        note=(
            "A product-strategy method serves strategic questions — adjacent "
            "to predictive, but it does not itself produce the forecast."
        ),
    ),
    # ── Level 0: serves nothing the question can use ────────────────────
    WorkedExample(
        id="WE-0a",
        level=0,
        question_text="How did the firm derive this conclusion?",
        topic_hint="methodology",
        method_pattern_type="valuation",
        method_has_boundary=True,
        expected_question_type=QuestionType.METHODOLOGICAL,
        note=(
            "A valuation's outputs (worth, price expectation) are disjoint "
            "from a methodological question — not its decomposition, not "
            "even adjacent."
        ),
    ),
    WorkedExample(
        id="WE-0b",
        level=0,
        question_text="What is the firm's current headcount?",
        topic_hint="",
        method_pattern_type="product_strategy",
        method_has_boundary=True,
        expected_question_type=QuestionType.DESCRIPTIVE,
        note=(
            "A product-strategy method produces recommended actions; it "
            "cannot answer a plain descriptive question."
        ),
    ),
)


def match_worked_example(
    question_type: QuestionType, methods: Sequence[MethodView]
) -> Optional[WorkedExample]:
    """Return the documented worked example a ``(question_type, method)``
    pair corresponds to, if any. Input (c) of the rubric."""
    method_keys = {normalize_pattern_type(m.pattern_type) for m in methods}
    for we in WORKED_EXAMPLES:
        if we.expected_question_type != question_type:
            continue
        if normalize_pattern_type(we.method_pattern_type) in method_keys:
            return we
    return None


# ── Result ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AimMethodFitResult:
    """The rubric's verdict for one conclusion.

    ``relation`` is the structural reason for the level: ``serves`` /
    ``answers-part`` / ``related-different`` / ``disjoint`` /
    ``undeclared`` / ``no-method``.
    """

    level: int
    score: float
    question_type: QuestionType
    question_type_confidence: float
    served_question_types: Tuple[QuestionType, ...]
    relation: str
    worked_example_id: Optional[str]
    worked_example_agrees: Optional[bool]
    signals: Tuple[str, ...]
    rationale: str

    def as_evidence(self) -> Dict[str, object]:
        """A small, JSON-round-trippable blob for the MQS evidence column."""
        return {
            "rule": "aim_method_fit_v2",
            "level": self.level,
            "level_name": LEVEL_NAMES[self.level],
            "score": round(self.score, 4),
            "question_type": self.question_type.value,
            "question_type_confidence": round(self.question_type_confidence, 4),
            "served_question_types": sorted(
                t.value for t in self.served_question_types
            ),
            "relation": self.relation,
            "worked_example_id": self.worked_example_id,
            "worked_example_agrees": self.worked_example_agrees,
            "signals": list(self.signals),
            "rationale": self.rationale,
        }


def _structural_level(
    question_type: QuestionType, methods: Sequence[MethodView]
) -> Tuple[int, str, FrozenSet[QuestionType]]:
    """Compute the rubric level from inputs (a) the question type and
    (b) the question types the producing methods serve."""
    if not methods:
        return 2, "no-method", frozenset()

    registered = [m for m in methods if is_registered(m)]
    if not registered:
        # Every producing method is unregistered. We cannot verify fit;
        # §2.3 forbids treating "cannot verify" as "fits nothing".
        return 2, "undeclared", frozenset()

    served: FrozenSet[QuestionType] = frozenset()
    for m in registered:
        served = served | served_by(m)

    if question_type in served:
        boundary = any(
            m.has_articulated_boundary and question_type in served_by(m)
            for m in registered
        )
        return (4 if boundary else 3), "serves", served

    if served & DECOMPOSES_INTO.get(question_type, frozenset()):
        return 2, "answers-part", served

    if served & ADJACENT.get(question_type, frozenset()):
        return 1, "related-different", served

    return 0, "disjoint", served


def _rationale(
    level: int,
    relation: str,
    question_type: QuestionType,
    served: FrozenSet[QuestionType],
) -> str:
    served_str = ", ".join(sorted(t.value for t in served)) or "none declared"
    qt = question_type.value
    if relation == "no-method":
        return (
            "No producing method attached; aim-method fit cannot be assessed "
            f"and defaults to level {level}."
        )
    if relation == "undeclared":
        return (
            "Every producing method is unregistered (no declared question "
            f"types); fit cannot be verified and defaults to level {level}."
        )
    if relation == "serves":
        boundary = (
            "with explicit, articulated caveats"
            if level == 4
            else "but its caveats stay implicit (no declared failure modes)"
        )
        return (
            f"The question is {qt}; the method serves {{{served_str}}}, which "
            f"includes {qt}. It answers the question {boundary}."
        )
    if relation == "answers-part":
        return (
            f"The question is {qt}; the method serves {{{served_str}}}, which "
            f"overlaps a reusable part of a {qt} question but not the whole."
        )
    if relation == "related-different":
        return (
            f"The question is {qt}; the method serves {{{served_str}}}, which "
            f"is adjacent to {qt} — it answers a related but different "
            "question."
        )
    return (
        f"The question is {qt}; the method serves {{{served_str}}}, which is "
        f"disjoint from {qt}, its decomposition, and its neighbours. The "
        "method's outputs cannot answer this question type."
    )


def score_aim_method_fit(
    conclusion_text: str,
    topic_hint: str,
    methods: Sequence[MethodView],
) -> AimMethodFitResult:
    """Score one conclusion's Aim-Method Fit, deterministically.

    ``conclusion_text`` should be the conclusion's target text (callers may
    append the rationale). ``topic_hint`` is the firm's topic tag.
    ``methods`` is the list of producing methods.
    """
    inference: QuestionTypeInference = infer_question_type(
        conclusion_text, topic_hint
    )
    question_type = inference.question_type

    level, relation, served = _structural_level(question_type, methods)

    worked = match_worked_example(question_type, methods)
    worked_id = worked.id if worked is not None else None
    worked_agrees = None if worked is None else (worked.level == level)

    rationale = _rationale(level, relation, question_type, served)
    if worked is not None and worked_agrees is False:
        # A rubric bug: the structural logic and the labelled worked example
        # disagree. Surface it loudly in the evidence; the test suite fails
        # on any such disagreement.
        rationale += (
            f" [WARNING: structural level {level} disagrees with worked "
            f"example {worked.id} (level {worked.level})]"
        )

    return AimMethodFitResult(
        level=level,
        score=LEVEL_SCORES[level],
        question_type=question_type,
        question_type_confidence=inference.confidence,
        served_question_types=tuple(sorted(served, key=lambda t: t.value)),
        relation=relation,
        worked_example_id=worked_id,
        worked_example_agrees=worked_agrees,
        signals=inference.signals,
        rationale=rationale,
    )


__all__ = [
    "LEVEL_DESCRIPTIONS",
    "LEVEL_NAMES",
    "LEVEL_SCORES",
    "WORKED_EXAMPLES",
    "AimMethodFitResult",
    "MethodView",
    "WorkedExample",
    "is_registered",
    "match_worked_example",
    "score_aim_method_fit",
    "served_by",
]
