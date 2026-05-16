"""Oracle / synthesis surface — backs the founder's ``/oracle`` page.

The Oracle is the founder-facing query layer that pulls firm material
through the synthesizer to answer a question. Prompt 09 adds a
``provenance_filter`` to every Oracle / synthesis call: the founder
picks which buckets of source material to include and what weight to
assign each. The defaults reflect the founder's directive — pull from
PROPRIETARY + ENDORSED_EXTERNAL, weight proprietary 2× higher,
STUDIED / OPPOSING must be explicitly opted in.

The endpoints here are read-only and per-tenant. They return source
counts for the UI checkbox labels and execute a filtered Oracle query
that records *which provenance kinds were active and with what
weights* on the response — so a memo's reasoning is auditable later.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from current_events_api.deps import enforce_read_rate_limit, get_store
from noosphere.models import (
    PROVENANCE_KIND_VALUES,
    ProvenanceKind,
    coerce_provenance,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/oracle", tags=["oracle"])


# ── ProvenanceFilter schema (prompt 09) ─────────────────────────────────────


class ProvenanceFilter(BaseModel):
    """Which provenance buckets to query and how to weight them.

    Defaults reflect the founder's directive in prompt 09:

    * include PROPRIETARY (default ON) and ENDORSED_EXTERNAL (default ON),
    * exclude STUDIED_EXTERNAL and OPPOSING_EXTERNAL (off by default),
    * weight proprietary 2.0×, endorsed 1.0×, studied 0.5×, opposing 0.1×.

    The synthesizer + cite-and-rerank pipeline both consume this exact
    shape; the Oracle UI renders the matching four checkboxes plus the
    weighting sliders (collapsed by default).
    """

    include_proprietary: bool = True
    include_endorsed_external: bool = True
    include_studied_external: bool = False
    include_opposing_external: bool = False
    proprietary_weight: float = Field(default=2.0, ge=0.0, le=10.0)
    endorsed_external_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    studied_external_weight: float = Field(default=0.5, ge=0.0, le=10.0)
    opposing_external_weight: float = Field(default=0.1, ge=0.0, le=10.0)

    def included_kinds(self) -> list[ProvenanceKind]:
        out: list[ProvenanceKind] = []
        if self.include_proprietary:
            out.append(ProvenanceKind.PROPRIETARY)
        if self.include_endorsed_external:
            out.append(ProvenanceKind.ENDORSED_EXTERNAL)
        if self.include_studied_external:
            out.append(ProvenanceKind.STUDIED_EXTERNAL)
        if self.include_opposing_external:
            out.append(ProvenanceKind.OPPOSING_EXTERNAL)
        return out

    def weight_for(self, kind: ProvenanceKind) -> float:
        return {
            ProvenanceKind.PROPRIETARY: self.proprietary_weight,
            ProvenanceKind.ENDORSED_EXTERNAL: self.endorsed_external_weight,
            ProvenanceKind.STUDIED_EXTERNAL: self.studied_external_weight,
            ProvenanceKind.OPPOSING_EXTERNAL: self.opposing_external_weight,
        }[kind]

    def weights_dict(self) -> dict[str, float]:
        """Return the per-kind weight map keyed by enum value string.

        Used by the synthesizer to record on each memo *which* weights
        were active when it ran — so a memo's reasoning is reproducible.
        """
        return {k.value: self.weight_for(k) for k in self.included_kinds()}


class OracleQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    provenance_filter: ProvenanceFilter = Field(default_factory=ProvenanceFilter)
    limit: int = Field(default=20, ge=1, le=200)


class OracleSource(BaseModel):
    id: str
    title: str
    provenance: str
    weight: float


class OracleAnswer(BaseModel):
    """The shape returned by ``POST /v1/oracle/ask``.

    Carries the *active* provenance filter so callers (UI, memos) can
    surface "this answer was synthesized from {kinds} with weights
    {weights}" without re-deriving it.
    """

    question: str
    sources: list[OracleSource]
    active_provenance_kinds: list[str]
    active_weights: dict[str, float]
    total_sources_considered: int


class ProvenanceCount(BaseModel):
    provenance: str
    count: int


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/provenance-counts", response_model=list[ProvenanceCount])
def provenance_counts(
    store: Annotated[Store, Depends(get_store)],
    _: Annotated[None, Depends(enforce_read_rate_limit)],
) -> list[ProvenanceCount]:
    """Source counts for the Oracle UI checkboxes.

    Every checkbox shows a count of available sources of that
    provenance — that's how the founder sees what they're querying.
    Always returns one row per kind, even if the count is zero, so the
    UI can render a stable four-row layout.
    """
    counts = store.count_artifacts_by_provenance()
    return [
        ProvenanceCount(provenance=k, count=int(counts.get(k, 0)))
        for k in PROVENANCE_KIND_VALUES
    ]


@router.post("/ask", response_model=OracleAnswer)
def ask(
    body: OracleQuery,
    store: Annotated[Store, Depends(get_store)],
    _: Annotated[None, Depends(enforce_read_rate_limit)],
) -> OracleAnswer:
    """Run a filtered Oracle query.

    The provenance filter (a) restricts which artifacts contribute and
    (b) records the weights on the response so the founder can audit
    later. The synthesizer multiplies each source's contribution by
    ``weight_for(provenance)`` before composing the answer; weights of
    zero are equivalent to excluding the kind but the filter shape is
    the canonical way to express "off".
    """
    pfilter = body.provenance_filter
    kinds = pfilter.included_kinds()
    if not kinds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provenance_filter must include at least one kind",
        )

    kind_values = [k.value for k in kinds]
    artifacts = []
    for kv in kind_values:
        artifacts.extend(
            store.list_artifacts_by_provenance(kv, limit=body.limit)
        )

    # Stable order: weight desc, then created_at desc (already so from
    # list_artifacts_by_provenance).
    sources = [
        OracleSource(
            id=a.id,
            title=a.title or a.uri or a.id,
            provenance=coerce_provenance(a.provenance).value,
            weight=pfilter.weight_for(coerce_provenance(a.provenance)),
        )
        for a in artifacts
    ]
    sources.sort(key=lambda s: (-s.weight, s.id))
    sources = sources[: body.limit]

    return OracleAnswer(
        question=body.question,
        sources=sources,
        active_provenance_kinds=[k.value for k in kinds],
        active_weights=pfilter.weights_dict(),
        total_sources_considered=len(artifacts),
    )
