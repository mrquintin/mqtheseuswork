#!/usr/bin/env python3
"""CI guard: docs/methods/MQS_Specification.md must agree with the MQS code.

The composite formula and the sub-score weights are defined in two places —
`noosphere/noosphere/evaluation/mqs.py` and
`docs/methods/MQS_Specification.md`. This script reads both and fails CI if
they drift.

The doc must contain, verbatim, the canonical formula string defined in code:

    COMPOSITE_FORMULA = "domain_sensitivity * mean(progressivity, severity, aim_method_fit, compressibility)"

It must also list each weight from `SUBSCORE_WEIGHTS` in the form
`"<key>": <value>`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "methods" / "MQS_Specification.md"
CODE_PATH = (
    REPO_ROOT / "noosphere" / "noosphere" / "evaluation" / "mqs.py"
)


def _load_canonical() -> tuple[str, dict[str, float], str]:
    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    from noosphere.evaluation.mqs import (  # type: ignore
        COMPOSITE_FORMULA,
        MQS_SCHEMA,
        SUBSCORE_WEIGHTS,
    )

    return COMPOSITE_FORMULA, dict(SUBSCORE_WEIGHTS), MQS_SCHEMA


def _missing(haystack: str, needle: str) -> bool:
    return needle not in haystack


def main() -> int:
    if not DOC_PATH.exists():
        print(f"Missing doc: {DOC_PATH}", file=sys.stderr)
        return 2
    if not CODE_PATH.exists():
        print(f"Missing code module: {CODE_PATH}", file=sys.stderr)
        return 2

    try:
        formula, weights, schema = _load_canonical()
    except Exception as exc:
        print(f"Cannot import canonical MQS constants: {exc}", file=sys.stderr)
        return 2

    doc_text = DOC_PATH.read_text(encoding="utf-8")
    failures: list[str] = []

    if _missing(doc_text, formula):
        failures.append(
            f"Doc does not contain the canonical composite formula:\n  {formula}"
        )

    if _missing(doc_text, schema):
        failures.append(f"Doc does not name the MQS schema string: {schema}")

    for key, value in weights.items():
        # Accept either "key": <number> or 'key': <number> in any whitespace.
        pat = re.compile(
            rf'["\']?{re.escape(key)}["\']?\s*[:=]\s*(0(?:\.\d+)?|1(?:\.0+)?)'
        )
        match = pat.search(doc_text)
        if not match:
            failures.append(
                f"Doc does not declare a numeric weight for '{key}'."
            )
            continue
        if abs(float(match.group(1)) - float(value)) > 1e-9:
            failures.append(
                f"Doc weight for '{key}' = {match.group(1)} does not match "
                f"code value {value}."
            )

    # Each criterion section must exist by name so reviewers can navigate it.
    for required_section in (
        "progressivity",
        "severity",
        "aim_method_fit",
        "compressibility",
        "domain_sensitivity",
    ):
        if required_section not in doc_text:
            failures.append(
                f"Doc is missing a section for criterion '{required_section}'."
            )

    if failures:
        print("MQS doc/code drift detected:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nUpdate docs/methods/MQS_Specification.md or "
            "noosphere/noosphere/evaluation/mqs.py until they agree.",
            file=sys.stderr,
        )
        return 1

    print("MQS doc and code agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
