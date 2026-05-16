"""Edge extractors for the cross-source knowledge graph (prompt 13).

One function per :class:`~noosphere.models.KGEdgeKind`. Each extractor
takes the store and a node-index keyed by ``(KGNodeKind, ref)`` so it
can map authoritative-table ids to graph node ids. Each yields
:class:`~noosphere.models.KGEdge` objects.

Extractors are intentionally read-only — they do not mutate the
authoritative tables. If a referenced node is missing the edge is
skipped (and counted in the builder's notes), never auto-created with
fabricated attributes.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from noosphere.models import (
    KGEdge,
    KGEdgeKind,
    KGNodeKind,
)


NodeIndex = dict[tuple[KGNodeKind, str], str]


def _edge(
    src: str,
    dst: str,
    kind: KGEdgeKind,
    *,
    weight: float = 1.0,
    attrs: Optional[dict[str, Any]] = None,
) -> KGEdge:
    return KGEdge(
        id=f"kgedge_{uuid4().hex[:24]}",
        src=src,
        dst=dst,
        kind=kind,
        weight=weight,
        attrs=attrs or {},
    )


def _node_id(
    index: NodeIndex, kind: KGNodeKind, ref: str
) -> Optional[str]:
    if not ref:
        return None
    return index.get((kind, str(ref)))


# ── DERIVED_FROM ────────────────────────────────────────────────────


def extract_derived_from(
    *,
    principles: Iterable[Any],
    index: NodeIndex,
) -> list[KGEdge]:
    """principle -> source it was derived from.

    Reads the principle's ``source_artifact_id`` / ``source_artifact``
    pointer (whichever shape is populated). Conclusion rows with the
    principle-shape contract carry the artifact id on the conclusion;
    the canonical Principle in v1 carries no FK so the edge is only
    surfaced when an explicit ``source_artifact`` attribute is set.
    """
    out: list[KGEdge] = []
    for p in principles:
        src_id = _node_id(index, KGNodeKind.PRINCIPLE, str(getattr(p, "id", "")))
        if src_id is None:
            continue
        source_ref = (
            getattr(p, "source_artifact_id", None)
            or getattr(p, "source_artifact", None)
            or ""
        )
        if not source_ref:
            continue
        dst_id = _node_id(index, KGNodeKind.SOURCE, str(source_ref))
        if dst_id is None:
            continue
        out.append(_edge(src_id, dst_id, KGEdgeKind.DERIVED_FROM))
    return out


# ── INVOKES ─────────────────────────────────────────────────────────


def extract_invokes(
    *,
    algorithms: Iterable[Any],
    index: NodeIndex,
) -> list[KGEdge]:
    """algorithm -> each principle it invokes."""
    out: list[KGEdge] = []
    for a in algorithms:
        src_id = _node_id(index, KGNodeKind.ALGORITHM, str(getattr(a, "id", "")))
        if src_id is None:
            continue
        for pid in getattr(a, "source_principle_ids", []) or []:
            dst_id = _node_id(index, KGNodeKind.PRINCIPLE, str(pid))
            if dst_id is None:
                continue
            out.append(_edge(src_id, dst_id, KGEdgeKind.INVOKES))
    return out


# ── CONTRADICTS ─────────────────────────────────────────────────────


def extract_contradicts(
    *,
    lifecycles: Iterable[Any],
    contradiction_rows_by_id: dict[str, Any],
    index: NodeIndex,
    exclude_statuses: tuple[str, ...] = ("DISPUTED_AS_ERROR",),
) -> list[KGEdge]:
    """principle_a -> principle_b via contradiction lifecycle.

    Skips lifecycles in ``exclude_statuses`` (default: DISPUTED_AS_ERROR
    only, per prompt). Edge weight carries the latest contradiction
    score from the linked contradiction_result row, or 0 if unknown.
    """
    out: list[KGEdge] = []
    for lc in lifecycles:
        status = str(getattr(lc, "current_status", "") or "")
        if status in exclude_statuses:
            continue
        contradiction_id = str(getattr(lc, "contradiction_id", "") or "")
        contradiction_row = contradiction_rows_by_id.get(contradiction_id)
        if contradiction_row is None:
            continue
        a_ref = str(getattr(contradiction_row, "principle_a_id", "") or "")
        b_ref = str(getattr(contradiction_row, "principle_b_id", "") or "")
        a_id = _node_id(index, KGNodeKind.PRINCIPLE, a_ref)
        b_id = _node_id(index, KGNodeKind.PRINCIPLE, b_ref)
        if a_id is None or b_id is None:
            continue
        score = float(getattr(contradiction_row, "score", 0.0) or 0.0)
        out.append(
            _edge(
                a_id,
                b_id,
                KGEdgeKind.CONTRADICTS,
                weight=score,
                attrs={
                    "status": status,
                    "contradiction_id": contradiction_id,
                    "axis": str(getattr(contradiction_row, "axis", "") or ""),
                },
            )
        )
    return out


# ── SUPPORTS ────────────────────────────────────────────────────────


def extract_supports(
    *,
    manual_supports: Iterable[dict[str, Any]],
    index: NodeIndex,
    llm_supports: Optional[Iterable[dict[str, Any]]] = None,
    confidence_threshold: float = 0.7,
) -> list[KGEdge]:
    """src -> dst SUPPORTS edges.

    ``manual_supports`` is a list of ``{src_kind, src_ref, dst_kind,
    dst_ref, confidence, source}`` dicts where source is "MANUAL".

    ``llm_supports`` is an optional iterable of the same shape produced
    by a scheduled LLM extractor; only those whose confidence ≥
    ``confidence_threshold`` are admitted (per prompt: "high confidence
    threshold").
    """
    out: list[KGEdge] = []
    sources: list[Iterable[dict[str, Any]]] = [manual_supports]
    if llm_supports is not None:
        sources.append(llm_supports)
    for batch in sources:
        for row in batch:
            try:
                src_kind = KGNodeKind(row["src_kind"])
                dst_kind = KGNodeKind(row["dst_kind"])
            except Exception:
                continue
            confidence = float(row.get("confidence", 0.0) or 0.0)
            src_provenance = str(row.get("source", "MANUAL") or "MANUAL").upper()
            if src_provenance != "MANUAL" and confidence < confidence_threshold:
                continue
            src_id = _node_id(index, src_kind, str(row.get("src_ref", "")))
            dst_id = _node_id(index, dst_kind, str(row.get("dst_ref", "")))
            if src_id is None or dst_id is None:
                continue
            out.append(
                _edge(
                    src_id,
                    dst_id,
                    KGEdgeKind.SUPPORTS,
                    weight=confidence,
                    attrs={"source": src_provenance},
                )
            )
    return out


# ── APPLIES_TO ──────────────────────────────────────────────────────


def extract_applies_to(
    *,
    principles: Iterable[Any],
    topics: Iterable[Any],
    index: NodeIndex,
) -> list[KGEdge]:
    """principle -> topic by string-match on principle.domain_of_applicability.

    The match is intentionally simple — substring containment between
    the principle's domain field and the topic label/name (case-fold).
    A heavier semantic matcher would belong in the topics module.
    """
    topic_list = list(topics)
    out: list[KGEdge] = []
    for p in principles:
        src_id = _node_id(index, KGNodeKind.PRINCIPLE, str(getattr(p, "id", "")))
        if src_id is None:
            continue
        domain = str(getattr(p, "domain_of_applicability", "") or "").strip().lower()
        if not domain:
            continue
        for t in topic_list:
            label = (
                str(getattr(t, "label", "") or "")
                or str(getattr(t, "name", "") or "")
            )
            if not label:
                continue
            label_l = label.lower()
            if label_l in domain or any(
                tok and tok in domain for tok in label_l.split()
            ):
                dst_id = _node_id(
                    index, KGNodeKind.TOPIC, str(getattr(t, "id", ""))
                )
                if dst_id is None:
                    continue
                out.append(_edge(src_id, dst_id, KGEdgeKind.APPLIES_TO))
    return out


# ── PREDICTS ────────────────────────────────────────────────────────


def extract_predicts(
    *,
    algorithms: Iterable[Any],
    topics: Iterable[Any],
    index: NodeIndex,
) -> list[KGEdge]:
    """algorithm -> topic via output schema + topic name match.

    The algorithm's output description and field names are scanned for
    occurrences of a topic name. This is a coarse signal — the operator
    surface lets a founder demote spurious matches.
    """
    topic_list = list(topics)
    out: list[KGEdge] = []
    for a in algorithms:
        src_id = _node_id(index, KGNodeKind.ALGORITHM, str(getattr(a, "id", "")))
        if src_id is None:
            continue
        output = getattr(a, "output", None)
        if output is None:
            continue
        blob_parts: list[str] = [
            str(getattr(output, "name", "") or ""),
            str(getattr(output, "description", "") or ""),
        ]
        for fld in getattr(output, "fields", []) or []:
            if isinstance(fld, dict):
                blob_parts.append(str(fld.get("name", "")))
            else:
                blob_parts.append(str(getattr(fld, "name", "")))
        blob = " ".join(p for p in blob_parts if p).lower()
        if not blob:
            continue
        for t in topic_list:
            label = (
                str(getattr(t, "label", "") or "")
                or str(getattr(t, "name", "") or "")
            ).lower()
            if not label:
                continue
            if label in blob:
                dst_id = _node_id(
                    index, KGNodeKind.TOPIC, str(getattr(t, "id", ""))
                )
                if dst_id is None:
                    continue
                out.append(_edge(src_id, dst_id, KGEdgeKind.PREDICTS))
    return out


# ── CITES ───────────────────────────────────────────────────────────


def extract_cites(
    *,
    memos: Iterable[Any],
    index: NodeIndex,
) -> list[KGEdge]:
    """memo -> principle / algorithm / source via governing+observed ids.

    Memos carry both ``governing_principle_ids`` (principles) and
    ``observed_input_ids`` (which may be artifact ids or algorithm
    invocation ids depending on the producer); we try the SOURCE
    lookup first and fall back to ALGORITHM.
    """
    out: list[KGEdge] = []
    for memo in memos:
        src_id = _node_id(index, KGNodeKind.MEMO, str(getattr(memo, "id", "")))
        if src_id is None:
            continue
        for pid in getattr(memo, "governing_principle_ids", []) or []:
            dst_id = _node_id(index, KGNodeKind.PRINCIPLE, str(pid))
            if dst_id is None:
                continue
            out.append(_edge(src_id, dst_id, KGEdgeKind.CITES))
        for oid in getattr(memo, "observed_input_ids", []) or []:
            dst_id = (
                _node_id(index, KGNodeKind.SOURCE, str(oid))
                or _node_id(index, KGNodeKind.ALGORITHM, str(oid))
            )
            if dst_id is None:
                continue
            out.append(_edge(src_id, dst_id, KGEdgeKind.CITES))
    return out


# ── MENTIONS ────────────────────────────────────────────────────────


def extract_mentions(
    *,
    source_mentions: Iterable[dict[str, Any]],
    index: NodeIndex,
) -> list[KGEdge]:
    """source -> person / concept via cached NER results.

    ``source_mentions`` is an iterable of ``{src_ref, dst_kind, dst_ref,
    salience}`` dicts that the NER cache hands the builder; the
    extractor does NOT itself run NER — running the model on a build
    would be unbounded in cost.
    """
    out: list[KGEdge] = []
    for row in source_mentions:
        src_id = _node_id(index, KGNodeKind.SOURCE, str(row.get("src_ref", "")))
        if src_id is None:
            continue
        try:
            dst_kind = KGNodeKind(row["dst_kind"])
        except Exception:
            continue
        if dst_kind not in (KGNodeKind.PERSON, KGNodeKind.CONCEPT):
            continue
        dst_id = _node_id(index, dst_kind, str(row.get("dst_ref", "")))
        if dst_id is None:
            continue
        salience = float(row.get("salience", 1.0) or 1.0)
        out.append(
            _edge(
                src_id,
                dst_id,
                KGEdgeKind.MENTIONS,
                weight=salience,
            )
        )
    return out


EXTRACTORS: dict[KGEdgeKind, Callable[..., list[KGEdge]]] = {
    KGEdgeKind.DERIVED_FROM: extract_derived_from,
    KGEdgeKind.INVOKES: extract_invokes,
    KGEdgeKind.CONTRADICTS: extract_contradicts,
    KGEdgeKind.SUPPORTS: extract_supports,
    KGEdgeKind.APPLIES_TO: extract_applies_to,
    KGEdgeKind.PREDICTS: extract_predicts,
    KGEdgeKind.CITES: extract_cites,
    KGEdgeKind.MENTIONS: extract_mentions,
}
