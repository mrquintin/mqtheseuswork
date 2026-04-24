#!/usr/bin/env python3
"""AST-walk every module under methods/; fail if a method reads from
module-level mutable state not routed through Store."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

METHODS_DIR = Path(__file__).resolve().parent.parent / "noosphere" / "noosphere" / "methods"

ALLOWED_GLOBALS = frozenset({
    "REGISTRY",
    "CORRELATION_ID",
    "TENANT_ID",
    "_PRE_HOOKS",
    "_POST_HOOKS",
    "_FAILURE_HOOKS",
    "_store_factory",
    "logger",
    "__name__",
    "__file__",
    "__all__",
})

SAFE_TYPES = frozenset({
    "frozenset", "tuple", "namedtuple", "Enum", "IntEnum", "StrEnum",
})


def _is_safe_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    if isinstance(node, ast.AnnAssign):
        if node.value is None:
            return True
        return _is_safe_value(node.value)
    return all(_is_safe_value(node.value) for _ in node.targets) if node.value else True


def _is_safe_value(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return False
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in SAFE_TYPES:
            return True
        if isinstance(func, ast.Attribute) and func.attr in ("getLogger", "ContextVar"):
            return True
        return False
    if isinstance(node, ast.Name):
        return True
    return True


def check_module(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [f"{path}: SyntaxError: {e}"]

    violations: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        targets.append(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets.append(node.target.id)

            for name in targets:
                if name in ALLOWED_GLOBALS:
                    continue
                if name.startswith("_") and name.isupper():
                    continue
                # ALL_CAPS names are constants by Python convention
                if name.isupper() or (name.replace("_", "").isupper() and "_" in name):
                    continue
                if not _is_safe_assignment(node):
                    violations.append(
                        f"{path}:{node.lineno}: mutable module-level state '{name}' "
                        f"not routed through Store"
                    )
            continue
        if isinstance(node, ast.If):
            if (isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name)
                    and node.test.left.id == "__name__"):
                continue

    return violations


def main() -> int:
    if not METHODS_DIR.is_dir():
        print(f"Methods directory not found: {METHODS_DIR}")
        return 0

    all_violations: list[str] = []
    for py_file in sorted(METHODS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        all_violations.extend(check_module(py_file))

    if all_violations:
        print("Hidden mutable globals found:")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("OK: no hidden mutable globals found in methods/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
