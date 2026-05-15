"""Static import-graph cycle detector for the noosphere package.

Walks every ``*.py`` file under a root package, records *top-level* import
edges (function-local imports are deliberately ignored — they do not form a
runtime cycle), builds the directed module graph, and reports strongly
connected components (SCCs) of size > 1. Each non-trivial SCC is a cycle.

Usage
-----

    python scripts/detect_import_cycles.py noosphere/noosphere

    # Or as a library:
    from scripts.detect_import_cycles import detect_cycles
    cycles = detect_cycles("noosphere/noosphere", package="noosphere")

The detector excludes test directories, generated code, and legacy archives.
It is intentionally framework-free so it can run in CI without installing
``grimp``/``pydeps``/``import-linter``.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import Dict, Iterable, List, Set, Tuple

EXCLUDED_PARTS: frozenset[str] = frozenset(
    {
        "__pycache__",
        "_legacy",
        "_generated",
        "tests",
        "test",
        ".pytest_cache",
        "build",
        "dist",
        ".venv",
        "venv",
        "node_modules",
    }
)


def _module_name(path: pathlib.Path, pkg_root: pathlib.Path) -> str:
    rel = path.relative_to(pkg_root.parent)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _toplevel_imports(tree: ast.Module, package: str) -> Set[str]:
    """Top-level imports only — function-local imports do not create cycles."""
    out: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == package:
                base = node.module
                out.add(base)
                # Also record `from pkg.X import Y` as a potential edge to
                # ``pkg.X.Y`` so submodule-style imports are not collapsed
                # back into the parent package.
                for alias in node.names:
                    out.add(f"{base}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == package:
                    out.add(alias.name)
    return out


def collect_dependencies(
    root: str | pathlib.Path,
    *,
    package: str,
) -> Dict[str, Set[str]]:
    """Return ``{module_name: {imported_module_names}}`` for every top-level
    import inside the given package root."""
    pkg_root = pathlib.Path(root).resolve()
    deps: Dict[str, Set[str]] = {}
    for path in pkg_root.rglob("*.py"):
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        module = _module_name(path, pkg_root)
        if not module or not module.startswith(package):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        deps[module] = _toplevel_imports(tree, package)
    return deps


def _resolve(name: str, known: Set[str]) -> str | None:
    """Resolve an import target to the longest known module prefix."""
    while name and name not in known:
        if "." not in name:
            return None
        name = name.rsplit(".", 1)[0]
    return name or None


def build_graph(deps: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    known = set(deps)
    graph: Dict[str, Set[str]] = {m: set() for m in known}
    for src, targets in deps.items():
        for tgt in targets:
            resolved = _resolve(tgt, known)
            if resolved and resolved != src:
                graph[src].add(resolved)
    return graph


def _tarjan_sccs(graph: Dict[str, Set[str]]) -> List[List[str]]:
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    stack: List[str] = []
    sccs: List[List[str]] = []
    counter = [0]

    def strong(node: str) -> None:
        index[node] = counter[0]
        lowlink[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack[node] = True
        for succ in graph.get(node, ()):
            if succ not in index:
                strong(succ)
                lowlink[node] = min(lowlink[node], lowlink[succ])
            elif on_stack.get(succ):
                lowlink[node] = min(lowlink[node], index[succ])
        if lowlink[node] == index[node]:
            component: List[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == node:
                    break
            sccs.append(sorted(component))

    for node in list(graph):
        if node not in index:
            strong(node)
    return sccs


def detect_cycles(
    root: str | pathlib.Path,
    *,
    package: str,
) -> List[List[str]]:
    """Return all SCCs of size > 1 (each is a cycle).

    A "size-1 SCC" is just a node with no self-loop; those are not cycles.
    """
    deps = collect_dependencies(root, package=package)
    graph = build_graph(deps)
    return [scc for scc in _tarjan_sccs(graph) if len(scc) > 1]


def cycle_edges(
    cycle: Iterable[str],
    root: str | pathlib.Path,
    *,
    package: str,
) -> List[Tuple[str, str]]:
    """Return the import edges that fall *inside* the given SCC."""
    deps = collect_dependencies(root, package=package)
    graph = build_graph(deps)
    members = set(cycle)
    return sorted(
        (src, tgt)
        for src in members
        for tgt in graph.get(src, ())
        if tgt in members
    )


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(
            "usage: detect_import_cycles.py PACKAGE_ROOT [--package NAME] [--json]\n"
        )
        return 2
    root = argv[1]
    package = pathlib.Path(root).name
    as_json = False
    i = 2
    while i < len(argv):
        if argv[i] == "--package" and i + 1 < len(argv):
            package = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        else:
            i += 1
    cycles = detect_cycles(root, package=package)
    if as_json:
        edges = {
            "cycles": [
                {
                    "modules": cycle,
                    "edges": cycle_edges(cycle, root, package=package),
                }
                for cycle in cycles
            ]
        }
        print(json.dumps(edges, indent=2))
    else:
        if not cycles:
            print(f"OK: no import cycles in {package}")
            return 0
        print(f"FAIL: {len(cycles)} import cycle(s) in {package}:")
        for cycle in cycles:
            print("  cycle:")
            for module in cycle:
                print(f"    - {module}")
            for src, tgt in cycle_edges(cycle, root, package=package):
                print(f"      edge: {src} -> {tgt}")
    return 1 if cycles else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
