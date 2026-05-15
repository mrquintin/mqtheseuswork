#!/usr/bin/env python3
"""CI invariant: the dead-code candidate count must not regress.

The committed `docs/architecture/Dead_Code_Survey.md` contains two
auto-generated tables (TypeScript via ts-prune, Python via vulture). Each
row is one candidate. The total row count is treated as a *ratchet*:
new commits may reduce it or hold it steady, but a PR that raises the
total without first updating the survey fails this check.

This protects against silent regressions — orphaned exports added by new
work — without forcing a binary "zero dead code" rule that would block
useful refactors mid-flight.

Usage:
  python3 scripts/check_dead_code_no_regression.py
  python3 scripts/check_dead_code_no_regression.py --baseline 200
  python3 scripts/check_dead_code_no_regression.py --update-survey

Exit codes:
  0   total candidate count <= baseline
  1   candidate count grew; survey must be regenerated and reviewed
  2   environment broken (ts-prune / vulture unavailable)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SURVEY = REPO / "docs" / "architecture" / "Dead_Code_Survey.md"
TC = REPO / "theseus-codex"

# The baseline is read from the committed survey unless overridden. If the
# survey says "TypeScript candidates (ts-prune, 174 rows)" then 174 is the
# ratchet — a future scan may not exceed it.
BASELINE_RE_TS = re.compile(r"TypeScript candidates \(ts-prune, (\d+) rows\)")
BASELINE_RE_PY = re.compile(r"Python candidates \(vulture[^,]*, (\d+) rows\)")


def _read_committed_baselines() -> tuple[int, int]:
    if not SURVEY.exists():
        print(f"check_dead_code: missing {SURVEY}", file=sys.stderr)
        sys.exit(2)
    text = SURVEY.read_text(encoding="utf-8")
    m_ts = BASELINE_RE_TS.search(text)
    m_py = BASELINE_RE_PY.search(text)
    if not m_ts or not m_py:
        print(
            "check_dead_code: baseline row counts not found in survey "
            "(regenerate with scripts/run_dead_code_survey.sh).",
            file=sys.stderr,
        )
        sys.exit(2)
    return int(m_ts.group(1)), int(m_py.group(1))


def _run_ts_prune() -> int:
    if shutil.which("node") is None:
        print("check_dead_code: 'node' not on PATH.", file=sys.stderr)
        sys.exit(2)
    proc = subprocess.run(
        ["npx", "-y", "ts-prune@0.10.3", "-p", "tsconfig.json"],
        cwd=TC,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = []
    for raw in proc.stdout.splitlines():
        if raw.startswith(".next/"):
            continue
        if raw.endswith("(used in module)"):
            continue
        if not raw.strip():
            continue
        lines.append(raw)
    return len(lines)


def _run_vulture() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "vulture", "noosphere/", "--min-confidence", "70"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1, 3):
        # vulture exits 1 when it finds dead code, 3 on internal error.
        print(
            f"check_dead_code: vulture exited {proc.returncode}: "
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(2)
    return sum(1 for line in proc.stdout.splitlines() if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-ts",
        type=int,
        default=None,
        help="Override TypeScript ratchet (default: read from survey doc).",
    )
    parser.add_argument(
        "--baseline-py",
        type=int,
        default=None,
        help="Override Python ratchet (default: read from survey doc).",
    )
    parser.add_argument(
        "--skip-ts",
        action="store_true",
        help="Skip the TypeScript scan (useful if Node is unavailable).",
    )
    parser.add_argument(
        "--skip-py",
        action="store_true",
        help="Skip the Python scan.",
    )
    args = parser.parse_args()

    base_ts, base_py = _read_committed_baselines()
    if args.baseline_ts is not None:
        base_ts = args.baseline_ts
    if args.baseline_py is not None:
        base_py = args.baseline_py

    failures: list[str] = []

    if not args.skip_ts:
        ts_now = _run_ts_prune()
        print(f"ts-prune candidates: {ts_now} (baseline {base_ts})")
        if ts_now > base_ts:
            failures.append(
                f"TypeScript dead-code count grew: {ts_now} > {base_ts}. "
                f"Run scripts/run_dead_code_survey.sh and triage the new rows."
            )

    if not args.skip_py:
        py_now = _run_vulture()
        print(f"vulture candidates:  {py_now} (baseline {base_py})")
        if py_now > base_py:
            failures.append(
                f"Python dead-code count grew: {py_now} > {base_py}. "
                f"Run scripts/run_dead_code_survey.sh and triage the new rows."
            )

    if failures:
        for f in failures:
            print(f"::error::{f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
