"""Tests for the principle abstraction layer and transfer graph.

The contract under test:

1. Two empirical cases that link to the same principle text converge
   on a single :class:`AbstractPrinciple` (id is content-addressed off
   the canonical statement, so this works without semantic
   clustering).
2. A third case can *bound* or *contradict* the principle, and that
   relationship is reflected in the principle's status and confidence
   band.
3. An abstract-only source produces a principle with provenance and
   no ``CASE_INSTANTIATES`` edge.
4. The transfer graph serializes deterministically: two runs that
   produce the same logical graph emit byte-identical JSON.

The tests deliberately avoid the LLM-backed case extractor — they
construct ``EmpiricalCaseStudy`` instances by hand so the principle
abstractor's behaviour is what's exercised.
"""

from __future__ import annotations

import json

import pytest

from noosphere.cases.models import (
    AbstractPrincipleLink,
    CaseStudyExtraction,
    CaseStudyKind,
    EmpiricalCaseStudy,
    EvidenceQuality,
    SourceSpan,
)
from noosphere.principles import (
    AbstractPrinciple,
    FailureCondition,
    NegationCandidate,
    PrincipleAbstractor,
    PrincipleConfidence,
    PrincipleStatus,
    TransferEdge,
    TransferEdgeKind,
    TransferGraph,
    TransferRisk,
    canonical_principle_id,
    normalize_principle_text,
)
from noosphere.principles.abstractor import (
    AbstractOnlySource,
    BoundingCaseLink,
    ContradictingCaseLink,
)


_PRINCIPLE_TEXT = (
    "Maturity mismatch between long assets and overnight funding "
    "creates run risk."
)


def _case(
    *,
    case_id: str,
    chunk_id: str,
    quote: str,
    domain: str,
    actors: list[str],
    mechanism: str,
    outcome: str,
    transfer_conditions: str,
    principle_text: str = _PRINCIPLE_TEXT,
) -> EmpiricalCaseStudy:
    return EmpiricalCaseStudy(
        id=case_id,
        kind=CaseStudyKind.NAMED_CASE,
        title=case_id,
        source_span=SourceSpan(chunk_id=chunk_id, source_quote=quote),
        actors=actors,
        institutions=actors,
        time_period="historical",
        domain=domain,
        observed_mechanism=mechanism,
        outcome=outcome,
        stated_causal_claim=mechanism,
        evidence_quality=EvidenceQuality.ASSERTED,
        linked_principles=[
            AbstractPrincipleLink(
                principle_text=principle_text,
                transfer_conditions=transfer_conditions,
            )
        ],
    )


def _extraction(case: EmpiricalCaseStudy) -> CaseStudyExtraction:
    return CaseStudyExtraction(
        chunk_id=case.source_span.chunk_id, cases=[case]
    )


# ── 1. Two cases converge on the same principle ──────────────────────────────


def test_two_cases_abstract_to_same_principle() -> None:
    lehman = _case(
        case_id="case_lehman",
        chunk_id="chunk_lehman",
        quote=(
            "In 2008 Lehman Brothers failed after its leverage ratio "
            "climbed past 30:1 and short-term funding markets refused "
            "to roll its repo book."
        ),
        domain="finance",
        actors=["Lehman Brothers"],
        mechanism="Excess leverage with short-term repo funding produces a run on roll refusal.",
        outcome="Lehman collapsed within a week.",
        transfer_conditions=(
            "Applies whenever a leveraged intermediary depends on rolling short-term funding."
        ),
    )
    nb = _case(
        case_id="case_northern_rock",
        chunk_id="chunk_nb",
        quote=(
            "In 2007 Northern Rock's reliance on wholesale short-term "
            "funding produced a depositor run once the funding window closed."
        ),
        domain="finance",
        actors=["Northern Rock"],
        mechanism=(
            "Wholesale short-term funding withdrawn caused a liquidity "
            "crisis at a leveraged mortgage lender."
        ),
        outcome="Northern Rock was nationalised.",
        transfer_conditions=(
            "Applies whenever a leveraged intermediary depends on rolling short-term funding."
        ),
    )

    result = PrincipleAbstractor().abstract(
        extractions=[_extraction(lehman), _extraction(nb)]
    )

    assert len(result.principles) == 1
    principle = result.principles[0]
    assert principle.id == canonical_principle_id(_PRINCIPLE_TEXT)
    assert sorted(principle.supporting_case_ids) == [
        "case_lehman",
        "case_northern_rock",
    ]
    # Two independent supporting cases → REFINED, MODERATE confidence.
    assert principle.status == PrincipleStatus.REFINED.value
    assert principle.confidence.band == PrincipleConfidence.MODERATE.value
    assert principle.confidence.supporting_case_count == 2
    # The provenance chain is preserved end-to-end.
    chunk_ids = sorted(p.chunk_id for p in principle.provenance)
    assert chunk_ids == ["chunk_lehman", "chunk_nb"]
    # Both source quotes survive.
    quotes = " ".join(p.source_quote for p in principle.provenance)
    assert "Lehman" in quotes and "Northern Rock" in quotes
    # The transfer graph has two CASE_INSTANTIATES edges and no others.
    edges = [(e.source_id, e.kind) for e in result.graph.edges]
    assert (
        "case_lehman",
        TransferEdgeKind.CASE_INSTANTIATES.value,
    ) in edges
    assert (
        "case_northern_rock",
        TransferEdgeKind.CASE_INSTANTIATES.value,
    ) in edges


def test_two_cases_in_different_domains_widen_scope() -> None:
    """Cross-domain corroboration trips ``domain_breadth`` in the
    calibration. The score still does not reach the ``HIGH`` band — that
    is the distillation path's responsibility."""

    finance = _case(
        case_id="case_finance",
        chunk_id="chunk_f",
        quote=(
            "A leveraged broker relying on overnight repo collapsed "
            "when its counterparties refused to roll."
        ),
        domain="finance",
        actors=["Broker"],
        mechanism="Overnight funding withdrawn against long assets.",
        outcome="Insolvency.",
        transfer_conditions=(
            "Applies whenever a leveraged intermediary depends on rolling short-term funding."
        ),
    )
    sovereign = _case(
        case_id="case_sovereign",
        chunk_id="chunk_s",
        quote=(
            "A government rolling its debt at short tenors faced a "
            "buyers' strike when foreign creditors withdrew."
        ),
        domain="sovereign_debt",
        actors=["Treasury"],
        mechanism="Short-tenor debt could not be rolled in a confidence shock.",
        outcome="Default.",
        transfer_conditions=(
            "Applies whenever a leveraged intermediary depends on rolling short-term funding."
        ),
    )

    result = PrincipleAbstractor().abstract(
        extractions=[_extraction(finance), _extraction(sovereign)]
    )

    principle = result.principles[0]
    assert set(principle.scope) == {"finance", "sovereign_debt"}
    assert principle.confidence.domain_breadth == 2
    assert principle.confidence.band == PrincipleConfidence.MODERATE.value
    # The cap on score is explicit; firm-level confidence belongs to
    # the distillation path, not this abstractor.
    assert principle.confidence.score <= 0.7


# ── 2a. Third case BOUNDS the principle ──────────────────────────────────────


def test_third_case_bounds_principle() -> None:
    lehman = _case(
        case_id="case_lehman",
        chunk_id="chunk_lehman",
        quote="Lehman 2008 collapse on repo roll refusal.",
        domain="finance",
        actors=["Lehman"],
        mechanism="Excess leverage with short-term repo funding produces a run.",
        outcome="Collapse.",
        transfer_conditions="Applies to leveraged repo-funded intermediaries.",
    )
    nb = _case(
        case_id="case_northern_rock",
        chunk_id="chunk_nb",
        quote="Northern Rock 2007 wholesale-funding run.",
        domain="finance",
        actors=["Northern Rock"],
        mechanism="Wholesale funding withdrawn at a leveraged lender.",
        outcome="Nationalisation.",
        transfer_conditions="Applies to leveraged wholesale-funded lenders.",
    )

    # The bounding case is registered only as a bound — not as a
    # supporting case extraction. The abstractor still admits it into
    # the graph via ``bounding_links``; this keeps the supporting /
    # bounding counts clean.
    abstractor = PrincipleAbstractor()
    pid = canonical_principle_id(_PRINCIPLE_TEXT)
    result = abstractor.abstract(
        extractions=[_extraction(lehman), _extraction(nb)],
        bounding_links=[
            BoundingCaseLink(
                case_id="case_money_market_fund",
                principle_id=pid,
                rationale="Unleveraged vehicles are outside the principle's scope.",
            )
        ],
    )

    principle = result.principles[0]
    assert principle.id == pid
    assert principle.confidence.supporting_case_count == 2
    assert principle.confidence.bounding_case_count == 1
    assert "case_money_market_fund" in principle.bounding_case_ids
    # Bound (without contradiction) sets the status to BOUNDED.
    assert principle.status == PrincipleStatus.BOUNDED.value
    # There is exactly one CASE_BOUNDS edge.
    bounds_edges = [
        e for e in result.graph.edges if e.kind == TransferEdgeKind.CASE_BOUNDS.value
    ]
    assert len(bounds_edges) == 1
    assert bounds_edges[0].source_id == "case_money_market_fund"
    assert bounds_edges[0].target_id == pid


# ── 2b. Third case CONTRADICTS the principle ─────────────────────────────────


def test_third_case_contradicts_principle() -> None:
    lehman = _case(
        case_id="case_lehman",
        chunk_id="chunk_lehman",
        quote="Lehman 2008 collapse on repo roll refusal.",
        domain="finance",
        actors=["Lehman"],
        mechanism="Excess leverage with short-term repo funding produces a run.",
        outcome="Collapse.",
        transfer_conditions="Applies to leveraged repo-funded intermediaries.",
    )
    nb = _case(
        case_id="case_northern_rock",
        chunk_id="chunk_nb",
        quote="Northern Rock 2007 wholesale-funding run.",
        domain="finance",
        actors=["Northern Rock"],
        mechanism="Wholesale funding withdrawn at a leveraged lender.",
        outcome="Nationalisation.",
        transfer_conditions="Applies to leveraged wholesale-funded lenders.",
    )

    abstractor = PrincipleAbstractor()
    pid = canonical_principle_id(_PRINCIPLE_TEXT)
    result = abstractor.abstract(
        extractions=[_extraction(lehman), _extraction(nb)],
        contradicting_links=[
            ContradictingCaseLink(
                case_id="case_2020_repo_intervention",
                principle_id=pid,
                rationale="Lender-of-last-resort breaks the predicted mechanism.",
            )
        ],
    )

    principle = result.principles[0]
    assert "case_2020_repo_intervention" in principle.contradicting_case_ids
    assert principle.status == PrincipleStatus.CONTRADICTED.value
    # Confidence is dragged into the LOW band; multiple supporting
    # cases do *not* override a contradiction.
    assert principle.confidence.band == PrincipleConfidence.LOW.value
    assert (
        TransferEdgeKind.CASE_CONTRADICTS.value
        in {e.kind for e in result.graph.edges}
    )


# ── 3. Abstract-only source → principle with no CASE_INSTANTIATES edge ───────


def test_abstract_only_source_creates_principle_without_case_edge() -> None:
    abstract_source = AbstractOnlySource(
        canonical_statement=(
            "When a coordination system rewards credential signaling "
            "over truth-seeking, local actors optimize for legibility "
            "rather than discovery."
        ),
        mechanism=(
            "Reward function targets observable proxies; agents respond "
            "to the proxy and starve the underlying signal."
        ),
        chunk_id="chunk_abstract",
        source_quote=(
            "When a coordination system rewards credential signaling "
            "over truth-seeking, local actors optimize for legibility."
        ),
        domain="coordination",
        scope=["coordination", "institutions"],
        preconditions=["credentialing is rewarded", "truth-seeking is unrewarded"],
        expected_outcomes=["optimization shifts toward legible proxies"],
        failure_conditions=[
            FailureCondition(
                description=(
                    "Truth-seeking is independently rewarded by a parallel "
                    "channel the credential system does not capture."
                ),
                detectable_signal="Parallel reward channel for discovery.",
                severity=PrincipleConfidence.HIGH,
            )
        ],
        negation_candidates=[
            NegationCandidate(
                statement=(
                    "Credential-rewarding systems consistently produce truth-seeking "
                    "behaviour at the local actor level."
                ),
                rationale="If true, the principle's predicted optimization shift does not occur.",
            )
        ],
        transfer_risk=TransferRisk(
            domain_shift="May not transfer to small face-to-face coordination groups.",
        ),
    )

    result = PrincipleAbstractor().abstract(
        abstract_only_sources=[abstract_source]
    )

    assert len(result.principles) == 1
    principle = result.principles[0]
    assert principle.canonical_statement.startswith("When a coordination system")
    assert principle.supporting_case_ids == []
    assert principle.provenance == [
        principle.provenance[0]
    ]
    assert principle.provenance[0].extracted_from == "abstract_only"
    assert principle.provenance[0].case_id is None
    # The graph has the principle as a node, no case ids, no edges.
    assert result.graph.case_ids == []
    assert result.graph.edges == []
    # Single-source abstract principle stays at CANDIDATE / LOW.
    assert principle.status == PrincipleStatus.CANDIDATE.value
    assert principle.confidence.band == PrincipleConfidence.LOW.value


def test_abstract_only_source_without_failure_condition_or_negation_raises() -> None:
    """The abstractor refuses to construct an
    :class:`AbstractPrinciple` whose principle is not contradiction-testable.
    This is a model-level invariant, not just a policy."""

    with pytest.raises(ValueError):
        # The model validator enforces that at least one of
        # ``failure_conditions`` or ``negation_candidates`` is present.
        AbstractPrinciple(
            id=canonical_principle_id("All swans are white."),
            canonical_statement="All swans are white.",
            failure_conditions=[],
            negation_candidates=[],
        )


# ── 4. Transfer graph serialization is stable ────────────────────────────────


def test_transfer_graph_serialization_is_stable_across_insertion_order() -> None:
    lehman = _case(
        case_id="case_lehman",
        chunk_id="chunk_lehman",
        quote="Lehman 2008 collapse.",
        domain="finance",
        actors=["Lehman"],
        mechanism="Excess leverage with short-term repo funding produces a run.",
        outcome="Collapse.",
        transfer_conditions="Applies whenever a leveraged intermediary depends on rolling short-term funding.",
    )
    nb = _case(
        case_id="case_northern_rock",
        chunk_id="chunk_nb",
        quote="Northern Rock 2007 wholesale-funding run.",
        domain="finance",
        actors=["Northern Rock"],
        mechanism="Wholesale funding withdrawn at a leveraged lender.",
        outcome="Nationalisation.",
        transfer_conditions="Applies whenever a leveraged intermediary depends on rolling short-term funding.",
    )
    pid = canonical_principle_id(_PRINCIPLE_TEXT)

    forward = PrincipleAbstractor().abstract(
        extractions=[_extraction(lehman), _extraction(nb)],
        bounding_links=[
            BoundingCaseLink(
                case_id="case_money_market_fund",
                principle_id=pid,
                rationale="Unleveraged vehicles excluded.",
            )
        ],
    )
    reverse = PrincipleAbstractor().abstract(
        extractions=[_extraction(nb), _extraction(lehman)],
        bounding_links=[
            BoundingCaseLink(
                case_id="case_money_market_fund",
                principle_id=pid,
                rationale="Unleveraged vehicles excluded.",
            )
        ],
    )

    fwd_dict = forward.graph.to_dict()
    rev_dict = reverse.graph.to_dict()
    assert fwd_dict == rev_dict
    # And the JSON form is byte-identical.
    assert forward.graph.to_json() == reverse.graph.to_json()


def test_transfer_graph_round_trips_through_dict() -> None:
    abstract_source = AbstractOnlySource(
        canonical_statement="Markets punish overconfidence eventually.",
        mechanism="Overconfident actors take outsized risk that mean-reverts.",
        chunk_id="chunk_x",
        source_quote="Markets punish overconfidence eventually.",
        domain="markets",
        scope=["markets"],
        failure_conditions=[
            FailureCondition(
                description="A regime change subsidizes overconfident strategies indefinitely.",
                detectable_signal="Persistent state subsidy.",
                severity=PrincipleConfidence.MODERATE,
            )
        ],
    )
    result = PrincipleAbstractor().abstract(abstract_only_sources=[abstract_source])
    payload = result.graph.to_dict()

    # Round-trip via from_dict must yield an equivalent graph.
    rebuilt = TransferGraph.from_dict(payload)
    assert rebuilt.to_dict() == payload

    # Payload must be JSON-serializable.
    serialized = json.dumps(payload, sort_keys=True)
    assert "Markets punish overconfidence" in serialized


# ── Defensive: edge type-checking ────────────────────────────────────────────


def test_graph_rejects_misclassified_edge_endpoints() -> None:
    """A principle-to-principle edge with a case id at one endpoint is a
    programming error; the graph must raise rather than corrupt
    traversal semantics."""

    abstract_source = AbstractOnlySource(
        canonical_statement="Test principle A.",
        mechanism="Test mechanism.",
        chunk_id="chunk_a",
        source_quote="Test principle A.",
        failure_conditions=[
            FailureCondition(description="A fails when X.")
        ],
    )
    result = PrincipleAbstractor().abstract(
        abstract_only_sources=[abstract_source]
    )
    graph = result.graph
    pid = result.principles[0].id

    # Register a case, then try to use it as the *source* of a
    # principle→principle edge.
    graph.add_case("case_synthetic")
    with pytest.raises(ValueError):
        graph.add_edge(
            TransferEdge(
                source_id="case_synthetic",
                target_id=pid,
                kind=TransferEdgeKind.PRINCIPLE_REFINES,
            )
        )


# ── Defensive: cosmetic differences in canonical statement still converge ────


def test_normalize_principle_text_folds_cosmetic_differences() -> None:
    assert normalize_principle_text(
        "  Maturity mismatch creates run risk.  "
    ) == normalize_principle_text("Maturity Mismatch creates run risk")


def test_skipped_link_when_neither_failure_condition_nor_negation_inferable() -> None:
    """If the case extractor returned a principle link with empty
    ``transfer_conditions`` and the caller didn't supply explicit
    failure conditions, the principle cannot be made
    contradiction-testable. The abstractor must record the skip rather
    than synthesizing one."""

    thin = EmpiricalCaseStudy(
        id="case_thin",
        kind=CaseStudyKind.NAMED_CASE,
        title="Thin",
        source_span=SourceSpan(chunk_id="chunk_thin", source_quote="Some passage."),
        actors=["X"],
        institutions=["X"],
        domain="misc",
        observed_mechanism="m",
        outcome="o",
        stated_causal_claim="c",
        evidence_quality=EvidenceQuality.ASSERTED,
        linked_principles=[
            AbstractPrincipleLink(
                principle_text="Some principle.",
                transfer_conditions="",  # No scope, no failure to derive.
            )
        ],
    )
    result = PrincipleAbstractor().abstract(extractions=[_extraction(thin)])
    assert result.principles == []
    assert len(result.skipped_links) == 1
    assert result.skipped_links[0].principle_text == "Some principle."
