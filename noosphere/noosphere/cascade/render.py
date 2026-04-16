from __future__ import annotations

from noosphere.models import CascadeEdge


def to_mermaid(edges: list[CascadeEdge], title: str = "Cascade") -> str:
    lines = [f"graph TD"]
    if title:
        lines.append(f"    %% {title}")
    seen: set[str] = set()
    for e in edges:
        if e.retracted_at is not None:
            continue
        key = f"{e.src}--{e.relation.value}-->{e.dst}"
        if key in seen:
            continue
        seen.add(key)
        label = f"{e.relation.value} ({e.confidence:.2f})"
        lines.append(f"    {_safe_id(e.src)} -->|{label}| {_safe_id(e.dst)}")
    return "\n".join(lines)


def to_graphviz(edges: list[CascadeEdge], title: str = "Cascade") -> str:
    lines = [f'digraph "{title}" {{', "    rankdir=LR;"]
    seen: set[str] = set()
    for e in edges:
        if e.retracted_at is not None:
            continue
        key = f"{e.src}->{e.dst}:{e.relation.value}"
        if key in seen:
            continue
        seen.add(key)
        label = f"{e.relation.value}\\n{e.confidence:.2f}"
        lines.append(
            f'    "{_safe_id(e.src)}" -> "{_safe_id(e.dst)}" '
            f'[label="{label}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def _safe_id(node_id: str) -> str:
    return node_id.replace("-", "_").replace(" ", "_")[:40]
