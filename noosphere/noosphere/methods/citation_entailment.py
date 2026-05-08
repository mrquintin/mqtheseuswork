"""
Registered method: citation entailment judge.

A citation says "X supports Y, see source S". This method is the
adjudication step: given the firm's stated claim and an excerpt of the
underlying source, run an NLI judge and emit a verdict label
(``entails`` / ``contradicts`` / ``neutral`` / ``ambiguous``).

The wrapper is intentionally thin. The hard work — windowing the
excerpt, deciding whether to escalate the verdict to founder triage,
and persisting the row — lives in ``noosphere.literature.citation_chain``.
This method only gives the registry an invocation row to point at so an
auditor can re-derive a verdict from the recorded inputs.

The verdict thresholds match ``methods/_legacy/nli_scorer.py``: a class
must clear 0.55 and beat its rival to be picked; otherwise the verdict
is ``ambiguous``. The threshold is duplicated rather than re-imported
because the legacy scorer's threshold is intended for the s1-coherence
verdict (cohere/contradict/unresolved), and we want the citation
verdict to track it deliberately rather than by accident.
"""
from __future__ import annotations

from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


# Match nli_scorer.py / _legacy.nli_scorer thresholds. Duplicated on
# purpose — see module docstring.
_VERDICT_THRESHOLD = 0.55


class CitationEntailmentInput(BaseModel):
    """Input for one citation-entailment judgment.

    ``excerpt`` is the source text excerpt that will be recorded
    verbatim on the verdict row. The caller is responsible for
    windowing — this method does not re-trim it.

    ``stated_claim`` is the firm's claim about the source (the
    hypothesis side of NLI).

    ``relation`` is the firm-declared relation type. ``mentions`` is
    treated as a non-load-bearing relation: even if NLI says
    ``entails``, the verdict is clamped to ``ambiguous`` to avoid
    silently promoting a passing reference into a supporting cite.
    """

    excerpt: str
    stated_claim: str
    relation: str = "supports"


class CitationEntailmentOutput(BaseModel):
    """Verdict for one citation.

    ``relation_holds`` ∈ {entails, contradicts, neutral, ambiguous}.
    ``confidence`` is the max class probability — bounded to [0, 1].
    ``excerpt_used`` echoes the excerpt back so it travels with the
    verdict row (callers persist this verbatim).
    ``model_version`` identifies the NLI head; the underlying
    ``NLIScorer`` reports its model name via the legacy module.
    """

    relation_holds: str
    confidence: float
    excerpt_used: str
    stated_claim: str
    relation: str
    model_version: str
    entailment: float
    neutral: float
    contradiction: float


def _label_from_probs(
    entailment: float,
    neutral: float,
    contradiction: float,
) -> tuple[str, float]:
    """Pick a verdict label from softmax probabilities.

    Returns ``(label, confidence)``. Confidence is the probability of
    the chosen class, except for ``ambiguous`` where it's the max class
    probability (a "we tried" signal — the gate code uses it to rank
    near-misses).
    """

    if entailment >= _VERDICT_THRESHOLD and entailment > contradiction:
        return "entails", entailment
    if contradiction >= _VERDICT_THRESHOLD and contradiction > entailment:
        return "contradicts", contradiction
    if neutral >= _VERDICT_THRESHOLD and neutral > entailment and neutral > contradiction:
        return "neutral", neutral
    return "ambiguous", max(entailment, neutral, contradiction)


_NON_LOAD_BEARING_RELATIONS = frozenset({"mentions"})


def _scorer():
    # Lazy import — keeps module import cheap when only running tests
    # that pass an injected judge.
    from noosphere.methods._legacy.nli_scorer import NLIScorer

    return NLIScorer()


@register_method(
    name="citation_entailment",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=CitationEntailmentInput,
    output_schema=CitationEntailmentOutput,
    description="NLI-based citation-chain verdict: does the cited source actually support the firm's claim?",
    rationale=(
        "Per-citation entailment check. Premise = source excerpt, "
        "hypothesis = firm's stated claim. mentions-relations are "
        "clamped to ambiguous to prevent silent promotion of passing "
        "references."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.COHERES_WITH, CascadeEdgeRelation.CONTRADICTS],
    dependencies=[],
)
def citation_entailment(
    input_data: CitationEntailmentInput,
) -> CitationEntailmentOutput:
    scorer = _scorer()
    nli_probs, _partial, _verdict = scorer.score_pair(
        input_data.excerpt, input_data.stated_claim
    )
    label, confidence = _label_from_probs(
        nli_probs.entailment, nli_probs.neutral, nli_probs.contradiction
    )
    if input_data.relation in _NON_LOAD_BEARING_RELATIONS and label == "entails":
        # Firm declared the cite as a passing mention; do not let NLI
        # promote it to a supports-strength verdict.
        label = "ambiguous"
    model_version = getattr(scorer, "model_name", "deberta-v3-nli")
    return CitationEntailmentOutput(
        relation_holds=label,
        confidence=float(confidence),
        excerpt_used=input_data.excerpt,
        stated_claim=input_data.stated_claim,
        relation=input_data.relation,
        model_version=str(model_version),
        entailment=float(nli_probs.entailment),
        neutral=float(nli_probs.neutral),
        contradiction=float(nli_probs.contradiction),
    )
