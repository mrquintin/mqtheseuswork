"""End-of-session export of the live argument map.

Produces three artifacts from a builder snapshot:

* ``map.json``   — full structured graph (nodes + edges + drift trace),
                   the canonical interchange format.
* ``map.svg``    — static force-directed picture of the final state.
                   Useful for embedding in articles or sharing without
                   shipping the JSON.
* ``map.md``     — Markdown summary; this is the artifact noosphere
                   ingests in place of the raw transcript. The raw
                   transcript is still written alongside as a fallback.

The Markdown carries YAML frontmatter (``kind: argument_map``) so the
ingester can route it to a structured-aware path instead of the generic
paragraph chunker.
"""

from __future__ import annotations

import json
import math
import textwrap
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..argument_map_builder import (
    ArgumentEdge,
    ArgumentMapBuilder,
    ArgumentNode,
    DriftReading,
    Utterance,
    RELATION_ASKS_ABOUT,
    RELATION_CONTRADICTS,
    RELATION_REFINES,
    RELATION_SUPPORTS,
)


# ── JSON ──────────────────────────────────────────────────────────────


def export_json(builder: ArgumentMapBuilder, *, session_id: str = "", title: str = "") -> dict:
    """Snapshot the builder to a JSON-safe dict."""

    snap = builder.snapshot()
    return {
        "kind": "argument_map",
        "version": 1,
        "session_id": session_id,
        "title": title,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "nodes": snap["nodes"],
        "edges": snap["edges"],
        "drift": snap["drift"],
        "turn_count": snap["turn_count"],
    }


# ── SVG ───────────────────────────────────────────────────────────────


_RELATION_STYLE = {
    RELATION_SUPPORTS: ("#2e7d32", "—"),
    RELATION_CONTRADICTS: ("#c62828", "⊥"),
    RELATION_REFINES: ("#1565c0", "→"),
    RELATION_ASKS_ABOUT: ("#9e9e9e", "?"),
}

_STATE_FILL = {
    "active": "#ffffff",
    "amber": "#ffb300",
    "red": "#e53935",
    "answered": "#a5d6a7",
}

_TYPE_STROKE = {
    "empirical": "#1565c0",
    "normative": "#6a1b9a",
    "methodological": "#00838f",
    "predictive": "#ef6c00",
    "definitional": "#37474f",
    "question": "#9e9e9e",
}


def _layout_force_directed(
    nodes: list[ArgumentNode],
    edges: list[ArgumentEdge],
    *,
    width: float = 900.0,
    height: float = 600.0,
    iterations: int = 120,
) -> dict[str, tuple[float, float]]:
    """A tiny Fruchterman-Reingold layout. Pure-python; deterministic
    given identical inputs (we don't randomise initial positions —
    polar placement on a circle is enough to break symmetry without
    drawing in the Random module)."""

    n = len(nodes)
    if n == 0:
        return {}
    if n == 1:
        return {nodes[0].node_id: (width / 2, height / 2)}

    pos: dict[str, list[float]] = {}
    radius = min(width, height) * 0.35
    for i, node in enumerate(nodes):
        theta = 2.0 * math.pi * i / n
        pos[node.node_id] = [
            width / 2 + radius * math.cos(theta),
            height / 2 + radius * math.sin(theta),
        ]

    area = width * height
    k = math.sqrt(area / n)
    t = max(width, height) / 10.0
    cooling = t / max(1, iterations)

    for _ in range(iterations):
        disp: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in pos}
        # repulsion
        ids = list(pos.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                dx = pos[a][0] - pos[b][0]
                dy = pos[a][1] - pos[b][1]
                dist = math.sqrt(dx * dx + dy * dy) or 0.01
                force = (k * k) / dist
                disp[a][0] += dx / dist * force
                disp[a][1] += dy / dist * force
                disp[b][0] -= dx / dist * force
                disp[b][1] -= dy / dist * force
        # attraction along edges
        for e in edges:
            if e.src not in pos or e.dst not in pos:
                continue
            dx = pos[e.src][0] - pos[e.dst][0]
            dy = pos[e.src][1] - pos[e.dst][1]
            dist = math.sqrt(dx * dx + dy * dy) or 0.01
            force = (dist * dist) / k
            disp[e.src][0] -= dx / dist * force
            disp[e.src][1] -= dy / dist * force
            disp[e.dst][0] += dx / dist * force
            disp[e.dst][1] += dy / dist * force
        # apply, clamped by temperature
        for nid, (dx, dy) in disp.items():
            mag = math.sqrt(dx * dx + dy * dy) or 0.01
            pos[nid][0] += dx / mag * min(mag, t)
            pos[nid][1] += dy / mag * min(mag, t)
            pos[nid][0] = max(20, min(width - 20, pos[nid][0]))
            pos[nid][1] = max(20, min(height - 20, pos[nid][1]))
        t = max(0.1, t - cooling)

    return {nid: (xy[0], xy[1]) for nid, xy in pos.items()}


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_svg(
    builder: ArgumentMapBuilder,
    *,
    width: int = 900,
    height: int = 600,
) -> str:
    nodes = builder.nodes()
    edges = builder.edges()
    pos = _layout_force_directed(nodes, edges, width=width, height=height)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(
        '<style>text{font:11px -apple-system,Helvetica,Arial,sans-serif;fill:#222}</style>'
    )

    for e in edges:
        if e.src not in pos or e.dst not in pos:
            continue
        x1, y1 = pos[e.src]
        x2, y2 = pos[e.dst]
        color, _ = _RELATION_STYLE.get(e.relation, ("#888", "—"))
        dasharray = '4,3' if e.relation == RELATION_ASKS_ABOUT else 'none'
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="{dasharray}" '
            f'opacity="{min(1.0, 0.4 + e.confidence):.2f}"/>'
        )

    for n in nodes:
        if n.node_id not in pos:
            continue
        cx, cy = pos[n.node_id]
        fill = _STATE_FILL.get(n.state, "#ffffff")
        stroke = _TYPE_STROKE.get(n.claim_type, "#444")
        r = 8 + min(12, 2 * (n.seen_count - 1))
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        label = _xml_escape(n.text[:60] + ("…" if len(n.text) > 60 else ""))
        parts.append(
            f'<text x="{cx + r + 4:.1f}" y="{cy + 3:.1f}">{label}</text>'
        )

    parts.append('</svg>')
    return "\n".join(parts)


# ── Markdown ──────────────────────────────────────────────────────────


def export_markdown(
    builder: ArgumentMapBuilder,
    *,
    session_id: str = "",
    title: str = "",
    include_transcript_fallback: bool = True,
) -> str:
    nodes = builder.nodes()
    edges = builder.edges()
    drift = builder.drift_readings()
    utterances = builder.utterances()

    by_id = {n.node_id: n for n in nodes}
    out_edges: dict[str, list[ArgumentEdge]] = {n.node_id: [] for n in nodes}
    in_edges: dict[str, list[ArgumentEdge]] = {n.node_id: [] for n in nodes}
    for e in edges:
        out_edges.setdefault(e.src, []).append(e)
        in_edges.setdefault(e.dst, []).append(e)

    lines: list[str] = []
    lines.append("---")
    lines.append("kind: argument_map")
    if session_id:
        lines.append(f'session_id: "{session_id}"')
    if title:
        lines.append(f'title: "{title}"')
    lines.append(f"node_count: {len(nodes)}")
    lines.append(f"edge_count: {len(edges)}")
    lines.append(f"turn_count: {builder.snapshot()['turn_count']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title or 'Argument Map'}")
    lines.append("")

    # Highlights: unresolved questions surface first because that's the
    # signal the participant is most likely to act on.
    unresolved = [n for n in nodes if n.is_question and n.state in ("amber", "red")]
    if unresolved:
        lines.append("## Unresolved questions")
        lines.append("")
        for n in unresolved:
            badge = "🔴" if n.state == "red" else "🟠"
            lines.append(f"- {badge} **{n.text}** _(asked at turn {n.turn_index} by {n.speaker})_")
        lines.append("")

    contradictions = [e for e in edges if e.relation == RELATION_CONTRADICTS]
    if contradictions:
        lines.append("## Contradictions")
        lines.append("")
        for e in contradictions:
            a = by_id.get(e.src)
            b = by_id.get(e.dst)
            if not a or not b:
                continue
            lines.append(f"- **{a.text}** ⊥ **{b.text}** _(confidence {e.confidence:.2f})_")
        lines.append("")

    if drift:
        flagged = [d for d in drift if d.flagged]
        if flagged:
            lines.append("## Drift events")
            lines.append("")
            for d in flagged:
                lines.append(f"- turn {d.turn_index}: drift={d.drift:.2f}")
            lines.append("")

    # The structured claim list. Each claim is a heading-less item with
    # its outgoing relations, so noosphere can extract claim/relation
    # pairs directly without re-running NLI.
    lines.append("## Claims")
    lines.append("")
    for n in sorted(nodes, key=lambda n: n.turn_index):
        marker = "?" if n.is_question else "•"
        lines.append(
            f"### {marker} {n.text}"
        )
        meta = [
            f"speaker: {n.speaker}",
            f"type: {n.claim_type}",
            f"turn: {n.turn_index}",
            f"state: {n.state}",
            f"seen: {n.seen_count}",
            f"id: {n.node_id}",
        ]
        lines.append("> " + " · ".join(meta))
        outs = out_edges.get(n.node_id, [])
        if outs:
            for e in outs:
                tgt = by_id.get(e.dst)
                if not tgt:
                    continue
                lines.append(
                    f"- {e.relation} → {tgt.text}  _(conf {e.confidence:.2f}, id {tgt.node_id})_"
                )
        lines.append("")

    if include_transcript_fallback and utterances:
        lines.append("## Transcript (fallback)")
        lines.append("")
        lines.append("```")
        for u in utterances:
            ts = f"[{u.t_start:7.1f}]" if u.t_start else "[       ]"
            lines.append(f"{ts} {u.speaker}: {u.text}")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ── disk write ────────────────────────────────────────────────────────


def write_session_exports(
    builder: ArgumentMapBuilder,
    out_dir: str | Path,
    *,
    session_id: str = "",
    title: str = "",
    transcript_text: str | None = None,
) -> dict[str, Path]:
    """Write JSON / SVG / Markdown exports plus the raw transcript fallback.

    Returns a dict of artifact_kind → Path so callers can attach the
    files (e.g. upload to Codex, log paths to the user)."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    j = export_json(builder, session_id=session_id, title=title)
    p_json = out / "argument_map.json"
    p_json.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["json"] = p_json

    p_svg = out / "argument_map.svg"
    p_svg.write_text(export_svg(builder), encoding="utf-8")
    paths["svg"] = p_svg

    p_md = out / "argument_map.md"
    p_md.write_text(
        export_markdown(builder, session_id=session_id, title=title),
        encoding="utf-8",
    )
    paths["markdown"] = p_md

    # The raw transcript stays available so a user with no NLI tooling
    # (or one who distrusts the extractor) can still see the source.
    if transcript_text is None:
        transcript_text = "\n".join(
            f"[{u.t_start:.1f}] {u.speaker}: {u.text}" for u in builder.utterances()
        )
    p_txt = out / "transcript.txt"
    p_txt.write_text(transcript_text, encoding="utf-8")
    paths["transcript"] = p_txt

    return paths


__all__ = [
    "export_json",
    "export_markdown",
    "export_svg",
    "write_session_exports",
]
