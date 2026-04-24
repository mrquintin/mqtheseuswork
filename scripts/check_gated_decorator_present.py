#!/usr/bin/env python3
"""AST-walk publication-handler modules and fail if any lack @gated."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

DEFAULT_HANDLER_PATHS = [
    "theseus-codex/src/app/api/",
    "researcher_api/researcher_api/routes/",
]


def _handler_paths() -> list[str]:
    env = os.environ.get("GATED_HANDLER_PATHS")
    if env:
        return [p.strip() for p in env.split(",") if p.strip()]
    return DEFAULT_HANDLER_PATHS


def _python_files(root: str) -> list[Path]:
    base = Path(root)
    if not base.exists():
        return []
    return sorted(base.rglob("*.py"))


def _has_gated_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id == "gated":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "gated":
                return True
        elif isinstance(dec, ast.Name) and dec.id == "gated":
            return True
        elif isinstance(dec, ast.Attribute) and dec.attr == "gated":
            return True
    return False


def _is_publication_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heuristic: functions that look like they write to a public store."""
    name = node.name.lower()
    publish_keywords = ("publish", "create_public", "post_public", "write_public")
    return any(kw in name for kw in publish_keywords)


def check_file(filepath: Path) -> list[str]:
    try:
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_publication_handler(node) and not _has_gated_decorator(node):
                issues.append(
                    f"{filepath}:{node.lineno} — {node.name}() lacks @gated decorator"
                )
    return issues


def main() -> int:
    paths = _handler_paths()
    all_issues: list[str] = []

    for handler_path in paths:
        for py_file in _python_files(handler_path):
            all_issues.extend(check_file(py_file))

    if all_issues:
        print("FAIL: publication handlers missing @gated decorator:")
        for issue in all_issues:
            print(f"  {issue}")
        return 1

    print("OK: all publication handlers have @gated decorator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
