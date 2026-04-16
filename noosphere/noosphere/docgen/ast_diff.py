"""Lightweight Python AST comparator producing human-readable change summaries."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ASTChange:
    kind: str  # "added", "removed", "modified", "signature_changed"
    entity_type: str  # "function", "class", "import", "constant"
    name: str
    detail: str = ""


def _extract_top_level(tree: ast.Module) -> dict[str, ast.AST]:
    """Extract top-level named definitions from an AST module."""
    entities: dict[str, ast.AST] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entities[f"function:{node.name}"] = node
        elif isinstance(node, ast.ClassDef):
            entities[f"class:{node.name}"] = node
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entities[f"method:{node.name}.{item.name}"] = item
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            key = ast.dump(node)
            entities[f"import:{key}"] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    entities[f"constant:{target.id}"] = node
    return entities


def _signature_str(node: ast.AST) -> Optional[str]:
    """Extract a function/method signature string."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        parts: list[str] = []
        for arg in args.args:
            ann = ast.dump(arg.annotation) if arg.annotation else ""
            parts.append(f"{arg.arg}:{ann}" if ann else arg.arg)
        ret = ast.dump(node.returns) if node.returns else ""
        return f"({', '.join(parts)}) -> {ret}"
    return None


def _body_hash(node: ast.AST) -> str:
    """Hash the AST dump of a node's body for change detection."""
    return ast.dump(node)


def diff_sources(old_source: str, new_source: str) -> list[ASTChange]:
    """Compare two Python source strings and return a list of changes."""
    try:
        old_tree = ast.parse(old_source)
        new_tree = ast.parse(new_source)
    except SyntaxError as e:
        return [ASTChange(kind="error", entity_type="parse", name="", detail=str(e))]

    old_entities = _extract_top_level(old_tree)
    new_entities = _extract_top_level(new_tree)

    old_keys = set(old_entities.keys())
    new_keys = set(new_entities.keys())

    changes: list[ASTChange] = []

    for key in sorted(new_keys - old_keys):
        entity_type, name = key.split(":", 1)
        changes.append(ASTChange(kind="added", entity_type=entity_type, name=name))

    for key in sorted(old_keys - new_keys):
        entity_type, name = key.split(":", 1)
        changes.append(ASTChange(kind="removed", entity_type=entity_type, name=name))

    for key in sorted(old_keys & new_keys):
        entity_type, name = key.split(":", 1)
        old_node = old_entities[key]
        new_node = new_entities[key]

        old_sig = _signature_str(old_node)
        new_sig = _signature_str(new_node)
        if old_sig is not None and new_sig is not None and old_sig != new_sig:
            changes.append(ASTChange(
                kind="signature_changed", entity_type=entity_type, name=name,
                detail=f"{old_sig} -> {new_sig}",
            ))
        elif _body_hash(old_node) != _body_hash(new_node):
            changes.append(ASTChange(
                kind="modified", entity_type=entity_type, name=name,
            ))

    return changes


def summarize_changes(changes: list[ASTChange]) -> str:
    """Produce a human-readable summary of AST changes."""
    if not changes:
        return "No changes detected."

    lines: list[str] = []
    for c in changes:
        if c.kind == "added":
            lines.append(f"+ Added {c.entity_type} `{c.name}`")
        elif c.kind == "removed":
            lines.append(f"- Removed {c.entity_type} `{c.name}`")
        elif c.kind == "signature_changed":
            lines.append(f"~ Signature changed for {c.entity_type} `{c.name}`: {c.detail}")
        elif c.kind == "modified":
            lines.append(f"~ Modified {c.entity_type} `{c.name}`")
        elif c.kind == "error":
            lines.append(f"! Parse error: {c.detail}")

    return "\n".join(lines)


def has_behavior_change(changes: list[ASTChange]) -> bool:
    """Return True if any change could affect runtime behavior."""
    return any(
        c.kind in ("added", "removed", "modified", "signature_changed")
        and c.entity_type in ("function", "method", "class")
        for c in changes
    )
