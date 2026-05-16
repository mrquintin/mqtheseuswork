#!/usr/bin/env python3
"""Pre-commit / CI entry point for the Round-19 import-cycle gate.

Runs ``lint-imports`` (import-linter) over the Round-19 contracts in
``noosphere/.import-linter`` if the binary is on PATH; otherwise falls
back to the framework-free AST walker in
``scripts/detect_import_cycles.py`` and reports any strongly-connected
component of size > 1.

Exits non-zero on any cycle or contract violation. Prints a one-line
install hint when import-linter is missing so a fresh clone can opt in
quickly.

The check is fast (~1 s on the noosphere tree) and is invoked from:

* ``scripts/hooks/pre-commit.sh``
* ``.github/workflows/type-contracts.yml``
* ``tests/static/test_no_import_cycles.py``
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
from typing import Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
NOOSPHERE_DIR = REPO_ROOT / "noosphere"
IMPORT_LINTER_CONFIG = NOOSPHERE_DIR / ".import-linter"

# The Round-19 contracts. Listed explicitly so this gate doesn't fail on
# pre-existing breakage in the legacy ``*-interfaces-leaf`` contracts
# (those are tracked separately).
ROUND19_CONTRACTS: tuple[str, ...] = (
    "round19-layering",
    "portfolio-agent-is-leaf-consumer",
    "synthesizer-no-portfolio-agent",
    "algorithms-no-upstream",
    "bets-not-consumed-by-upstream",
    "knowledge-graph-no-mutation-of-peers",
)


def _run_import_linter() -> int:
    binary = shutil.which("lint-imports")
    if binary is None:
        return _fallback_ast_walker()
    if not IMPORT_LINTER_CONFIG.is_file():
        print(
            f"check_no_import_cycles: missing {IMPORT_LINTER_CONFIG}",
            file=sys.stderr,
        )
        return 2
    cmd: list[str] = [binary, "--config", str(IMPORT_LINTER_CONFIG)]
    for contract in ROUND19_CONTRACTS:
        cmd.extend(["--contract", contract])
    env = dict(os.environ)
    # import-linter loads the package; make sure noosphere is importable.
    pythonpath = env.get("PYTHONPATH", "")
    if str(NOOSPHERE_DIR) not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = (
            f"{NOOSPHERE_DIR}{os.pathsep}{pythonpath}" if pythonpath else str(NOOSPHERE_DIR)
        )
    proc = subprocess.run(cmd, env=env, cwd=str(REPO_ROOT))
    return proc.returncode


def _fallback_ast_walker() -> int:
    """Run the AST-based cycle detector and fail on any non-trivial SCC."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.detect_import_cycles import detect_cycles
    except ImportError as exc:  # pragma: no cover — defensive
        print(
            f"check_no_import_cycles: fallback detector unavailable ({exc}).\n"
            "Install import-linter for a richer check:\n"
            "    pip install import-linter\n",
            file=sys.stderr,
        )
        return 2

    package_root = NOOSPHERE_DIR / "noosphere"
    cycles = detect_cycles(str(package_root), package="noosphere")
    if not cycles:
        print("check_no_import_cycles: no cycles detected (AST fallback).")
        print(
            "note: install import-linter for full Round-19 layered checks:\n"
            "    pip install import-linter"
        )
        return 0

    # Read the allowlist. Each `### slug` block has a `Modules:` line listing
    # the sorted-tuple of the strongly-connected component, and an `Expires:`
    # line. A cycle is treated as allowed if its sorted-tuple matches an
    # un-expired allowlist entry exactly. New cycles, or cycles past expiry,
    # are hard failures.
    allow_path = REPO_ROOT / "docs" / "architecture" / "Known_Cycles.md"
    allowed: dict[tuple[str, ...], str] = {}
    expired: list[tuple[str, str]] = []
    if allow_path.is_file():
        import datetime as _dt
        import re as _re

        text = allow_path.read_text(encoding="utf-8")
        today = _dt.date.today()
        # Split on '### ' headings; first chunk is preamble.
        chunks = _re.split(r"^### ", text, flags=_re.MULTILINE)[1:]
        for chunk in chunks:
            slug = chunk.splitlines()[0].strip()
            mods_match = _re.search(
                r"-\s*Modules:\s*\n?((?:\s*[\w.]+,?\s*\n?)+)", chunk
            )
            exp_match = _re.search(r"-\s*Expires:\s*(\d{4}-\d{2}-\d{2})", chunk)
            if not (mods_match and exp_match):
                continue
            mods_blob = mods_match.group(1)
            modules = tuple(
                sorted(
                    m.strip().rstrip(",")
                    for m in mods_blob.split(",")
                    if m.strip().rstrip(",")
                )
            )
            try:
                exp_date = _dt.date.fromisoformat(exp_match.group(1))
            except ValueError:
                continue
            if exp_date < today:
                expired.append((slug, exp_match.group(1)))
                continue
            allowed[modules] = slug

    unallowed: list[tuple[str, ...]] = []
    allowed_hits: list[str] = []
    for scc in cycles:
        key = tuple(sorted(scc))
        if key in allowed:
            allowed_hits.append(f"{allowed[key]} ({len(key)} modules)")
        else:
            unallowed.append(key)

    if allowed_hits:
        print("check_no_import_cycles: allowlisted cycles (un-expired):")
        for hit in allowed_hits:
            print(f"  ✓ {hit}")

    if expired:
        print("\ncheck_no_import_cycles: EXPIRED allowlist entries:", file=sys.stderr)
        for slug, exp in expired:
            print(f"  ✗ {slug}  (expired {exp})", file=sys.stderr)
        print(
            "  → fix the cycle OR bump the Expires date with a written reason.",
            file=sys.stderr,
        )
        return 1

    if not unallowed:
        print(
            f"\ncheck_no_import_cycles: all {len(allowed_hits)} cycle(s) are "
            "allowlisted with un-expired entries. PASS."
        )
        return 0

    print(
        "\ncheck_no_import_cycles: UNALLOWLISTED import cycles detected:",
        file=sys.stderr,
    )
    for scc in sorted(unallowed):
        print("  - " + ", ".join(scc), file=sys.stderr)
    print(
        "\nResolve structurally or document in docs/architecture/Known_Cycles.md "
        "with an expiry date. Run\n"
        "    pip install import-linter\n"
        "for the richer layered-contract check.",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # unused — the gate is parameter-free by design.
    return _run_import_linter()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
