#!/usr/bin/env python3
"""CI gate — `os.getenv` / `process.env.X` reads are forbidden outside
the central config modules.

This is the enforcement counterpart to the Round 17 configuration
consolidation (see ``docs/architecture/Configuration.md``).

The contract:
- Python: only ``noosphere/noosphere/core/config.py`` (and the legacy
  shim at ``noosphere/noosphere/config.py``) may call ``os.getenv`` /
  ``os.environ.get`` / ``os.environ[...]``.
- TypeScript: only ``theseus-codex/src/lib/config.ts`` may reference
  ``process.env.X``.

Existing call-sites are grandfathered through a baseline file at
``scripts/no_inline_env_reads_baseline.json`` (per-file violation
counts). The gate fails when a new file appears, or when an existing
file's count grows. The baseline is intended to *shrink* — when a file
is migrated to the central settings object, drop its baseline entry.

Run::

    python scripts/check_no_inline_env_reads.py             # gate
    python scripts/check_no_inline_env_reads.py --strict    # ignore baseline
    python scripts/check_no_inline_env_reads.py --baseline  # rewrite baseline
    python scripts/check_no_inline_env_reads.py --report    # print full inventory
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "scripts" / "no_inline_env_reads_baseline.json"

# Files explicitly allowed to read env vars directly. Keep this list
# tight — every entry must have a one-line justification.
PY_ALLOWED: set[str] = {
    # The central config module reads env (this is the whole point).
    "noosphere/noosphere/core/config.py",
    # Legacy shim re-exports from core; kept until callers migrate.
    "noosphere/noosphere/config.py",
    # The CI gate itself talks about the patterns (string literals
    # only, no live reads), but excluding it keeps false positives
    # from "os.getenv" appearing in our error messages.
    "scripts/check_no_inline_env_reads.py",
}

TS_ALLOWED: set[str] = {
    # The central TS config module reads process.env (whole point).
    "theseus-codex/src/lib/config.ts",
    # The tests for the central TS config must touch process.env to
    # exercise the env-parsing code paths.
    "theseus-codex/src/__tests__/config.test.ts",
}

# Roots we walk. Keep narrow — third-party / generated trees don't count.
PY_ROOTS = (
    "noosphere/noosphere",
    "noosphere/scripts",
    "current_events_api",
    "dialectic",
    "scripts",
    "researcher_api",
)

TS_ROOTS = (
    "theseus-codex/src",
    "theseus-codex/scripts",
    "theseus-codex/desktop",
    "theseus-codex/e2e",
    "theseus-codex/playwright",
    "theseus-codex/playwright.config.ts",
    "theseus-codex/next.config.ts",
    "theseus-public/src",
)

PY_PATTERNS = (
    re.compile(r"\bos\.getenv\s*\("),
    re.compile(r"\bos\.environ\s*\.\s*get\s*\("),
    re.compile(r"\bos\.environ\s*\["),
)

TS_PATTERN = re.compile(r"\bprocess\s*\.\s*env\s*\.\s*[A-Z_][A-Z0-9_]*")
# Also match `process.env["X"]` and destructuring on `process.env`.
TS_BRACKET_PATTERN = re.compile(r"\bprocess\s*\.\s*env\s*\[")


def _iter_files(roots: Iterable[str], suffixes: tuple[str, ...]) -> Iterable[Path]:
    for root in roots:
        rooted = REPO_ROOT / root
        if rooted.is_file():
            yield rooted
            continue
        if not rooted.is_dir():
            continue
        for path in rooted.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            # Skip generated / vendored trees.
            parts = set(path.parts)
            if parts & {"node_modules", ".next", "_generated", "__pycache__"}:
                continue
            yield path


def _strip_comments_and_strings(text: str, *, lang: str) -> str:
    """Conservative strip so `os.getenv` inside a docstring or # comment
    isn't counted. We don't need a real parser — replacing string and
    comment runs with whitespace of equal length preserves line numbers.
    """

    if lang == "python":
        # Triple-quoted strings.
        text = re.sub(
            r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
            lambda m: " " * len(m.group(0)),
            text,
        )
        # Single-line strings (greedy enough for our purpose).
        text = re.sub(
            r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
            lambda m: " " * len(m.group(0)),
            text,
        )
        # `#` line comments.
        text = re.sub(
            r"#[^\n]*",
            lambda m: " " * len(m.group(0)),
            text,
        )
        return text

    # TypeScript / JS.
    # Block comments.
    text = re.sub(
        r"/\*[\s\S]*?\*/",
        lambda m: " " * len(m.group(0)),
        text,
    )
    # Line comments.
    text = re.sub(
        r"//[^\n]*",
        lambda m: " " * len(m.group(0)),
        text,
    )
    # Strings (single, double, backtick — backticks may contain
    # `${...}` expressions but we accept the false negative; the goal
    # is to suppress noise, not parse template literals).
    text = re.sub(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`',
        lambda m: " " * len(m.group(0)),
        text,
    )
    return text


def _count_python(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    cleaned = _strip_comments_and_strings(text, lang="python")
    return sum(len(p.findall(cleaned)) for p in PY_PATTERNS)


def _count_typescript(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    cleaned = _strip_comments_and_strings(text, lang="typescript")
    return len(TS_PATTERN.findall(cleaned)) + len(
        TS_BRACKET_PATTERN.findall(cleaned)
    )


def collect_violations() -> dict[str, int]:
    """Return {repo-relative-path: violation-count} for non-allowed files."""

    violations: dict[str, int] = {}

    for path in _iter_files(PY_ROOTS, (".py",)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in PY_ALLOWED:
            continue
        count = _count_python(path)
        if count:
            violations[rel] = count

    for path in _iter_files(TS_ROOTS, (".ts", ".tsx")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in TS_ALLOWED:
            continue
        count = _count_typescript(path)
        if count:
            violations[rel] = count

    return violations


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.is_file():
        return {}
    try:
        loaded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(k): int(v) for k, v in loaded.items() if isinstance(v, int)}


def write_baseline(violations: dict[str, int]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(dict(sorted(violations.items())), indent=2) + "\n",
        encoding="utf-8",
    )


def diff_against_baseline(
    current: dict[str, int],
    baseline: dict[str, int],
) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """Return (new_files, regressed_files).

    - new_files: paths in current that are not in baseline.
    - regressed_files: paths whose count grew vs baseline (old, new).
    """

    new_files = {p: c for p, c in current.items() if p not in baseline}
    regressed: dict[str, tuple[int, int]] = {}
    for path, count in current.items():
        old = baseline.get(path)
        if old is not None and count > old:
            regressed[path] = (old, count)
    return new_files, regressed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Rewrite the baseline to match current violations and exit 0.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Ignore the baseline and fail on ANY non-allowed env read.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the full inventory of non-allowed env reads and exit 0.",
    )
    args = parser.parse_args()

    violations = collect_violations()

    if args.report:
        for path, count in sorted(violations.items()):
            print(f"{count:4d}  {path}")
        print(f"--- total: {sum(violations.values())} reads "
              f"across {len(violations)} files")
        return 0

    if args.baseline:
        write_baseline(violations)
        print(
            f"Wrote baseline with {len(violations)} files / "
            f"{sum(violations.values())} reads to "
            f"{BASELINE_PATH.relative_to(REPO_ROOT)}"
        )
        return 0

    if args.strict:
        if not violations:
            return 0
        print(
            "[no-inline-env-reads] strict mode: "
            f"{len(violations)} file(s) read env directly:",
            file=sys.stderr,
        )
        for path, count in sorted(violations.items()):
            print(f"  {path}: {count} reads", file=sys.stderr)
        return 1

    baseline = load_baseline()
    new_files, regressed = diff_against_baseline(violations, baseline)

    if not new_files and not regressed:
        return 0

    print(
        "[no-inline-env-reads] new direct env reads detected. "
        "Move these through the central config module:",
        file=sys.stderr,
    )
    print(
        "  - Python: noosphere/noosphere/core/config.py "
        "(get_settings())",
        file=sys.stderr,
    )
    print(
        "  - TypeScript: theseus-codex/src/lib/config.ts "
        "(`config` import)",
        file=sys.stderr,
    )
    print(
        "See docs/architecture/Configuration.md.",
        file=sys.stderr,
    )

    if new_files:
        print("\nNew files reading env directly:", file=sys.stderr)
        for path, count in sorted(new_files.items()):
            print(f"  + {path}: {count} reads", file=sys.stderr)

    if regressed:
        print(
            "\nFiles whose env-read count grew vs baseline:",
            file=sys.stderr,
        )
        for path, (old, new) in sorted(regressed.items()):
            print(f"  ↑ {path}: {old} → {new}", file=sys.stderr)

    print(
        "\nIf the new reads are unavoidable (e.g. you migrated a file "
        "and the count legitimately changed), regenerate the baseline:",
        file=sys.stderr,
    )
    print(
        "  python scripts/check_no_inline_env_reads.py --baseline",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
