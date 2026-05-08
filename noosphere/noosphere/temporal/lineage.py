"""Lineage assembler — projects the cascade graph + Store rows into a typed,
order-stable timeline that a reader can use to reconstruct how a conclusion
came to be.

A `Lineage` is a directed acyclic timeline of `LineageNode`s connected by
`LineageEdge`s. Each node carries an absolute timestamp; the canonical
serialisation sorts nodes by `(timestamp, kind_priority, id)` so the same
inputs always produce the same JSON byte-for-byte.

Public visibility is a per-node bit. The `public()` projection drops
private nodes (and their dangling edges) without leaving redaction
markers — readers cannot tell a private step ever existed.

This module does NOT introduce a new graph storage layer. It composes
existing reads from `noosphere.store.Store` (cascade graph, claims,
artifacts, conclusions, drift events, peer-review reports).
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field

from noosphere.models import (
    CascadeEdge,
    CascadeNodeKind,
)


# ── Node kinds ──────────────────────────────────────────────────────────────


class LineageNodeKind(str, Enum):
    SOURCE = "source"
    CLAIM = "claim"
    METHODOLOGY = "methodology"
    METHOD_INVOCATION = "method_invocation"
    PEER_REVIEW = "peer_review"
    REVISION = "revision"
    DRIFT = "drift"
    CALIBRATION = "calibration"
    CONCLUSION = "conclusion"
    PUBLICATION = "publication"
    CITATION = "citation"


# Causal ordering for ties on timestamp. Sources/claims come first, then
# the conclusion itself, then post-hoc events (review → drift → revision →
# calibration → publication → citations).
_KIND_PRIORITY: dict[LineageNodeKind, int] = {
    LineageNodeKind.SOURCE: 0,
    LineageNodeKind.CLAIM: 1,
    LineageNodeKind.METHODOLOGY: 2,
    LineageNodeKind.METHOD_INVOCATION: 3,
    LineageNodeKind.CONCLUSION: 4,
    LineageNodeKind.PEER_REVIEW: 5,
    LineageNodeKind.DRIFT: 6,
    LineageNodeKind.REVISION: 7,
    LineageNodeKind.CALIBRATION: 8,
    LineageNodeKind.PUBLICATION: 9,
    LineageNodeKind.CITATION: 10,
}


# ── Models ──────────────────────────────────────────────────────────────────


class LineageNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: LineageNodeKind
    label: str
    timestamp: datetime
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    public_visible: bool = False
    record_url: str = ""


class LineageEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str
    dst: str
    relation: str


class Lineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion_id: str
    assembled_at: datetime
    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdge] = Field(default_factory=list)

    def public(self) -> "Lineage":
        """Drop private nodes (and their dangling edges) without leaving
        gaps. The returned Lineage is what we ship to the public site."""
        keep = {n.id for n in self.nodes if n.public_visible}
        return Lineage(
            conclusion_id=self.conclusion_id,
            assembled_at=self.assembled_at,
            nodes=[n for n in self.nodes if n.id in keep],
            edges=[e for e in self.edges if e.src in keep and e.dst in keep],
        )


class LineageDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: list[LineageNode] = Field(default_factory=list)
    removed: list[LineageNode] = Field(default_factory=list)
    changed: list[dict[str, Any]] = Field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_to_dt(d: Optional[_date]) -> Optional[datetime]:
    if d is None:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _sort_key(node: LineageNode) -> tuple:
    return (_utc(node.timestamp), _KIND_PRIORITY.get(node.kind, 99), node.id)


def _trunc(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"


# ── Assembly ────────────────────────────────────────────────────────────────


def assemble_lineage(store, conclusion_id: str) -> Lineage:
    """Build the lineage for ``conclusion_id`` from rows in ``store``.

    Reads are batched: drift events and review reports are fetched once;
    cascade edges are walked once with `dst=conclusion_id` plus a single
    pass over each upstream claim's source artifact. For a 100-event
    conclusion this is comfortably under the 500ms cold budget on SQLite.
    """
    conclusion = store.get_conclusion(conclusion_id)
    if conclusion is None:
        raise LookupError(f"conclusion not found: {conclusion_id}")

    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_edge(src: str, dst: str, relation: str) -> None:
        key = (src, dst, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(LineageEdge(src=src, dst=dst, relation=relation))

    conclusion_nid = f"conclusion:{conclusion.id}"
    tier = conclusion.confidence_tier
    nodes[conclusion_nid] = LineageNode(
        id=conclusion_nid,
        kind=LineageNodeKind.CONCLUSION,
        label=_trunc(conclusion.text, 120),
        timestamp=_utc(conclusion.created_at),
        summary=_trunc(conclusion.rationale or conclusion.reasoning, 480),
        payload={
            "confidence": float(conclusion.confidence),
            "confidence_tier": tier.value if hasattr(tier, "value") else str(tier),
        },
        public_visible=True,
        record_url=f"/conclusions/{conclusion.id}",
    )

    # Cascade edges with this conclusion as destination — pulls in
    # supporting claims, methodology nodes, and any artifact that was
    # cited directly. Each upstream node is added at most once even if
    # it appears on multiple edges.
    for edge in store.iter_cascade_edges(dst=conclusion.id):
        _ingest_cascade_src(store, edge, nodes, add_edge, conclusion_nid)

    # Belt-and-braces: claims listed on the Conclusion payload itself.
    # When the cascade graph has been backfilled this is redundant; when
    # it hasn't, this is the only signal.
    for claim_id in conclusion.evidence_chain_claim_ids:
        _add_claim(store, claim_id, nodes, add_edge, conclusion_nid, "supports")
    for claim_id in conclusion.dissent_claim_ids:
        _add_claim(store, claim_id, nodes, add_edge, conclusion_nid, "dissents")

    # Peer reviews — list_review_reports already filters to this
    # conclusion. Reviews are private by default.
    for report in store.list_review_reports(conclusion.id):
        nid = f"review:{report.report_id}"
        nodes[nid] = LineageNode(
            id=nid,
            kind=LineageNodeKind.PEER_REVIEW,
            label=f"{report.reviewer}: {report.overall_verdict}",
            timestamp=_utc(report.completed_at),
            summary=_trunc(
                "; ".join(f.detail for f in report.findings[:3]), 480
            ),
            payload={
                "reviewer": report.reviewer,
                "verdict": report.overall_verdict,
                "confidence": float(report.confidence),
                "findings": [f.model_dump() for f in report.findings],
            },
            public_visible=False,
            record_url=f"/conclusions/{conclusion.id}?tab=peer",
        )
        add_edge(nid, conclusion_nid, "reviews")

    # Drift events. Filter target_id == conclusion_id; the Store API
    # returns all events so we project here. These are private — drift
    # is part of the firm's internal calibration loop.
    for drift in store.list_drift_events():
        if drift.target_id != conclusion.id:
            continue
        nid = f"drift:{drift.id}"
        nodes[nid] = LineageNode(
            id=nid,
            kind=LineageNodeKind.DRIFT,
            label=f"drift {drift.drift_score:.2f}",
            timestamp=_utc(_date_to_dt(drift.observed_at)),
            summary=_trunc(drift.notes, 480),
            payload={"drift_score": float(drift.drift_score)},
            public_visible=False,
            record_url="",
        )
        add_edge(nid, conclusion_nid, "observed_on")

    return Lineage(
        conclusion_id=conclusion_id,
        assembled_at=datetime.now(timezone.utc),
        nodes=sorted(nodes.values(), key=_sort_key),
        edges=edges,
    )


def _ingest_cascade_src(
    store,
    edge: CascadeEdge,
    nodes: dict[str, LineageNode],
    add_edge,
    conclusion_nid: str,
) -> None:
    cnode = store.get_cascade_node(edge.src)
    if cnode is None:
        return
    relation = edge.relation.value
    if cnode.kind == CascadeNodeKind.CLAIM:
        _add_claim(store, cnode.ref, nodes, add_edge, conclusion_nid, relation)
    elif cnode.kind == CascadeNodeKind.ARTIFACT:
        _add_artifact(store, cnode.ref, nodes, add_edge, conclusion_nid, relation)


def _add_claim(
    store,
    claim_id: str,
    nodes: dict[str, LineageNode],
    add_edge,
    dst: str,
    relation: str,
) -> None:
    nid = f"claim:{claim_id}"
    if nid in nodes:
        add_edge(nid, dst, relation)
        return
    claim = store.get_claim(claim_id)
    if claim is None:
        return
    when = claim.effective_at or _date_to_dt(claim.episode_date)
    nodes[nid] = LineageNode(
        id=nid,
        kind=LineageNodeKind.CLAIM,
        label=_trunc(claim.text, 120),
        timestamp=_utc(when),
        summary=_trunc(claim.text, 480),
        payload={
            "episode_id": claim.episode_id,
            "speaker_id": getattr(claim.speaker, "id", "") if claim.speaker else "",
            "confidence": float(claim.confidence),
        },
        # Claims that grounded a public conclusion are themselves
        # publicly attributable; sensitive content should be redacted
        # at extraction time, not lineage time.
        public_visible=True,
        record_url="",
    )
    add_edge(nid, dst, relation)
    if claim.source_id:
        _add_artifact(store, claim.source_id, nodes, add_edge, nid, "extracted_from")


def _add_artifact(
    store,
    artifact_id: str,
    nodes: dict[str, LineageNode],
    add_edge,
    dst: str,
    relation: str,
) -> None:
    nid = f"source:{artifact_id}"
    if nid in nodes:
        add_edge(nid, dst, relation)
        return
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        return
    label = artifact.title or artifact.uri or artifact_id
    nodes[nid] = LineageNode(
        id=nid,
        kind=LineageNodeKind.SOURCE,
        label=_trunc(label, 120),
        timestamp=_utc(artifact.effective_at or artifact.created_at),
        summary=_trunc(
            " · ".join(p for p in (artifact.author, artifact.uri) if p), 480
        ),
        payload={
            "uri": artifact.uri,
            "title": artifact.title,
            "author": artifact.author,
            "mime_type": artifact.mime_type,
        },
        public_visible=True,
        record_url=artifact.uri,
    )
    add_edge(nid, dst, relation)


# ── Diff ────────────────────────────────────────────────────────────────────


def lineage_diff(t1: Lineage, t2: Lineage) -> LineageDiff:
    """Return what changed between two snapshots — used by revision-event
    rendering to surface "since the last revision, what's new"."""
    by1 = {n.id: n for n in t1.nodes}
    by2 = {n.id: n for n in t2.nodes}
    added = [by2[nid] for nid in by2 if nid not in by1]
    removed = [by1[nid] for nid in by1 if nid not in by2]
    changed: list[dict[str, Any]] = []
    for nid in by1.keys() & by2.keys():
        a = by1[nid].model_dump(mode="json")
        b = by2[nid].model_dump(mode="json")
        if a != b:
            changed.append({"id": nid, "before": a, "after": b})
    added.sort(key=_sort_key)
    removed.sort(key=_sort_key)
    changed.sort(key=lambda d: d["id"])
    return LineageDiff(added=added, removed=removed, changed=changed)


# ── Markdown export ─────────────────────────────────────────────────────────


def lineage_to_markdown(lineage: Lineage) -> str:
    """Markdown rendering suitable for a research appendix."""
    lines: list[str] = []
    lines.append(f"# Lineage of conclusion `{lineage.conclusion_id}`")
    lines.append("")
    lines.append(
        f"_Assembled at {lineage.assembled_at.isoformat()} · "
        f"{len(lineage.nodes)} nodes, {len(lineage.edges)} edges_"
    )
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    for n in lineage.nodes:
        lines.append(
            f"### {n.timestamp.isoformat()} — {n.kind.value} — `{n.id}`"
        )
        lines.append(f"**{n.label}**")
        if n.summary:
            lines.append("")
            lines.append(n.summary)
        lines.append("")
    lines.append("## Edges")
    lines.append("")
    for e in lineage.edges:
        lines.append(f"- `{e.src}` —[{e.relation}]→ `{e.dst}`")
    return "\n".join(lines) + "\n"


# ── Sentence-provenance bridge ──────────────────────────────────────────────


def lineage_source_ids(lineage: Lineage) -> list[str]:
    """Return the artifact (source) node ids participating in a lineage.

    Companion to ``noosphere.cascade.sentence_provenance``: callers that
    already have a public lineage in hand can use this to validate that
    every source cited in the heatmap also appears in the public
    timeline (no heatmap source should be invisible to the reader who
    inspects the lineage).
    """
    return [n.id for n in lineage.nodes if n.kind == LineageNodeKind.SOURCE]


__all__ = [
    "Lineage",
    "LineageNode",
    "LineageEdge",
    "LineageNodeKind",
    "LineageDiff",
    "assemble_lineage",
    "lineage_diff",
    "lineage_source_ids",
    "lineage_to_markdown",
]
