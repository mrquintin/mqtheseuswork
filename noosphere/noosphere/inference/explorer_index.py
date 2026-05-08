"""Explorer index builder.

Materialises the data payload the founder-side embedding Explorer
consumes: per-conclusion embeddings, the methods that produced each
conclusion, geometric contradiction edges (prompt 24), and cascade
``SUPPORTS`` edges (prompt 05's composition graph plus the ordinary
cascade store).

The Explorer canvas itself runs in the browser (the dimensionality
reduction, the lasso, the edge overlay). This module is the
server-side assembler — it returns a dictionary that round-trips
through JSON without further transformation. It deliberately avoids
loading the Explorer's UI concerns (colour, tier styling); those are
the front-end's responsibility.

Public-preview filtering: when ``public_preview=True`` is passed, any
conclusion derived from an upload marked private is dropped from the
index. The Explorer must work for a public surface a future prompt
will build, so the filter has to live here, not in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

from noosphere.peer_review.geometric_blindspot import (
    DEFAULT_K,
    DEFAULT_RADIUS,
    DEFAULT_SPARSITY_FLOOR,
    detect_geometric_blindspots,
)


# ── Types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExplorerPoint:
    """One embedded conclusion, ready for projection in the browser."""

    id: str
    text: str
    topic_hint: str
    confidence_tier: str
    methods: tuple[str, ...]
    is_private: bool
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class ExplorerEdge:
    """One edge on the canvas. ``score`` is in [0, 1]."""

    a: str
    b: str
    kind: str  # "contradicts" | "supports"
    score: float


@dataclass(frozen=True)
class ExplorerIndex:
    """Server-built payload; flattens to the JSON the canvas reads."""

    points: tuple[ExplorerPoint, ...] = field(default_factory=tuple)
    edges: tuple[ExplorerEdge, ...] = field(default_factory=tuple)
    embedding_dim: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "points": [
                {
                    "id": p.id,
                    "text": p.text,
                    "topicHint": p.topic_hint,
                    "confidenceTier": p.confidence_tier,
                    "methods": list(p.methods),
                    "isPrivate": p.is_private,
                    "embedding": list(p.embedding),
                }
                for p in self.points
            ],
            "edges": [
                {"a": e.a, "b": e.b, "kind": e.kind, "score": e.score}
                for e in self.edges
            ],
            "embeddingDim": self.embedding_dim,
        }


# ── Helpers ────────────────────────────────────────────────────────


def _coerce_embedding(value: Any) -> Optional[tuple[float, ...]]:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        return None
    return tuple(float(x) for x in arr.tolist())


def _normalize_methods(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Mapping):
        return tuple(sorted(str(k) for k in value.keys()))
    try:
        return tuple(sorted({str(x) for x in value if x is not None and str(x)}))
    except TypeError:
        return ()


def _ensure_dim(points: Sequence[ExplorerPoint]) -> int:
    dims = {len(p.embedding) for p in points if p.embedding}
    if not dims:
        return 0
    if len(dims) > 1:
        # Drop ragged dims at the boundary; the canvas requires uniform width.
        raise ValueError(
            f"Explorer points have inconsistent embedding dimensions: {sorted(dims)}"
        )
    return dims.pop()


# ── Edge detection ─────────────────────────────────────────────────


def _supports_edges(
    points_by_id: Mapping[str, ExplorerPoint],
    cascade_edges: Iterable[Any],
) -> list[ExplorerEdge]:
    """Cascade ``SUPPORTS``-style edges restricted to the indexed points."""

    out: list[ExplorerEdge] = []
    for edge in cascade_edges:
        relation = getattr(edge, "relation", None)
        rel_value = getattr(relation, "value", relation)
        if str(rel_value).lower() not in {"supports", "extracted_from", "depends_on"}:
            continue
        src = str(getattr(edge, "src", ""))
        dst = str(getattr(edge, "dst", ""))
        if not src or not dst:
            continue
        if src not in points_by_id or dst not in points_by_id:
            continue
        score = float(getattr(edge, "confidence", 0.5) or 0.0)
        if score < 0.0:
            score = 0.0
        if score > 1.0:
            score = 1.0
        out.append(ExplorerEdge(a=src, b=dst, kind="supports", score=score))
    return out


def _contradicts_edges(
    points: Sequence[ExplorerPoint],
    locality_index: Any,
    *,
    radius: float,
    k: int,
    sparsity_floor: float,
    edges_per_point: int,
    detect: Any = detect_geometric_blindspots,
) -> list[ExplorerEdge]:
    """Run the geometric blindspot detector once per indexed point.

    The detector is lifted from prompt 24's reviewer; we deliberately
    reuse the shared algorithm rather than duplicating the geometry.
    Each blindspot a→b is rendered as a contradiction edge with
    ``score = combined_score`` so the UI can fade by confidence.
    """

    if locality_index is None or detect is None:
        return []

    ids = {p.id for p in points}
    out: list[ExplorerEdge] = []
    seen: set[tuple[str, str]] = set()

    # Lazy import to avoid a hard dependency on `noosphere.models` when
    # this module is consumed in environments that only need the JSON
    # builders (e.g. a docs script).
    from noosphere.models import Conclusion  # noqa: WPS433

    for point in points:
        try:
            stub = Conclusion(
                id=point.id,
                text=point.text,
                topic_hint=point.topic_hint or None,
                confidence_tier=point.confidence_tier or "open",
            )
        except Exception:
            # If the model schema rejects our stub, skip — better to
            # render the canvas without this point's edges than fail.
            continue

        try:
            spots = detect(
                stub,
                locality_index=locality_index,
                context={"query_embedding": list(point.embedding)},
                radius=radius,
                k=k,
                sparsity_floor=sparsity_floor,
                max_findings=edges_per_point,
            )
        except Exception:
            continue

        for spot in spots:
            other = str(spot.proposition_id)
            if other == point.id or other not in ids:
                continue
            key = (point.id, other) if point.id < other else (other, point.id)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ExplorerEdge(
                    a=key[0],
                    b=key[1],
                    kind="contradicts",
                    score=float(spot.combined_score),
                )
            )
    return out


# ── Public entry points ────────────────────────────────────────────


def build_explorer_index(
    rows: Iterable[Mapping[str, Any]],
    *,
    cascade_edges: Iterable[Any] = (),
    locality_index: Any = None,
    public_preview: bool = False,
    radius: float = DEFAULT_RADIUS,
    k: int = DEFAULT_K,
    sparsity_floor: float = DEFAULT_SPARSITY_FLOOR,
    contradiction_edges_per_point: int = 4,
    detect_blindspots: Any = detect_geometric_blindspots,
) -> ExplorerIndex:
    """Materialise the Explorer payload from raw conclusion rows.

    ``rows`` must be an iterable of mappings with at least the keys
    ``id``, ``text``, ``confidenceTier``, ``embedding``. Optional keys:
    ``topicHint``, ``methods``, ``isPrivate``.

    When ``public_preview`` is True, rows whose ``isPrivate`` flag is
    truthy are dropped before any geometry runs — the Explorer must
    not leak private claims even into the contradiction edge set.
    """

    points: list[ExplorerPoint] = []
    for raw in rows:
        rid = str(raw.get("id") or "").strip()
        if not rid:
            continue
        embedding = _coerce_embedding(raw.get("embedding"))
        if embedding is None:
            continue
        is_private = bool(raw.get("isPrivate") or raw.get("is_private"))
        if public_preview and is_private:
            continue
        points.append(
            ExplorerPoint(
                id=rid,
                text=str(raw.get("text") or ""),
                topic_hint=str(raw.get("topicHint") or raw.get("topic_hint") or ""),
                confidence_tier=str(raw.get("confidenceTier") or raw.get("confidence_tier") or "open"),
                methods=_normalize_methods(raw.get("methods")),
                is_private=is_private,
                embedding=embedding,
            )
        )

    if not points:
        return ExplorerIndex()

    embedding_dim = _ensure_dim(points)

    points_by_id = {p.id: p for p in points}
    edges: list[ExplorerEdge] = []
    edges.extend(_supports_edges(points_by_id, cascade_edges))
    edges.extend(
        _contradicts_edges(
            points,
            locality_index,
            radius=radius,
            k=k,
            sparsity_floor=sparsity_floor,
            edges_per_point=contradiction_edges_per_point,
            detect=detect_blindspots,
        )
    )

    return ExplorerIndex(
        points=tuple(points),
        edges=tuple(edges),
        embedding_dim=embedding_dim,
    )


def explorer_index_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper returning JSON-ready output."""

    return build_explorer_index(*args, **kwargs).to_json()


__all__ = [
    "ExplorerEdge",
    "ExplorerIndex",
    "ExplorerPoint",
    "build_explorer_index",
    "explorer_index_payload",
]
