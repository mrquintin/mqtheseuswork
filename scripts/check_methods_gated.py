#!/usr/bin/env python3
"""CI lint: fail if any module calls a ported method directly instead of via REGISTRY.get()."""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _populate_registry() -> None:
    import importlib

    methods_dir = REPO_ROOT / "noosphere" / "noosphere" / "methods"
    for py in sorted(methods_dir.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        try:
            importlib.import_module(f"noosphere.methods.{py.stem}")
        except Exception:
            pass


def _build_target_set() -> set[str]:
    from noosphere.methods._registry import REGISTRY

    targets: set[str] = set()

    for spec in REGISTRY.list():
        impl = spec.implementation
        targets.add(f"{impl.module}.{impl.fn_name}")

    legacy_dir = REPO_ROOT / "noosphere" / "noosphere" / "methods" / "_legacy"
    for py in sorted(legacy_dir.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        mod_fqn = f"noosphere.methods._legacy.{py.stem}"
        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    targets.add(f"{mod_fqn}.{node.name}")

    return targets


def _resolve_attr_chain(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        base = _resolve_attr_chain(node.value)
        if base is not None:
            return [*base, node.attr]
    return None


def _build_import_map(tree: ast.Module) -> dict[str, str]:
    imap: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    imap[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    imap.setdefault(top, top)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                imap[local] = f"{node.module}.{alias.name}"
    return imap


def _scan_file(
    filepath: Path, targets: set[str], methods_dir: Path
) -> list[str]:
    try:
        filepath.resolve().relative_to(methods_dir.resolve())
        return []
    except ValueError:
        pass

    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except Exception:
        return []

    imap = _build_import_map(tree)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _resolve_attr_chain(node.func)
        if not chain:
            continue
        head = chain[0]
        if head not in imap:
            continue
        fqn = imap[head] + ("." + ".".join(chain[1:]) if len(chain) > 1 else "")
        if fqn in targets:
            violations.append(
                f"{filepath}:{node.lineno} calls ported fn {fqn} directly"
                f" — use REGISTRY.get()"
            )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that ported methods are called through REGISTRY",
    )
    parser.add_argument("--scan-dir", action="append", default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    _populate_registry()
    targets = _build_target_set()

    if not targets:
        print("No ported methods found in registry — nothing to check.")
        return 0

    scan_dirs = args.scan_dir or [str(REPO_ROOT / "noosphere" / "noosphere")]
    methods_dir = REPO_ROOT / "noosphere" / "noosphere" / "methods"
    violations: list[str] = []

    for scan_dir in scan_dirs:
        for py_file in sorted(Path(scan_dir).rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            violations.extend(_scan_file(py_file, targets, methods_dir))

    if violations:
        for v in violations:
            print(v)
        print(f"\n{len(violations)} violation(s) found.")
        return 1

    print("No bypass violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
