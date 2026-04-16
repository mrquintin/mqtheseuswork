#!/usr/bin/env python3
"""CI lint: fail if any packaged artifact, public-site asset, or API route phones home to unallowlisted domains."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ALLOWLIST = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "example.com",
    "example.org",
    "doi.org",
}

URL_RE = re.compile(
    r"""https?://([a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,}))(?:[:/?\#\s'"\)\]\}]|$)"""
)

FETCH_LIKE_RE = re.compile(
    r"""(?:fetch|axios|requests?\.|httpx\.|urllib|http\.get|http\.post|http\.request|XMLHttpRequest|\.open\s*\(\s*["'](?:GET|POST|PUT|DELETE))"""
)

SKIP_DIRS = {"node_modules", "__pycache__", ".next", ".git", "venv", ".venv"}
SCAN_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".mjs", ".cjs"}


def _load_allowlist() -> set[str]:
    env = os.environ.get("THESEUS_ALLOWLIST", "")
    extra = {d.strip().lower() for d in env.split(",") if d.strip()}
    return DEFAULT_ALLOWLIST | extra


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _scan_file(filepath: Path, allowlist: set[str]) -> list[str]:
    if filepath.suffix not in SCAN_EXTENSIONS:
        return []
    try:
        text = filepath.read_text(errors="replace")
    except OSError:
        return []

    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in URL_RE.finditer(line):
            domain = m.group(1).lower()
            if domain not in allowlist and not domain.endswith(".localhost") and not domain.endswith(".invalid"):
                violations.append(
                    f"{filepath}:{lineno}: outbound URL to unallowlisted domain {domain!r}"
                )
    return violations


def _scan_dir(root: Path, allowlist: set[str]) -> list[str]:
    if not root.exists():
        return []
    violations: list[str] = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and not _should_skip(f):
            violations.extend(_scan_file(f, allowlist))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for unallowlisted outbound URLs")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    allowlist = _load_allowlist()

    scan_targets = [
        REPO_ROOT / "founder-portal" / "src" / "app" / "api",
        REPO_ROOT / "theseus-public" / "src",
        REPO_ROOT / "docs" / "methods",
        REPO_ROOT / "docs" / "interop",
    ]

    out_dir = REPO_ROOT / "out_dir"
    if out_dir.exists():
        scan_targets.append(out_dir)

    all_violations: list[str] = []
    for target in scan_targets:
        all_violations.extend(_scan_dir(target, allowlist))

    if args.json:
        import json

        print(json.dumps({"ok": len(all_violations) == 0, "violations": all_violations}))
    elif all_violations:
        print("FAIL: unallowlisted outbound URLs detected:")
        for v in all_violations:
            print(f"  {v}")
        print(f"\n{len(all_violations)} violation(s) found.")
    else:
        print("OK: no unallowlisted outbound URLs detected.")

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
