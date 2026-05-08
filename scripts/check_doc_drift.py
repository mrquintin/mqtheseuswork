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
import re
import sys
import tempfile
from pathlib import Path

GENERATED_FILES = {"spec.md", "examples.md", "calibration.md", "transfer.md", "operations.md", "index.md"}
HAND_AUTHORED = {"rationale.md"}

# RATIONALE.md files are next to each method's source (not under
# docs/methods/). They are hand-authored and may name dependencies in
# free prose; the depends_on= declaration in code is the authoritative
# contract. We compare the two sets so a doc that lists a dep the code
# does not declare (or vice versa) fails CI.
RATIONALE_SUFFIX = ".RATIONALE.md"


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


def check_depends_on_rationale_drift(
    methods_dir: Path,
    declared_by_method: dict[str, list[str]],
    known_method_names: set[str],
) -> list[str]:
    """Compare each method's RATIONALE.md against its declared
    ``depends_on`` set. A drift is a method *named* in the RATIONALE
    that is also a registered method, but is NOT listed in the code's
    ``depends_on``. The reverse direction (declared in code but not
    mentioned in the doc) is also flagged so authors update the
    rationale when they wire up a new edge.

    The matcher is conservative — we look for exact-token method names
    inside RATIONALE.md so prose like "the prediction extractor" does
    not false-positive on ``extract_prediction`` while still catching a
    direct mention.
    """
    diffs: list[str] = []
    if not methods_dir.exists():
        return diffs
    for path in sorted(methods_dir.glob(f"*{RATIONALE_SUFFIX}")):
        method_name = path.name[: -len(RATIONALE_SUFFIX)]
        if method_name not in declared_by_method:
            # Method has a rationale but no declaration on file (e.g.
            # not yet imported by this CI run). Skip silently.
            continue
        body = path.read_text(encoding="utf-8")
        # Extract "word characters with underscores" ≥ 3 chars.
        tokens = set(re.findall(r"\b[a-z][a-z0-9_]{2,}\b", body))
        mentioned = tokens & known_method_names
        # Exclude self-mentions and the method's own name.
        mentioned.discard(method_name)
        declared = set(declared_by_method.get(method_name, []))

        only_in_doc = sorted(mentioned - declared - {method_name})
        only_in_code = sorted(declared - mentioned)

        if only_in_doc:
            diffs.append(
                f"{path.name}: RATIONALE names registered methods "
                f"{only_in_doc!r} but the decorator's depends_on does not "
                f"declare them — either add to depends_on or rephrase the "
                f"prose so it does not look like a dependency claim."
            )
        if only_in_code:
            diffs.append(
                f"{path.name}: depends_on declares {only_in_code!r} but "
                f"the RATIONALE never names them — update the rationale "
                f"to explain why the method composes them."
            )
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for doc drift")
    parser.add_argument("--docs-dir", type=Path, default=Path("docs/methods"))
    parser.add_argument(
        "--methods-dir",
        type=Path,
        default=Path("noosphere/noosphere/methods"),
        help="Where method source + RATIONALE.md files live.",
    )
    parser.add_argument(
        "--skip-rationale-drift",
        action="store_true",
        help="Skip the RATIONALE.md ↔ depends_on consistency check.",
    )
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

    # depends_on ↔ RATIONALE.md drift is registry-only and does NOT
    # require the docgen toolchain (jinja2 etc). Run it first so a fast
    # CI lane can catch typos without booting the full doc compiler.
    early_diffs: list[str] = []
    if not args.skip_rationale_drift:
        try:
            from noosphere.methods._registry import REGISTRY as _EARLY_REGISTRY
            # Import all method modules so REGISTRY is populated.
            import importlib as _il
            import pkgutil as _pk
            import noosphere.methods as _methods_pkg
            for _info in _pk.iter_modules(_methods_pkg.__path__):
                if _info.name.startswith("_") or _info.name in {"composition", "failure_modes"}:
                    continue
                try:
                    _il.import_module(f"noosphere.methods.{_info.name}")
                except Exception:  # tolerate optional deps; the catalog check is best-effort
                    continue
            declared: dict[str, list[str]] = {}
            for spec in _EARLY_REGISTRY.list():
                declared[spec.name] = _EARLY_REGISTRY.get_depends_on(spec.name)
            known = _EARLY_REGISTRY.known_method_names()
            early_diffs.extend(
                check_depends_on_rationale_drift(args.methods_dir, declared, known)
            )
        except ImportError as exc:
            print(
                f"warning: skipping depends_on ↔ RATIONALE drift check ({exc})",
                file=sys.stderr,
            )

    # Full drift check requires recompilation — import here to avoid import cost in pre-commit mode
    try:
        from noosphere.docgen.compiler import compile_method_doc, TEMPLATE_VERSION
        from noosphere.ledger.keys import KeyRing
        from noosphere.methods._registry import REGISTRY
        from noosphere.models import MethodRef
    except ImportError as e:
        # If we have nothing to report from the early pass, that's a hard
        # error like before. Otherwise, surface the rationale-drift
        # findings even when the heavyweight compiler is unavailable.
        if early_diffs:
            print("Doc drift detected (rationale-only run):", file=sys.stderr)
            for d in early_diffs:
                print(d, file=sys.stderr)
            return 1
        print(f"Cannot import noosphere modules: {e}", file=sys.stderr)
        print("Run from project root with noosphere on PYTHONPATH.", file=sys.stderr)
        return 2

    docs_dir = args.docs_dir
    methods = REGISTRY.list(status_filter="active")
    if not methods:
        print("No active methods in registry.")
        return 0

    all_diffs: list[str] = list(early_diffs)
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
