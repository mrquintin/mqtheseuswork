#!/usr/bin/env python3
"""CI lint: recompile every method doc and reject drift against committed docs.

Usage:
    python scripts/check_doc_drift.py [--docs-dir docs/methods]

Also usable as a pre-commit hook to reject manual edits to generated files
(only RATIONALE.md is hand-authored).
"""
from __future__ import annotations

import argparse
import difflib
import sys
import tempfile
from pathlib import Path

GENERATED_FILES = {"spec.md", "examples.md", "calibration.md", "transfer.md", "operations.md", "index.md"}
HAND_AUTHORED = {"rationale.md"}


def check_precommit_hook(staged_files: list[str], docs_dir: Path) -> list[str]:
    """Return list of violations: generated files that were manually edited."""
    violations: list[str] = []
    docs_prefix = str(docs_dir)
    for f in staged_files:
        if not f.startswith(docs_prefix):
            continue
        fname = Path(f).name.lower()
        if fname in GENERATED_FILES:
            violations.append(f"Manual edit to generated file: {f}")
    return violations


def check_drift(committed_dir: Path, recompiled_dir: Path) -> list[str]:
    """Diff committed docs against freshly compiled docs. Return list of diffs."""
    diffs: list[str] = []
    if not committed_dir.exists():
        return diffs

    for committed_file in sorted(committed_dir.rglob("*.md")):
        rel = committed_file.relative_to(committed_dir)
        if rel.name.lower() in HAND_AUTHORED:
            continue
        recompiled_file = recompiled_dir / rel
        if not recompiled_file.exists():
            diffs.append(f"Missing in recompiled output: {rel}")
            continue

        committed_lines = committed_file.read_text().splitlines(keepends=True)
        recompiled_lines = recompiled_file.read_text().splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            committed_lines, recompiled_lines,
            fromfile=f"committed/{rel}",
            tofile=f"recompiled/{rel}",
        ))
        if diff:
            diffs.append("".join(diff))

    for recompiled_file in sorted(recompiled_dir.rglob("*.md")):
        rel = recompiled_file.relative_to(recompiled_dir)
        committed_file = committed_dir / rel
        if not committed_file.exists() and rel.name.lower() not in HAND_AUTHORED:
            diffs.append(f"New file in recompiled output not yet committed: {rel}")

    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for doc drift")
    parser.add_argument("--docs-dir", type=Path, default=Path("docs/methods"))
    parser.add_argument("--pre-commit", action="store_true", help="Run in pre-commit mode")
    parser.add_argument("staged_files", nargs="*", help="Staged files (for pre-commit mode)")
    args = parser.parse_args()

    if args.pre_commit:
        violations = check_precommit_hook(args.staged_files, args.docs_dir)
        if violations:
            print("Pre-commit hook: manual edits to generated doc files detected:", file=sys.stderr)
            for v in violations:
                print(f"  {v}", file=sys.stderr)
            print("\nOnly RATIONALE.md files may be hand-edited. Regenerate docs with the compiler.", file=sys.stderr)
            return 1
        return 0

    # Full drift check requires recompilation — import here to avoid import cost in pre-commit mode
    try:
        from noosphere.docgen.compiler import compile_method_doc, TEMPLATE_VERSION
        from noosphere.ledger.keys import KeyRing
        from noosphere.methods._registry import REGISTRY
        from noosphere.models import MethodRef
    except ImportError as e:
        print(f"Cannot import noosphere modules: {e}", file=sys.stderr)
        print("Run from project root with noosphere on PYTHONPATH.", file=sys.stderr)
        return 2

    docs_dir = args.docs_dir
    methods = REGISTRY.list(status_filter="active")
    if not methods:
        print("No active methods in registry.")
        return 0

    all_diffs: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for spec in methods:
            method_ref = MethodRef(name=spec.name, version=spec.version)
            try:
                sk_path = KeyRing.generate_keypair(tmp / "_keys")
                kr = KeyRing(signing_key_path=sk_path)
                compile_method_doc(method_ref, tmp / "docs", kr)
            except Exception as e:
                all_diffs.append(f"Failed to compile {spec.name} v{spec.version}: {e}")
                continue

            committed = docs_dir / spec.name / spec.version
            recompiled = tmp / "docs" / spec.name / spec.version
            all_diffs.extend(check_drift(committed, recompiled))

    if all_diffs:
        print("Doc drift detected:", file=sys.stderr)
        for d in all_diffs:
            print(d, file=sys.stderr)
        return 1

    print("No doc drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
