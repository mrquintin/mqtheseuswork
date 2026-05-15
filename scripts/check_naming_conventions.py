#!/usr/bin/env python3
"""CI gate for the naming convention pass.

This is the *gate* counterpart to `survey_naming_violations.py`.

The survey is informational; this script fails CI when a violation is
seen that is **not** on the approved allowlist below. The allowlist
encodes the deliberate exceptions (signed-input fields, third-party
APIs, Qt overrides, http.server overrides, etc.) so that CI can
distinguish drift introduced by new code from violations the firm has
explicitly chosen to keep.

Run:

    python scripts/check_naming_conventions.py             # full repo
    python scripts/check_naming_conventions.py --baseline  # write the
        current set of violations to .cache/naming_baseline.json. Used
        once at the start of a convention pass to grandfather in the
        existing drift; after that the gate fails only on *new*
        violations.
    python scripts/check_naming_conventions.py --strict    # ignore the
        baseline and fail on any non-allowlisted violation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse the survey's walkers so the gate and the survey see exactly
# the same set of violations.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from survey_naming_violations import (  # noqa: E402
    REPO_ROOT,
    SurveyReport,
    survey_prisma,
    survey_python,
    survey_typescript,
    survey_urls,
)

# Explicit allowlist of (kind, name) pairs we will not flag.
# Each entry MUST carry a one-line justification.
ALLOWLIST: set[tuple[str, str]] = {
    # Qt overrides — names mandated by PyQt5/PySide6, cannot be renamed.
    ("python_function", "keyPressEvent"),
    ("python_function", "closeEvent"),
    ("python_function", "resizeEvent"),
    ("python_function", "paintEvent"),
    ("python_function", "showEvent"),
    ("python_function", "hideEvent"),
    ("python_function", "mousePressEvent"),
    ("python_function", "mouseReleaseEvent"),
    ("python_function", "mouseMoveEvent"),
    ("python_function", "wheelEvent"),
    # http.server overrides — names mandated by stdlib.
    ("python_function", "do_GET"),
    ("python_function", "do_POST"),
    ("python_function", "do_PUT"),
    ("python_function", "do_DELETE"),
    ("python_function", "do_HEAD"),
    ("python_function", "do_OPTIONS"),
    # Dunder test hooks (intentional leading-double-underscore tag).
    ("ts_function", "__setMailSendersForTesting"),
    ("ts_function", "__resetMailSendersForTesting"),
    ("ts_const", "__test"),
    ("ts_const", "__test__"),
    # Mathematical / linear-algebra identifiers — convention break is
    # deliberate to mirror the math (`Xv`, the matrix-vector product).
    ("ts_const", "Xv"),
    # Test-suite imports of third-party classes — the binding name
    # mirrors the foreign API.
    ("ts_const", "EventEmitter"),
}

# Allowlisted *patterns*. A violation matches if its name starts with
# any of the prefixes below; used for families like
# `test_X_kicks_in_above_K` where the trailing `_K`/`_N` is by design
# (capital denotes a configurable threshold, not a class).
ALLOWLIST_PREFIXES: tuple[tuple[str, str], ...] = (
    # Round 3: tests that explicitly invoke "above K" / "below N"
    # semantics in the name. The capital is the math, not a class.
    ("python_function", "test_typed_confirmation_kicks_in_above_K"),
    ("python_function", "test_question_goes_amber_after_K_turns_then_red"),
    ("python_function", "test_detects_missing_withGated"),
)

# Kinds that are *advisory only* in CI — they are surfaced by the
# survey for follow-up but never fail the build, because resolving
# them requires a data migration, founder approval, or both.
ADVISORY_KINDS = {
    "prisma_column",   # rename = data migration
    "url_segment",     # rename = breaks external links unless aliased
    "url_param",       # rename = breaks external links unless aliased
}

# Baseline lives alongside the gate so it is committed with CI's
# configuration. Refresh it deliberately via `--baseline` after a
# convention pass; do *not* refresh it just to make CI pass — that
# would defeat the gate.
BASELINE_PATH = REPO_ROOT / "scripts" / "naming_baseline.json"


def collect() -> SurveyReport:
    report = SurveyReport()
    survey_python(report, REPO_ROOT)
    survey_typescript(report, REPO_ROOT / "theseus-codex" / "src")
    survey_urls(report, REPO_ROOT)
    survey_prisma(report, REPO_ROOT)
    return report


def is_allowlisted(kind: str, name: str) -> bool:
    if (kind, name) in ALLOWLIST:
        return True
    for ak, prefix in ALLOWLIST_PREFIXES:
        if ak == kind and name.startswith(prefix):
            return True
    return False


def violation_key(v: dict) -> str:
    """Stable key for baseline comparison.

    Includes path + line so that a rename in the same file doesn't
    accidentally silence a *new* violation later, but excludes the
    `note` field (which is descriptive, not identifying).
    """
    return f"{v['kind']}::{v['name']}::{v['path']}::{v.get('line') or ''}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Write the current violations to the baseline and exit 0.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any non-allowlisted violation, ignoring the baseline.",
    )
    args = parser.parse_args()

    report = collect()

    # Filter to enforced kinds and remove allowlisted entries.
    enforced: list[dict] = []
    for v in report.violations:
        d = {
            "kind": v.kind,
            "name": v.name,
            "path": v.path,
            "line": v.line,
            "expected": v.expected,
            "requires_founder_approval": v.requires_founder_approval,
        }
        if d["kind"] in ADVISORY_KINDS:
            continue
        if is_allowlisted(d["kind"], d["name"]):
            continue
        enforced.append(d)

    if args.baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(
                {"violations": enforced},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(
            f"wrote {len(enforced)} grandfathered violations to "
            f"{BASELINE_PATH.relative_to(REPO_ROOT)}"
        )
        return 0

    baseline_keys: set[str] = set()
    if not args.strict and BASELINE_PATH.is_file():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            baseline_keys = {violation_key(v) for v in baseline.get("violations", [])}
        except (OSError, json.JSONDecodeError) as e:
            print(f"warning: could not read baseline ({e}); running in strict mode")

    new_violations = [v for v in enforced if violation_key(v) not in baseline_keys]
    if not new_violations:
        print(
            f"OK — {len(enforced)} grandfathered, "
            f"0 new naming violations."
        )
        return 0

    print(f"FAIL — {len(new_violations)} new naming violation(s):")
    for v in new_violations:
        loc = f"{v['path']}:{v['line']}" if v["line"] else v["path"]
        print(f"  [{v['kind']}] {v['name']} at {loc} (expected {v['expected']})")
    print()
    print("If a violation is intentional, add it to ALLOWLIST in")
    print("scripts/check_naming_conventions.py with a one-line reason.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
