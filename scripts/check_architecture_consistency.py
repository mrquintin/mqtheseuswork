#!/usr/bin/env python3
"""CI guard: docs/architecture/Theseus_Architecture.md must not drift from the
codebase it describes.

The architecture document is the connecting map for the firm's system. If a
new Noosphere package appears under ``noosphere/noosphere/`` or a new top-level
route appears under ``theseus-codex/src/app/`` and nobody adds it to the
architecture doc, the map is silently wrong. This script fails CI in that case.

What "mentioned" means here
---------------------------
The doc carries an explicit, CI-checked component index (Appendix A) in which
every package name and every route segment appears as its own inline-code
(backtick) token. This script:

1. Enumerates the *actual* package directories (a directory under
   ``noosphere/noosphere/`` that contains an ``__init__.py``).
2. Enumerates the *actual* top-level route segments under
   ``theseus-codex/src/app/`` (each immediate sub-directory; Next.js route
   groups like ``(authed)`` are normalised to ``authed``).
3. Collects every inline-code token from the Markdown architecture doc.
4. Asserts every package and every route segment is present as a token.

Granularity note: "every route" is checked at the top-level route-segment
level. Checking every nested route would mean naming hundreds of routes in an
architecture document, which the doc's own two-page-per-section constraint
rules out. Top-level segments are the architectural granularity.

Exit code 0 = consistent, 1 = drift (with a report of what is missing).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "architecture" / "Theseus_Architecture.md"
NOOSPHERE_PKG_ROOT = REPO_ROOT / "noosphere" / "noosphere"
CODEX_APP_ROOT = REPO_ROOT / "theseus-codex" / "src" / "app"

# Fenced code blocks (```...```) — stripped before inline-token extraction so
# the triple-backtick fences do not desync inline-code pairing.
FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
# Inline-code token: text between single backticks, no nested backticks.
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def discover_packages() -> list[str]:
    """Package directories under noosphere/noosphere/ (have an __init__.py)."""
    if not NOOSPHERE_PKG_ROOT.is_dir():
        print(f"error: {NOOSPHERE_PKG_ROOT} does not exist", file=sys.stderr)
        sys.exit(1)
    pkgs = [
        child.name
        for child in NOOSPHERE_PKG_ROOT.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    ]
    return sorted(pkgs)


def discover_routes() -> list[str]:
    """Top-level route segments under theseus-codex/src/app/.

    Each immediate sub-directory is a segment. Next.js route groups are wrapped
    in parentheses (``(authed)``, ``(home)``); the parentheses are stripped so
    the doc can refer to them as plain words.
    """
    if not CODEX_APP_ROOT.is_dir():
        print(f"error: {CODEX_APP_ROOT} does not exist", file=sys.stderr)
        sys.exit(1)
    routes = []
    for child in CODEX_APP_ROOT.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("(") and name.endswith(")"):
            name = name[1:-1]
        routes.append(name)
    return sorted(routes)


def doc_tokens(text: str) -> set[str]:
    """Every inline-code token in the Markdown doc, fenced blocks excluded."""
    without_fences = FENCED_BLOCK.sub("", text)
    return {m.group(1).strip() for m in INLINE_CODE.finditer(without_fences)}


def main() -> int:
    if not DOC_PATH.exists():
        print(f"error: architecture doc not found at {DOC_PATH}", file=sys.stderr)
        return 1

    text = DOC_PATH.read_text(encoding="utf-8")
    tokens = doc_tokens(text)

    packages = discover_packages()
    routes = discover_routes()

    missing_packages = [p for p in packages if p not in tokens]
    missing_routes = [r for r in routes if r not in tokens]

    if missing_packages or missing_routes:
        print("Architecture document is out of date with the codebase.\n")
        print(f"  doc: {DOC_PATH.relative_to(REPO_ROOT)}\n")
        if missing_packages:
            print("Noosphere packages not mentioned in the architecture doc:")
            for p in missing_packages:
                print(f"  - noosphere/noosphere/{p}/")
            print()
        if missing_routes:
            print("Codex top-level routes not mentioned in the architecture doc:")
            for r in missing_routes:
                print(f"  - theseus-codex/src/app/{r}/")
            print()
        print(
            "Add each missing name as an inline-code token (e.g. `name`) to the\n"
            "component index in Appendix A, and describe it in the relevant\n"
            "section if it is architecturally significant."
        )
        return 1

    print(
        f"architecture doc consistent: {len(packages)} Noosphere packages and "
        f"{len(routes)} Codex top-level routes all mentioned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
