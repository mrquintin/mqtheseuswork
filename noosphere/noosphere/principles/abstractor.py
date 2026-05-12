"""Principle abstraction pass — consumes case extractions, emits candidate
principles, and assembles a transfer graph.

The pass is deliberately *not* a clustering routine. Two cases
abstract to the same principle iff they link to the same canonical
statement (modulo whitespace and casing). Semantic clustering of
similar-but-not-identical principle texts is a job for the
distillation pipeline (:mod:`noosphere.distillation`), which already
gates on cross-domain breadth.

What this pass does:

1. Walk ``CaseStudyExtraction`` records.
2. For each ``EmpiricalCaseStudy.linked_principles`` entry, derive a
   content-addressed principle id and either create a new
   :class:`AbstractPrinciple` or extend an existing one with the
   new case as a supporting node.
3. Accept *abstract-only* sources (e.g. a passage where the author
   states a principle without attaching a concrete case). These
   produce a principle with provenance to the chunk but no
   ``CASE_INSTANTIATES`` edge.
4. Allow the caller to record bounding / contradicting cases
   explicitly; the abstractor cannot infer them from a single
   ``EmpiricalCaseStudy``, but it knows how to register them.
5. Emit a :class:`TransferGraph` with typed edges.

The pass is conservative on confidence:

- a single case → ``CANDIDATE`` (low confidence band);
- two or more independent supporting cases (different chunk_ids) →
  ``REFINED`` (moderate);
- at least one contradicting case → ``CONTRADICTED``;
- at least one bounding case → ``BOUNDED`` (overrides ``REFINED``
  but not ``CONTRADICTED``);
- the band never crosses into ``HIGH``: that is reserved for the
  distillation path with cross-domain corroboration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from noosphere.cases.models import (
    AbstractPrincipleLink,
    CaseStudyExtraction,
    EmpiricalCaseStudy,
)
from noosphere.principles.models import (
    AbstractPrinciple,
    ConfidenceCalibration,
    FailureCondition,
    NegationCandidate,
    PrincipleConfidence,
    PrincipleProvenance,
    PrincipleStatus,
    TransferEdge,
    TransferEdgeKind,
    TransferGraph,
    TransferRisk,
    canonical_principle_id,
    normalize_principle_text,
)


# ── Inputs the caller may supply alongside case extractions ──────────────────


@dataclass(frozen=True)
class AbstractOnlySource:
    """A passage that states a principle *without* attaching a concrete case.

    Created when the case extractor emits a ``NonCaseMention`` of
    kind ``ABSTRACT_CONCEPT`` *and* the surrounding pipeline has
    enough additional structure (mechanism, preconditions, expected
    outcome, failure conditions) to make the principle
    contradiction-testable. The abstractor does not synthesize these
    fields from prose — they must be supplied by the caller, because
    inventing them silently is precisely the failure mode the package
    contract refuses.
    """

    canonical_statement: str
    mechanism: str
    chunk_id: str = ""
    source_quote: str = ""
    domain: str = ""
    scope: Sequence[str] = ()
    preconditions: Sequence[str] = ()
    expected_outcomes: Sequence[str] = ()
    failure_conditions: Sequence[FailureCondition] = ()
    negation_candidates: Sequence[NegationCandidate] = ()
    transfer_risk: Optional[TransferRisk] = None
    notes: str = ""


@dataclass(frozen=True)
class BoundingCaseLink:
    """A directive: case ``case_id`` *bounds* principle ``principle_id``.

    Recorded by hand (or by a downstream reviewer); the abstractor
    does not detect bounds from prose alone.
    """

    case_id: str
    principle_id: str
    rationale: str = ""


@dataclass(frozen=True)
class ContradictingCaseLink:
    """A directive: case ``case_id`` *contradicts* principle ``principle_id``."""

    case_id: str
    principle_id: str
    rationale: str = ""


# ── Result ───────────────────────────────────────────────────────────────────


@dataclass
class PrincipleAbstractionResult:
    """What the abstractor returns: the assembled graph plus a list of
    principles that the caller should consider for review.

    Returning the graph and the principle list separately keeps the
    common case (write to disk, render to UI) ergonomic while
    preserving the typed graph for downstream traversal.
    """

    graph: TransferGraph
    principles: list[AbstractPrinciple]
    skipped_links: list[AbstractPrincipleLink]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _link_is_contradiction_testable(link: AbstractPrincipleLink) -> bool:
    """An ``AbstractPrincipleLink`` produced by the case extractor only
    carries ``principle_text`` and ``transfer_conditions``. Neither field
    alone is sufficient to satisfy
    :class:`AbstractPrinciple`'s model-level requirement that a principle
    declare at least one failure condition or negation candidate. The
    caller (or the extractor's prompt) is expected to populate one of
    them via :func:`build_principle_from_link`'s ``failure_conditions`` /
    ``negation_candidates`` hooks. This helper just guards the link
    has *some* principle text to work from.
    """

    return bool(link.principle_text.strip())


def _failure_condition_from_transfer_condition(
    transfer_condition: str,
) -> Optional[FailureCondition]:
    """Promote a non-empty ``transfer_conditions`` string into a failure
    condition.

    The case extractor's ``transfer_conditions`` field captures *where*
    the principle is supposed to hold ("Applies whenever a leveraged
    intermediary depends on rolling short-term funding"). Inverted,
    that yields a usable failure-condition description ("Principle
    does not apply when ..."). This rewriting is conservative — we
    keep the original phrase and label it as a scope marker, leaving
    the rater to refine it.
    """

    text = (transfer_condition or "").strip()
    if not text:
        return None
    return FailureCondition(
        description=(
            f"Principle should not be applied outside its stated scope: {text}"
        ),
        detectable_signal="Scope check: target case must satisfy the stated transfer conditions.",
        severity=PrincipleConfidence.MODERATE,
    )


def _confidence_band_for(
    supporting: int, contradicting: int, bounding: int, domain_breadth: int
) -> tuple[PrincipleConfidence, float]:
    """Map raw counts to a coarse band + continuous score.

    The mapping is intentionally conservative:

    - Score is capped at 0.7 (the upper end of the ``MODERATE`` band).
      Promotion past 0.7 is reserved for the cross-domain distillation
      path.
    - A contradicting case never produces a ``HIGH`` band even if
      supporting count is large.
    - Domain breadth nudges the score upward but cannot, by itself,
      override contradictions.
    """

    if contradicting > 0 and supporting <= contradicting:
        return PrincipleConfidence.LOW, 0.2

    base = 0.0
    if supporting >= 1:
        base = 0.3
    if supporting >= 2:
        base = 0.5
    if bounding >= 1:
        base = max(base, 0.45)
    if domain_breadth >= 2:
        base = min(0.7, base + 0.1)
    if contradicting >= 1:
        base = min(base, 0.4)

    if base >= 0.5:
        return PrincipleConfidence.MODERATE, base
    return PrincipleConfidence.LOW, base


def _status_for(
    supporting: int, contradicting: int, bounding: int
) -> PrincipleStatus:
    if contradicting >= 1:
        return PrincipleStatus.CONTRADICTED
    if bounding >= 1:
        return PrincipleStatus.BOUNDED
    if supporting >= 2:
        return PrincipleStatus.REFINED
    return PrincipleStatus.CANDIDATE


# ── Principle builders ───────────────────────────────────────────────────────


def build_principle_from_link(
    *,
    case: EmpiricalCaseStudy,
    chunk_id: str,
    link: AbstractPrincipleLink,
    additional_failure_conditions: Sequence[FailureCondition] = (),
    additional_negation_candidates: Sequence[NegationCandidate] = (),
    transfer_risk: Optional[TransferRisk] = None,
) -> Optional[AbstractPrinciple]:
    """Construct a single :class:`AbstractPrinciple` from one case→principle link.

    Returns ``None`` if the link cannot be made contradiction-testable —
    i.e. neither a failure condition nor a negation candidate can be
    derived from the link's ``transfer_conditions`` and none were
    supplied by the caller. This is the path the *skipped_links* return
    field on :class:`PrincipleAbstractionResult` records.
    """

    if not _link_is_contradiction_testable(link):
        return None

    failure_conditions = list(additional_failure_conditions)
    derived_failure = _failure_condition_from_transfer_condition(
        link.transfer_conditions
    )
    if derived_failure is not None:
        failure_conditions.append(derived_failure)
    negation_candidates = list(additional_negation_candidates)

    if not failure_conditions and not negation_candidates:
        # Without a stated failure mode or a negation candidate the
        # principle would not be contradiction-testable. We refuse to
        # fabricate one — the extractor is expected to either fill
        # ``transfer_conditions`` or to plumb explicit failure
        # conditions through the abstractor.
        return None

    statement = link.principle_text.strip()
    principle_id = canonical_principle_id(statement)
    scope = [case.domain] if case.domain else []
    return AbstractPrinciple(
        id=principle_id,
        canonical_statement=statement,
        scope=scope,
        domain=case.domain,
        mechanism=case.observed_mechanism,
        preconditions=[],
        expected_outcomes=[case.outcome] if case.outcome else [],
        failure_conditions=failure_conditions,
        negation_candidates=negation_candidates,
        supporting_case_ids=[case.id],
        provenance=[
            PrincipleProvenance(
                chunk_id=chunk_id,
                source_quote=case.source_span.source_quote,
                case_id=case.id,
                extracted_from="case",
            )
        ],
        transfer_risk=transfer_risk or TransferRisk(),
    )


def build_principle_from_abstract_source(
    source: AbstractOnlySource,
) -> AbstractPrinciple:
    """Construct a principle from an abstract-only source.

    The caller must supply at least one of ``failure_conditions`` or
    ``negation_candidates``; otherwise the :class:`AbstractPrinciple`
    validator refuses construction. We surface that as a ``ValueError``
    rather than silently dropping the source — the failure mode is
    "I cannot make this contradiction-testable", which deserves a
    loud diagnostic.
    """

    statement = source.canonical_statement.strip()
    pid = canonical_principle_id(statement)
    return AbstractPrinciple(
        id=pid,
        canonical_statement=statement,
        scope=list(source.scope),
        domain=source.domain,
        mechanism=source.mechanism,
        preconditions=list(source.preconditions),
        expected_outcomes=list(source.expected_outcomes),
        failure_conditions=list(source.failure_conditions),
        negation_candidates=list(source.negation_candidates),
        supporting_case_ids=[],
        provenance=[
            PrincipleProvenance(
                chunk_id=source.chunk_id,
                source_quote=source.source_quote,
                case_id=None,
                extracted_from="abstract_only",
            )
        ],
        transfer_risk=source.transfer_risk or TransferRisk(),
        status=PrincipleStatus.CANDIDATE,
    )


# ── Abstractor ───────────────────────────────────────────────────────────────


class PrincipleAbstractor:
    """Glue between case extractions and the transfer graph.

    Usage::

        abstractor = PrincipleAbstractor()
        result = abstractor.abstract(
            extractions=[extraction_a, extraction_b],
            abstract_only_sources=[abstract_source],
            bounding_links=[BoundingCaseLink(...)],
            contradicting_links=[ContradictingCaseLink(...)],
        )
        graph_json = result.graph.to_json()

    The class itself is stateless; the caller is responsible for
    deciding which case extractions and overrides are in scope for a
    single pass. This makes the abstractor easy to compose into the
    Round 18 prompt batch without smuggling shared state.
    """

    def abstract(
        self,
        *,
        extractions: Iterable[CaseStudyExtraction] = (),
        abstract_only_sources: Iterable[AbstractOnlySource] = (),
        bounding_links: Iterable[BoundingCaseLink] = (),
        contradicting_links: Iterable[ContradictingCaseLink] = (),
    ) -> PrincipleAbstractionResult:
        graph = TransferGraph()
        skipped: list[AbstractPrincipleLink] = []

        # 1. Case-derived principles. Process in a deterministic order
        #    (by case id) so two runs over the same logical inputs in
        #    different insertion order produce byte-identical
        #    serialization. ``mechanism``, ``expected_outcomes``, and
        #    derived ``failure_conditions`` depend on the first case
        #    to instantiate a principle; the sort ensures "first" is
        #    a function of the data, not the caller's iteration order.
        sorted_cases: list[tuple[str, EmpiricalCaseStudy]] = []
        for extraction in extractions:
            chunk_id = extraction.chunk_id
            for case in extraction.cases:
                effective_chunk = chunk_id or case.source_span.chunk_id
                sorted_cases.append((effective_chunk, case))
        sorted_cases.sort(key=lambda pair: pair[1].id)

        for chunk_id, case in sorted_cases:
            graph.add_case(case.id)
            for link in case.linked_principles:
                principle = build_principle_from_link(
                    case=case,
                    chunk_id=chunk_id,
                    link=link,
                )
                if principle is None:
                    skipped.append(link)
                    continue
                merged = graph.add_principle(principle)
                # ``add_principle`` merges supporting_case_ids; we
                # still need the edge so the graph traversal works.
                graph.add_edge(
                    TransferEdge(
                        source_id=case.id,
                        target_id=merged.id,
                        kind=TransferEdgeKind.CASE_INSTANTIATES,
                        rationale=link.transfer_conditions,
                    )
                )

        # 2. Abstract-only sources.
        for src in abstract_only_sources:
            principle = build_principle_from_abstract_source(src)
            graph.add_principle(principle)
            # No CASE_INSTANTIATES edge: the provenance is the
            # ``extracted_from="abstract_only"`` provenance entry.

        # 3. Bounding case links.
        for bound in bounding_links:
            graph.add_case(bound.case_id)
            existing = graph._find_principle(bound.principle_id)
            if existing is None:
                # The graph should already contain the principle this
                # bound applies to; silently dropping would mask the
                # bug. Raise loud.
                raise ValueError(
                    f"BoundingCaseLink references unknown principle {bound.principle_id!r}"
                )
            if bound.case_id not in existing.bounding_case_ids:
                existing.bounding_case_ids = sorted(
                    set(existing.bounding_case_ids) | {bound.case_id}
                )
            graph.add_edge(
                TransferEdge(
                    source_id=bound.case_id,
                    target_id=bound.principle_id,
                    kind=TransferEdgeKind.CASE_BOUNDS,
                    rationale=bound.rationale,
                )
            )

        # 4. Contradicting case links.
        for contra in contradicting_links:
            graph.add_case(contra.case_id)
            existing = graph._find_principle(contra.principle_id)
            if existing is None:
                raise ValueError(
                    f"ContradictingCaseLink references unknown principle {contra.principle_id!r}"
                )
            if contra.case_id not in existing.contradicting_case_ids:
                existing.contradicting_case_ids = sorted(
                    set(existing.contradicting_case_ids) | {contra.case_id}
                )
            graph.add_edge(
                TransferEdge(
                    source_id=contra.case_id,
                    target_id=contra.principle_id,
                    kind=TransferEdgeKind.CASE_CONTRADICTS,
                    rationale=contra.rationale,
                )
            )

        # 5. Recompute confidence / status for every principle now that
        #    all supporting / bounding / contradicting links are known.
        for principle in graph.principles:
            self._recompute_calibration(principle)

        return PrincipleAbstractionResult(
            graph=graph, principles=list(graph.principles), skipped_links=skipped
        )

    # ── Calibration ──────────────────────────────────────────────────────

    def _recompute_calibration(self, principle: AbstractPrinciple) -> None:
        supporting = len(principle.supporting_case_ids)
        contradicting = len(principle.contradicting_case_ids)
        bounding = len(principle.bounding_case_ids)
        # Domain breadth: count distinct ``scope`` entries — the
        # abstractor seeds scope from case.domain, so distinct domains
        # show up here when the same principle is supported by cases
        # from different fields.
        domain_breadth = len({s for s in principle.scope if s})

        band, score = _confidence_band_for(
            supporting=supporting,
            contradicting=contradicting,
            bounding=bounding,
            domain_breadth=domain_breadth,
        )
        principle.confidence = ConfidenceCalibration(
            band=band,
            score=score,
            supporting_case_count=supporting,
            contradicting_case_count=contradicting,
            bounding_case_count=bounding,
            domain_breadth=domain_breadth,
            notes=principle.confidence.notes,
        )
        principle.status = _status_for(
            supporting=supporting,
            contradicting=contradicting,
            bounding=bounding,
        )

    # ── Convenience for callers that already have a graph ────────────────

    def extend_principle_with_case(
        self,
        *,
        graph: TransferGraph,
        case: EmpiricalCaseStudy,
        chunk_id: str,
        link: AbstractPrincipleLink,
    ) -> Optional[AbstractPrinciple]:
        """Add a case to an existing graph as a supporting link.

        Returns the merged :class:`AbstractPrinciple`, or ``None`` if
        the link could not be made contradiction-testable.
        """

        principle = build_principle_from_link(
            case=case,
            chunk_id=chunk_id,
            link=link,
        )
        if principle is None:
            return None
        graph.add_case(case.id)
        merged = graph.add_principle(principle)
        # Re-merge scope so multi-domain seeds accumulate. The
        # ``add_principle`` path does not touch ``scope`` because
        # collapsing scopes blindly would risk renaming a principle
        # by promoting a narrow scope into a wider one; merging here
        # is opt-in.
        merged.scope = sorted(set(merged.scope) | set(principle.scope))
        graph.add_edge(
            TransferEdge(
                source_id=case.id,
                target_id=merged.id,
                kind=TransferEdgeKind.CASE_INSTANTIATES,
                rationale=link.transfer_conditions,
            )
        )
        self._recompute_calibration(merged)
        return merged
