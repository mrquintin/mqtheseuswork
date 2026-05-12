"""Typed schema for abstract, contradiction-testable principles.

The shapes here mirror what the §1 (Algorithmized Decision Making)
contract asks of principles when they are used as load-bearing inputs
to a decision trace: each principle must be addressable, falsifiable,
and traceable back to the source span it came from.

Key design choices:

- ``AbstractPrinciple.id`` is content-addressed (sha256 of the
  normalized canonical statement). Two extractors that arrive at the
  same canonical statement produce the same id, so cross-source
  convergence is detectable without a join key.
- ``failure_conditions`` and ``negation_candidates`` are *required*
  shape, not optional decoration: a principle with no stated way to
  fail is not contradiction-testable and is rejected at construction
  time (see :func:`AbstractPrinciple._needs_failure_or_negation`).
- ``confidence`` caps at ``REFINED`` here. Promotion to ``FIRM``
  belongs to :mod:`noosphere.distillation`, which already gates
  firm-level convictions on cross-domain breadth — not just example
  count.
- Provenance is preserved at three levels (chunk → case → principle)
  so a downstream consumer can answer "which verbatim source quote
  led to this principle?" without re-reading the corpus.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Identity ─────────────────────────────────────────────────────────────────


def normalize_principle_text(text: str) -> str:
    """Whitespace-stable, case-folded canonical form for hashing.

    Two extractors that quote a principle with cosmetic differences
    (line wraps, trailing punctuation, leading "that") must still hash
    to the same id; full lexical normalization would over-collapse
    distinct principles, so we only fold whitespace, casing, and
    trailing punctuation.
    """

    folded = " ".join((text or "").strip().lower().split())
    while folded.endswith((".", ",", ";", ":")):
        folded = folded[:-1].rstrip()
    return folded


def canonical_principle_id(canonical_statement: str) -> str:
    """Deterministic principle id from a canonical statement.

    Cases that link the same principle text converge on the same id;
    this is the only mechanism the abstractor uses to detect "two
    cases instantiate the same principle". Identifier collisions on
    near-identical statements are intentional: the abstractor is
    *trying* to collapse them.
    """

    norm = normalize_principle_text(canonical_statement)
    if not norm:
        raise ValueError("canonical_statement must be non-empty for id derivation")
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"prn_{digest[:24]}"


# ── Enums ────────────────────────────────────────────────────────────────────


class PrincipleStatus(str, Enum):
    """Lifecycle of an abstracted principle.

    ``CANDIDATE`` — proposed by a single case or abstract-only source;
        the default until at least one independent corroboration or
        bound is recorded.

    ``REFINED`` — at least one additional case has been linked
        (supporting, bounding, or contradicting). The principle is
        worth defending in writing.

    ``CONTRADICTED`` — at least one case explicitly contradicts the
        principle and that contradiction has not been resolved into a
        ``bounds`` relationship. The principle is *not* deleted; it
        is kept so future cases can rediscover the contradiction.

    ``BOUNDED`` — the principle has been refined by an explicit
        bounding case or by a ``BOUNDS`` edge from a sibling
        principle. The principle still holds, but only within the
        recorded scope.

    Promotion to firm-level conviction is intentionally *not* a value
    here: that decision belongs to ``noosphere.distillation`` and
    requires cross-domain breadth, not example count.
    """

    CANDIDATE = "candidate"
    REFINED = "refined"
    CONTRADICTED = "contradicted"
    BOUNDED = "bounded"


class PrincipleConfidence(str, Enum):
    """Coarse confidence band. Continuous score lives on
    :class:`ConfidenceCalibration`."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class TransferEdgeKind(str, Enum):
    """The kinds of edges allowed in the transfer graph.

    The set is intentionally small. The graph is *not* a knowledge
    graph for free-form annotation; it is the substrate the
    decision-making contract reads when it asks "does principle P
    transfer to event E, and which cases are relevant?".

    Case ↔ principle edges:

    - ``CASE_INSTANTIATES`` — a case supports the principle.
    - ``CASE_BOUNDS`` — a case narrows the scope under which the
      principle holds (it does not break the principle, but it
      records a boundary condition discovered empirically).
    - ``CASE_CONTRADICTS`` — a case directly contradicts the
      principle's predicted outcome under stated preconditions.
    - ``PRINCIPLE_PREDICTS`` — the principle was applied to predict
      this case (forward-looking; recorded when a forecast cites
      the principle).

    Principle ↔ principle edges:

    - ``PRINCIPLE_REFINES`` — A → B means A is a *narrower*
      specialization of B that holds under tighter preconditions.
    - ``PRINCIPLE_GENERALIZES`` — A → B means A is a *broader*
      generalization of B; the inverse of ``PRINCIPLE_REFINES``.
    - ``PRINCIPLE_CONTRADICTS`` — A and B make incompatible
      predictions under at least one overlapping precondition set.
    - ``PRINCIPLE_BOUNDS`` — A → B means A names a boundary
      condition for B (e.g. "B holds, but not when A obtains").
    """

    CASE_INSTANTIATES = "case_instantiates"
    CASE_BOUNDS = "case_bounds"
    CASE_CONTRADICTS = "case_contradicts"
    PRINCIPLE_PREDICTS = "principle_predicts"
    PRINCIPLE_REFINES = "principle_refines"
    PRINCIPLE_GENERALIZES = "principle_generalizes"
    PRINCIPLE_CONTRADICTS = "principle_contradicts"
    PRINCIPLE_BOUNDS = "principle_bounds"


# Edges whose ``source_id`` MUST be a case id and ``target_id`` a
# principle id. The abstractor uses this to type-check graph
# construction so a misplaced edge fails loudly instead of corrupting
# downstream traversal.
_CASE_TO_PRINCIPLE_EDGES = frozenset(
    {
        TransferEdgeKind.CASE_INSTANTIATES,
        TransferEdgeKind.CASE_BOUNDS,
        TransferEdgeKind.CASE_CONTRADICTS,
    }
)
_PRINCIPLE_TO_CASE_EDGES = frozenset({TransferEdgeKind.PRINCIPLE_PREDICTS})
_PRINCIPLE_TO_PRINCIPLE_EDGES = frozenset(
    {
        TransferEdgeKind.PRINCIPLE_REFINES,
        TransferEdgeKind.PRINCIPLE_GENERALIZES,
        TransferEdgeKind.PRINCIPLE_CONTRADICTS,
        TransferEdgeKind.PRINCIPLE_BOUNDS,
    }
)


# ── Sub-models ───────────────────────────────────────────────────────────────


class PrincipleProvenance(BaseModel):
    """Pointer from a principle back to its originating source spans.

    A single principle can have multiple provenance entries (one per
    case or abstract-only source it was drawn from). The abstractor
    preserves *all* of them: the principle id is content-addressed, so
    convergence by two extractors must be auditable.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = ""
    source_quote: str = ""
    case_id: Optional[str] = None
    extracted_from: str = "case"  # 'case' | 'abstract_only'

    @field_validator("extracted_from")
    @classmethod
    def _kind_known(cls, value: str) -> str:
        if value not in {"case", "abstract_only"}:
            raise ValueError("extracted_from must be 'case' or 'abstract_only'")
        return value


class FailureCondition(BaseModel):
    """A named circumstance under which the principle should fail.

    Failure conditions are part of the principle's *contract*: they
    describe what the world would have to look like for the principle
    to be falsified. Storing them up front turns later cases into
    test points — a case that satisfies a recorded failure condition
    is a candidate ``CASE_CONTRADICTS`` edge, not a surprise.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    detectable_signal: str = ""
    severity: PrincipleConfidence = PrincipleConfidence.MODERATE

    @field_validator("description")
    @classmethod
    def _description_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("FailureCondition.description must be non-empty")
        return value.strip()


class NegationCandidate(BaseModel):
    """An explicit alternative statement whose truth would refute the principle.

    The point is *not* to predict what evidence would look like; that
    is what :class:`FailureCondition` captures. A negation candidate
    is the *propositional* opposite — a sentence that, if defensible,
    means the principle is wrong as stated. The downstream
    contradiction-direction probe consumes these as anchor pairs.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str
    rationale: str = ""

    @field_validator("statement")
    @classmethod
    def _statement_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("NegationCandidate.statement must be non-empty")
        return value.strip()


class ConfidenceCalibration(BaseModel):
    """How confident the system is in the principle, and how that confidence
    was arrived at.

    Calibration is *not* a sample count: a single high-quality
    bounding case can move a principle's calibration substantially,
    while a dozen near-duplicate examples should not.
    """

    model_config = ConfigDict(extra="forbid")

    band: PrincipleConfidence = PrincipleConfidence.LOW
    score: float = 0.0
    supporting_case_count: int = 0
    contradicting_case_count: int = 0
    bounding_case_count: int = 0
    domain_breadth: int = 0
    notes: str = ""

    @field_validator("score")
    @classmethod
    def _score_in_unit(cls, value: float) -> float:
        if value != value:  # NaN
            raise ValueError("score must not be NaN")
        if value < 0.0 or value > 1.0:
            raise ValueError("score must be in [0, 1]")
        return float(value)


class TransferRisk(BaseModel):
    """Recorded reasons the principle might fail to transfer to a new case.

    These are not the same as :class:`FailureCondition`: a failure
    condition describes when the principle is *wrong*; a transfer
    risk describes when the principle might be *inapplicable* to a
    superficially similar case (domain shift, scale shift, actor
    composition change, regime change).
    """

    model_config = ConfigDict(extra="forbid")

    domain_shift: str = ""
    scale_shift: str = ""
    regime_shift: str = ""
    actor_composition_shift: str = ""
    notes: str = ""

    def is_empty(self) -> bool:
        return not any(
            (
                self.domain_shift.strip(),
                self.scale_shift.strip(),
                self.regime_shift.strip(),
                self.actor_composition_shift.strip(),
                self.notes.strip(),
            )
        )


# ── Principle ────────────────────────────────────────────────────────────────


class AbstractPrinciple(BaseModel):
    """A contradiction-testable principle abstracted from one or more cases.

    The shape encodes the §1 (Algorithmized Decision Making) contract's
    requirement that a principle be addressable, falsifiable, and
    traceable. ``id`` is content-addressed so two extractions of the
    same canonical statement converge; ``failure_conditions`` and
    ``negation_candidates`` make the principle contradiction-testable
    by construction; ``provenance`` preserves the source-span chain.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: str
    canonical_statement: str
    scope: list[str] = Field(default_factory=list)
    domain: str = ""
    mechanism: str = ""
    preconditions: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    failure_conditions: list[FailureCondition] = Field(default_factory=list)
    negation_candidates: list[NegationCandidate] = Field(default_factory=list)

    supporting_case_ids: list[str] = Field(default_factory=list)
    contradicting_case_ids: list[str] = Field(default_factory=list)
    bounding_case_ids: list[str] = Field(default_factory=list)

    provenance: list[PrincipleProvenance] = Field(default_factory=list)
    confidence: ConfidenceCalibration = Field(default_factory=ConfidenceCalibration)
    transfer_risk: TransferRisk = Field(default_factory=TransferRisk)
    status: PrincipleStatus = PrincipleStatus.CANDIDATE

    @field_validator("canonical_statement")
    @classmethod
    def _canonical_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical_statement must be non-empty")
        return value.strip()

    @model_validator(mode="after")
    def _needs_failure_or_negation(self) -> "AbstractPrinciple":
        """A principle that cannot be contradicted is not a principle.

        We require at least one of ``failure_conditions`` or
        ``negation_candidates``. This is enforced at construction time
        so a caller that builds an ``AbstractPrinciple`` from raw text
        without populating either field fails loudly rather than
        producing a principle that the contradiction engine cannot
        test.
        """

        if not self.failure_conditions and not self.negation_candidates:
            raise ValueError(
                "AbstractPrinciple must declare at least one failure_condition "
                "or negation_candidate so it is contradiction-testable"
            )
        return self

    @model_validator(mode="after")
    def _id_matches_canonical(self) -> "AbstractPrinciple":
        """Guard against externally-supplied ids drifting from the canonical
        statement. Two callers must converge on the same id for the same
        statement, or convergence detection silently breaks."""

        expected = canonical_principle_id(self.canonical_statement)
        if self.id != expected:
            raise ValueError(
                f"AbstractPrinciple.id ({self.id}) does not match the "
                f"content-addressed id of canonical_statement ({expected})"
            )
        return self


# ── Transfer graph ───────────────────────────────────────────────────────────


class TransferEdge(BaseModel):
    """One typed directed edge in the transfer graph."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    source_id: str
    target_id: str
    kind: TransferEdgeKind
    rationale: str = ""

    @field_validator("source_id", "target_id")
    @classmethod
    def _ids_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("edge endpoints must be non-empty")
        return value.strip()


class TransferGraph(BaseModel):
    """A serializable, contradiction-aware graph of principles and cases.

    Two design constraints matter for downstream consumers:

    1. Serialization is *stable*. ``to_dict`` emits nodes and edges
       in a deterministic order (id-sorted), so two runs that produce
       the same logical graph produce byte-identical JSON. This is
       what makes graph snapshots diffable.

    2. Edges are *typed* and *direction-checked*. Calling
       ``add_edge`` with a case id where a principle id is required
       raises immediately; this prevents the graph from silently
       acquiring undefined transfer semantics.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    principles: list[AbstractPrinciple] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    edges: list[TransferEdge] = Field(default_factory=list)

    # ── Node helpers ─────────────────────────────────────────────────────

    def add_principle(self, principle: AbstractPrinciple) -> AbstractPrinciple:
        existing = self._find_principle(principle.id)
        if existing is None:
            self.principles.append(principle)
            return principle
        # Merge supporting/contradicting/bounding sets so a re-add does
        # not lose links recorded between calls.
        existing.supporting_case_ids = sorted(
            set(existing.supporting_case_ids) | set(principle.supporting_case_ids)
        )
        existing.contradicting_case_ids = sorted(
            set(existing.contradicting_case_ids)
            | set(principle.contradicting_case_ids)
        )
        existing.bounding_case_ids = sorted(
            set(existing.bounding_case_ids) | set(principle.bounding_case_ids)
        )
        # Scope is unioned so that two cases from different domains
        # contributing the same canonical statement produce a
        # cross-domain principle (and trip the ``domain_breadth`` field
        # in the abstractor's calibration). Mechanism, preconditions,
        # and expected outcomes are left to the first contributor —
        # collapsing those across cases would silently rewrite the
        # principle's content.
        existing.scope = sorted(set(existing.scope) | set(principle.scope))
        # Append any provenance not already present, key by
        # (chunk_id, source_quote, case_id).
        seen = {
            (p.chunk_id, p.source_quote, p.case_id) for p in existing.provenance
        }
        for prov in principle.provenance:
            key = (prov.chunk_id, prov.source_quote, prov.case_id)
            if key not in seen:
                existing.provenance.append(prov)
                seen.add(key)
        return existing

    def add_case(self, case_id: str) -> None:
        if not case_id.strip():
            raise ValueError("case_id must be non-empty")
        if case_id not in self.case_ids:
            self.case_ids.append(case_id)

    def add_edge(self, edge: TransferEdge) -> TransferEdge:
        """Type-check and append an edge.

        The kind dictates whether the endpoints must be cases or
        principles; a misclassified endpoint is a programming error,
        not a data issue.
        """

        kind = (
            edge.kind
            if isinstance(edge.kind, TransferEdgeKind)
            else TransferEdgeKind(edge.kind)
        )
        if kind in _CASE_TO_PRINCIPLE_EDGES:
            if edge.source_id not in self.case_ids:
                raise ValueError(
                    f"edge {kind.value}: source_id must be a registered case id; "
                    f"got {edge.source_id!r}"
                )
            if self._find_principle(edge.target_id) is None:
                raise ValueError(
                    f"edge {kind.value}: target_id must be a registered "
                    f"principle id; got {edge.target_id!r}"
                )
        elif kind in _PRINCIPLE_TO_CASE_EDGES:
            if self._find_principle(edge.source_id) is None:
                raise ValueError(
                    f"edge {kind.value}: source_id must be a registered "
                    f"principle id; got {edge.source_id!r}"
                )
            if edge.target_id not in self.case_ids:
                raise ValueError(
                    f"edge {kind.value}: target_id must be a registered case "
                    f"id; got {edge.target_id!r}"
                )
        elif kind in _PRINCIPLE_TO_PRINCIPLE_EDGES:
            if self._find_principle(edge.source_id) is None:
                raise ValueError(
                    f"edge {kind.value}: source_id must be a registered "
                    f"principle id; got {edge.source_id!r}"
                )
            if self._find_principle(edge.target_id) is None:
                raise ValueError(
                    f"edge {kind.value}: target_id must be a registered "
                    f"principle id; got {edge.target_id!r}"
                )
        else:  # pragma: no cover - exhaustive enum check
            raise ValueError(f"unknown edge kind: {kind!r}")

        # De-duplicate exact-match edges (same endpoints + kind).
        for existing in self.edges:
            if (
                existing.source_id == edge.source_id
                and existing.target_id == edge.target_id
                and existing.kind == kind.value
            ):
                return existing
        self.edges.append(edge)
        return edge

    # ── Queries ──────────────────────────────────────────────────────────

    def principles_for_case(self, case_id: str) -> list[AbstractPrinciple]:
        ids = {
            e.target_id
            for e in self.edges
            if e.source_id == case_id and e.kind in {k.value for k in _CASE_TO_PRINCIPLE_EDGES}
        }
        return [p for p in self.principles if p.id in ids]

    def cases_for_principle(self, principle_id: str) -> list[str]:
        return sorted(
            {
                e.source_id
                for e in self.edges
                if e.target_id == principle_id
                and e.kind in {k.value for k in _CASE_TO_PRINCIPLE_EDGES}
            }
        )

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Stable, deterministic dict representation.

        Sort keys: principles by id; case ids alphabetic; edges by
        ``(source_id, target_id, kind)``. The serializer also sorts
        per-principle list fields (supporting_case_ids, etc.) so the
        output is byte-stable across runs that produce the same
        logical graph.
        """

        principles_sorted = sorted(self.principles, key=lambda p: p.id)
        principle_payload = []
        for p in principles_sorted:
            payload = p.model_dump(mode="json")
            for key in (
                "supporting_case_ids",
                "contradicting_case_ids",
                "bounding_case_ids",
                "scope",
                "preconditions",
                "expected_outcomes",
            ):
                payload[key] = sorted(payload.get(key, []))
            payload["provenance"] = sorted(
                payload.get("provenance", []),
                key=lambda prov: (
                    prov.get("case_id") or "",
                    prov.get("chunk_id", ""),
                    prov.get("source_quote", ""),
                ),
            )
            principle_payload.append(payload)

        edges_sorted = sorted(
            (e.model_dump(mode="json") for e in self.edges),
            key=lambda e: (e["source_id"], e["target_id"], e["kind"]),
        )

        return {
            "principles": principle_payload,
            "case_ids": sorted(self.case_ids),
            "edges": edges_sorted,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TransferGraph":
        return cls.model_validate(payload)

    # ── Internal ─────────────────────────────────────────────────────────

    def _find_principle(self, principle_id: str) -> Optional[AbstractPrinciple]:
        for p in self.principles:
            if p.id == principle_id:
                return p
        return None


def iter_unique_principles(
    principles: Iterable[AbstractPrinciple],
) -> list[AbstractPrinciple]:
    """De-duplicate principles by id, preserving first occurrence order.

    Convenience for callers that build a list of candidate
    ``AbstractPrinciple`` instances across multiple cases before
    constructing a graph.
    """

    seen: dict[str, AbstractPrinciple] = {}
    for p in principles:
        if p.id not in seen:
            seen[p.id] = p
    return list(seen.values())
