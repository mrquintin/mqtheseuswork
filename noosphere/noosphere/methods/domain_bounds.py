"""Domain Bounds — declarative, machine-checkable applicability bounds for
methods.

THE_META_METHOD criterion #5 (Domain Sensitivity) used to be evaluated by an
LLM judge with the prompt "does this seem in domain". That answer is fragile
and not auditable. This module replaces that with a declarative bound a
method registers up-front: a tag set, a set of anchor centroids in embedding
space (with an angular-cosine threshold), or a logical combination of the
two. The check is deterministic and emits a verdict in
{in_bounds, edge_case, out_of_bounds} together with a numeric margin so
downstream gates (MQS composite, refusal pipeline) can act on it.

Anchors are versioned. Re-curating creates a new ``AnchorRevision``; the
in-process bound never mutates an existing revision. Older conclusions
retain whatever verdict was produced by the anchors active at run time.

The angular cosine distance is the canonical metric here. The threshold
lives on the bound declaration, not as a global default — different methods
can have very different in-domain radii.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional, Sequence


Verdict = Literal["in_bounds", "edge_case", "out_of_bounds"]
Combinator = Literal["all", "any"]


# ── Distance ────────────────────────────────────────────────────────────────


def angular_cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Angular cosine distance in [0, 1].

    Defined as ``arccos(clamped_cosine_similarity) / pi``. We use angular
    rather than ``1 - cosine`` because angular is a true metric: monotonic
    in the actual angle between the vectors and stable under typical
    embedding norms. The result is always in [0, 1] regardless of input
    norms (we normalize internally).

    Returns 1.0 (maximum distance) when either vector is the zero vector,
    so an unfit input never accidentally passes a tight bound.
    """
    if len(a) != len(b):
        raise ValueError(
            f"angular_cosine_distance: dim mismatch ({len(a)} vs {len(b)})"
        )
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 1.0
    cos = dot / math.sqrt(na * nb)
    if cos > 1.0:
        cos = 1.0
    elif cos < -1.0:
        cos = -1.0
    return math.acos(cos) / math.pi


# ── Bound declarations ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TagBound:
    """A method is in-domain iff at least one of the conclusion's topic tags
    is one of these declared tags. Tags are matched case-insensitively after
    stripping; no fuzzy matching."""

    tags: tuple[str, ...]

    def normalized(self) -> tuple[str, ...]:
        return tuple(sorted({t.strip().lower() for t in self.tags if t.strip()}))


@dataclass(frozen=True)
class AnchorBound:
    """A method is in-domain iff at least one anchor centroid is within
    ``in_radius`` angular cosine distance. ``edge_radius`` (>= ``in_radius``)
    grants the softer ``edge_case`` verdict. Cross-model comparisons are
    refused."""

    anchors: tuple[tuple[float, ...], ...]
    embedding_model: str
    in_radius: float
    edge_radius: float
    revision_id: str

    def __post_init__(self) -> None:  # pragma: no cover - validation path
        if not self.anchors:
            raise ValueError("AnchorBound requires at least one anchor")
        if not (0.0 < self.in_radius <= 1.0):
            raise ValueError("in_radius must be in (0, 1]")
        if not (self.in_radius <= self.edge_radius <= 1.0):
            raise ValueError("edge_radius must be >= in_radius and <= 1")
        if not self.embedding_model:
            raise ValueError("embedding_model is required on AnchorBound")
        dim0 = len(self.anchors[0])
        for i, a in enumerate(self.anchors):
            if len(a) != dim0:
                raise ValueError(
                    f"AnchorBound: anchor {i} dim {len(a)} != dim0 {dim0}"
                )

    @property
    def dim(self) -> int:
        return len(self.anchors[0])


@dataclass(frozen=True)
class DomainBound:
    """A method's declared domain. May contain a tag bound, an anchor bound,
    or both. ``combinator`` controls how the two are combined when both are
    present:

      * ``"any"`` — pass if either side passes (default; the firm's safer
        default since either gate is sufficient evidence of in-domain)
      * ``"all"`` — pass only if both sides pass (strict intersection)

    A bound with neither side is forbidden — the loader rejects empty
    bounds."""

    tag_bound: Optional[TagBound] = None
    anchor_bound: Optional[AnchorBound] = None
    combinator: Combinator = "any"

    def __post_init__(self) -> None:
        if self.tag_bound is None and self.anchor_bound is None:
            raise ValueError(
                "DomainBound: must declare at least one of tag_bound or anchor_bound"
            )
        if self.combinator not in ("all", "any"):
            raise ValueError(f"unknown combinator: {self.combinator!r}")


# ── Deterministic loader ────────────────────────────────────────────────────


def load_domain_bound(data: Any) -> DomainBound:
    """Load a ``DomainBound`` from a dict, list, or another ``DomainBound``.

    Accepted shapes:

    * ``DomainBound`` instance — returned unchanged.
    * ``list[str]`` — interpreted as a pure ``TagBound``.
    * ``dict`` with one or more of:

        - ``tags``: list[str]
        - ``anchors``: list[list[float]]
        - ``embedding_model``: str (required when ``anchors`` is set)
        - ``in_radius``: float (required when ``anchors`` is set)
        - ``edge_radius``: float (defaults to ``in_radius * 1.25`` capped at 1.0)
        - ``revision_id``: str (defaults to a content hash of the anchors)
        - ``combinator``: ``"all"`` | ``"any"`` (default ``"any"``)

    The loader is deterministic: the same input dict produces an
    identical ``DomainBound`` (including the derived ``revision_id``).
    """
    if isinstance(data, DomainBound):
        return data
    if isinstance(data, list):
        # bare list of tags
        return DomainBound(tag_bound=TagBound(tags=tuple(str(t) for t in data)))
    if not isinstance(data, dict):
        raise TypeError(
            f"load_domain_bound: expected dict|list|DomainBound, got {type(data).__name__}"
        )

    tag_bound: Optional[TagBound] = None
    if data.get("tags"):
        tag_bound = TagBound(tags=tuple(str(t) for t in data["tags"]))

    anchor_bound: Optional[AnchorBound] = None
    if data.get("anchors"):
        anchors_raw = data["anchors"]
        anchors = tuple(tuple(float(x) for x in row) for row in anchors_raw)
        model = data.get("embedding_model")
        if not model:
            raise ValueError(
                "load_domain_bound: 'embedding_model' is required when 'anchors' is set"
            )
        in_radius = data.get("in_radius")
        if in_radius is None:
            raise ValueError(
                "load_domain_bound: 'in_radius' is required when 'anchors' is set"
            )
        in_radius = float(in_radius)
        edge_radius = data.get("edge_radius")
        if edge_radius is None:
            edge_radius = min(1.0, in_radius * 1.25)
        edge_radius = float(edge_radius)
        revision_id = data.get("revision_id") or _anchor_revision_id(
            model, anchors, in_radius, edge_radius
        )
        anchor_bound = AnchorBound(
            anchors=anchors,
            embedding_model=str(model),
            in_radius=in_radius,
            edge_radius=edge_radius,
            revision_id=str(revision_id),
        )

    combinator: Combinator = data.get("combinator", "any")
    return DomainBound(
        tag_bound=tag_bound, anchor_bound=anchor_bound, combinator=combinator
    )


def _anchor_revision_id(
    model: str,
    anchors: tuple[tuple[float, ...], ...],
    in_radius: float,
    edge_radius: float,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "anchors": [list(a) for a in anchors],
            "in_radius": round(in_radius, 8),
            "edge_radius": round(edge_radius, 8),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "rev_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Verdict ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DomainVerdict:
    """Result of checking a conclusion against a method's bound.

    ``margin`` is signed:
      * ``in_bounds`` → margin = ``in_radius - distance`` (positive)
      * ``edge_case`` → margin = ``edge_radius - distance`` (positive but
        smaller than the in_radius gap)
      * ``out_of_bounds`` → margin = ``edge_radius - distance`` (negative)

    For pure tag verdicts the margin is binary (1.0 or -1.0). When both
    sides participate the verdict reports the worse (or better, depending
    on combinator) numeric margin.
    """

    status: Verdict
    margin: float
    reason: str
    embedding_model: Optional[str] = None
    anchor_revision_id: Optional[str] = None
    matched_anchor_index: Optional[int] = None
    matched_tags: tuple[str, ...] = field(default_factory=tuple)
    distance: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "margin": round(float(self.margin), 6),
            "reason": self.reason,
            "embedding_model": self.embedding_model,
            "anchor_revision_id": self.anchor_revision_id,
            "matched_anchor_index": self.matched_anchor_index,
            "matched_tags": list(self.matched_tags),
            "distance": (
                None if self.distance is None else round(float(self.distance), 6)
            ),
        }


class EmbeddingModelMismatch(ValueError):
    """Raised when an anchor bound is checked against an embedding produced
    by a different model. We refuse cross-model comparisons rather than
    silently producing a meaningless distance."""


# ── Checks ──────────────────────────────────────────────────────────────────


def check_tags(bound: TagBound, tags: Iterable[str]) -> DomainVerdict:
    accepted = set(bound.normalized())
    matched = sorted(
        {t.strip().lower() for t in tags if t and t.strip()} & accepted
    )
    if matched:
        return DomainVerdict(
            status="in_bounds",
            margin=1.0,
            reason=f"matched tags: {', '.join(matched)}",
            matched_tags=tuple(matched),
        )
    return DomainVerdict(
        status="out_of_bounds",
        margin=-1.0,
        reason=(
            "no conclusion tag in {" + ", ".join(sorted(accepted)) + "}"
        ),
    )


def check_anchor(
    bound: AnchorBound,
    *,
    embedding: Sequence[float],
    embedding_model: str,
) -> DomainVerdict:
    if embedding_model != bound.embedding_model:
        raise EmbeddingModelMismatch(
            f"anchor bound was built with embedding model "
            f"{bound.embedding_model!r}; cannot check against an embedding "
            f"produced by {embedding_model!r}"
        )
    if len(embedding) != bound.dim:
        raise EmbeddingModelMismatch(
            f"embedding dim {len(embedding)} != anchor dim {bound.dim}"
        )

    best_d = math.inf
    best_i = -1
    for i, anchor in enumerate(bound.anchors):
        d = angular_cosine_distance(embedding, anchor)
        if d < best_d:
            best_d = d
            best_i = i

    if best_d <= bound.in_radius:
        status: Verdict = "in_bounds"
        margin = bound.in_radius - best_d
    elif best_d <= bound.edge_radius:
        status = "edge_case"
        margin = bound.edge_radius - best_d
    else:
        status = "out_of_bounds"
        margin = bound.edge_radius - best_d  # negative

    return DomainVerdict(
        status=status,
        margin=margin,
        reason=(
            f"nearest anchor #{best_i} at angular distance {best_d:.4f} "
            f"(in_radius={bound.in_radius}, edge_radius={bound.edge_radius})"
        ),
        embedding_model=bound.embedding_model,
        anchor_revision_id=bound.revision_id,
        matched_anchor_index=best_i,
        distance=best_d,
    )


def check_domain(
    bound: DomainBound,
    *,
    embedding: Optional[Sequence[float]] = None,
    embedding_model: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> DomainVerdict:
    """Apply the bound. Routes to the relevant single-side check or
    combines the two sides per ``bound.combinator``.

    When the bound has an anchor side but the caller passed no embedding,
    the anchor side is treated as ``out_of_bounds`` (we cannot prove
    in-domain without the embedding the bound was declared against)."""
    tag_v: Optional[DomainVerdict] = None
    anc_v: Optional[DomainVerdict] = None

    if bound.tag_bound is not None:
        tag_v = check_tags(bound.tag_bound, tags or [])

    if bound.anchor_bound is not None:
        if embedding is None or embedding_model is None:
            anc_v = DomainVerdict(
                status="out_of_bounds",
                margin=-1.0,
                reason="no embedding provided; anchor bound cannot be checked",
                embedding_model=bound.anchor_bound.embedding_model,
                anchor_revision_id=bound.anchor_bound.revision_id,
            )
        else:
            anc_v = check_anchor(
                bound.anchor_bound,
                embedding=embedding,
                embedding_model=embedding_model,
            )

    if tag_v is not None and anc_v is None:
        return tag_v
    if anc_v is not None and tag_v is None:
        return anc_v
    assert tag_v is not None and anc_v is not None  # for type checker

    return _combine(tag_v, anc_v, bound.combinator)


# Status order: in_bounds (best) > edge_case > out_of_bounds (worst).
_ORDER: dict[Verdict, int] = {
    "in_bounds": 2,
    "edge_case": 1,
    "out_of_bounds": 0,
}


def _combine(a: DomainVerdict, b: DomainVerdict, combinator: Combinator) -> DomainVerdict:
    """Combine two verdicts under ``"any"`` (better wins) or ``"all"``
    (worse wins). The carried metadata follows the verdict that drives
    the decision."""
    if combinator == "any":
        winner = a if _ORDER[a.status] >= _ORDER[b.status] else b
        loser = b if winner is a else a
        reason = f"any: {winner.reason}; (other side: {loser.reason})"
    else:
        winner = a if _ORDER[a.status] <= _ORDER[b.status] else b
        loser = b if winner is a else a
        reason = f"all: gated by {winner.reason}; (other side: {loser.reason})"
    return DomainVerdict(
        status=winner.status,
        margin=winner.margin,
        reason=reason,
        embedding_model=winner.embedding_model,
        anchor_revision_id=winner.anchor_revision_id,
        matched_anchor_index=winner.matched_anchor_index,
        matched_tags=winner.matched_tags,
        distance=winner.distance,
    )


# ── Refusal pipeline ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DomainRefusal:
    """Sentinel record emitted when a method is invoked outside its
    declared domain. The orchestrator returns this in place of method
    output and (when wired) writes a ledger entry mirroring the same
    fields so the refusal is auditable.

    ``edge_case`` does NOT trigger a refusal — only ``out_of_bounds``
    does. Edge cases produce a soft warning recorded alongside a normal
    method run; downstream MQS treats them as a 0.4 ceiling on
    ``domain_sensitivity`` rather than a hard zero.
    """

    method_name: str
    method_version: str
    conclusion_id: str
    verdict: DomainVerdict
    refused_at_iso: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "domain_refusal",
            "method_name": self.method_name,
            "method_version": self.method_version,
            "conclusion_id": self.conclusion_id,
            "refused_at": self.refused_at_iso,
            "verdict": self.verdict.to_dict(),
        }


def refuse_out_of_bounds(
    *,
    method_name: str,
    method_version: str,
    method_id: Optional[str],
    conclusion_id: str,
    verdict: DomainVerdict,
    ledger: Any = None,
    actor: Any = None,
    context: Any = None,
) -> DomainRefusal:
    """Build a ``DomainRefusal`` and (when ``ledger``, ``actor``, and
    ``context`` are all provided) append a ledger entry recording the
    refusal. Only ``out_of_bounds`` verdicts route through here — other
    statuses are programmer errors and raise ``ValueError``."""
    from datetime import datetime, timezone

    if verdict.status != "out_of_bounds":
        raise ValueError(
            f"refuse_out_of_bounds called with non-refusing verdict {verdict.status!r}"
        )
    refusal = DomainRefusal(
        method_name=method_name,
        method_version=method_version,
        conclusion_id=conclusion_id,
        verdict=verdict,
        refused_at_iso=datetime.now(timezone.utc).isoformat(),
    )

    if ledger is not None and actor is not None and context is not None:
        payload = json.dumps(refusal.to_dict(), sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        try:
            ledger.append(
                actor=actor,
                method_id=method_id,
                inputs_hash=payload_hash,
                outputs_hash=payload_hash,
                inputs_ref=f"domain_refusal:{method_name}@{method_version}",
                outputs_ref=f"domain_refusal:{conclusion_id}",
                context=context,
            )
        except Exception:
            # The ledger is append-only and signed; a write failure must not
            # silently swallow the refusal. Raise so the orchestrator can
            # decide whether to retry or escalate.
            raise

    return refusal


__all__ = [
    "AnchorBound",
    "Combinator",
    "DomainBound",
    "DomainRefusal",
    "DomainVerdict",
    "EmbeddingModelMismatch",
    "TagBound",
    "Verdict",
    "angular_cosine_distance",
    "check_anchor",
    "check_domain",
    "check_tags",
    "load_domain_bound",
    "refuse_out_of_bounds",
]
