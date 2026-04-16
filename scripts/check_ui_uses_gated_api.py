#!/usr/bin/env python3
"""CI lint: verify founder-portal round3 routes use withGated and theseus-public has no write routes."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WITH_GATED_RE = re.compile(r"\bwithGated\s*\(")
EXPORT_HANDLER_RE = re.compile(r"export\s+(?:const|function)\s+(GET|POST|PUT|DELETE|PATCH)\b")
WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _check_round3_routes(round3_dir: Path) -> list[str]:
    if not round3_dir.exists():
        return []

    violations: list[str] = []
    route_files = sorted(round3_dir.rglob("route.ts")) + sorted(round3_dir.rglob("route.tsx"))

    for route_file in route_files:
        try:
            text = route_file.read_text()
        except OSError:
            continue

        handlers = EXPORT_HANDLER_RE.findall(text)
        if not handlers:
            continue

        has_with_gated = bool(WITH_GATED_RE.search(text))
        if not has_with_gated:
            for handler in handlers:
                violations.append(
                    f"{route_file}: export {handler} does not use withGated wrapper"
                )

    return violations


def _check_public_routes(public_app_dir: Path) -> list[str]:
    if not public_app_dir.exists():
        return []

    violations: list[str] = []
    api_dir = public_app_dir / "api"
    if not api_dir.exists():
        return []

    route_files = sorted(api_dir.rglob("route.ts")) + sorted(api_dir.rglob("route.tsx"))
    for route_file in route_files:
        try:
            text = route_file.read_text()
        except OSError:
            continue

        for m in EXPORT_HANDLER_RE.finditer(text):
            method = m.group(1)
            if method in WRITE_METHODS:
                violations.append(
                    f"{route_file}: public site exports write handler {method}"
                )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check UI route gating and public-site write restrictions",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    round3_dir = REPO_ROOT / "founder-portal" / "src" / "app" / "api" / "round3"
    public_app_dir = REPO_ROOT / "theseus-public" / "src" / "app"

    violations: list[str] = []
    violations.extend(_check_round3_routes(round3_dir))
    violations.extend(_check_public_routes(public_app_dir))

    if args.json:
        import json

        print(json.dumps({"ok": len(violations) == 0, "violations": violations}))
    elif violations:
        print("FAIL: UI route violations:")
        for v in violations:
            print(f"  {v}")
        print(f"\n{len(violations)} violation(s) found.")
    else:
        print("OK: all round3 routes use withGated; public site has no write handlers.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
