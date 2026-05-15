#!/usr/bin/env python3
"""CI guard: docs/methods/MQS_Specification.md must agree with the MQS code.

The formal MQS specification pins a composite formula, a set of sub-score
weights, a gating threshold, and a registry of named constants. All of them
are defined in `noosphere/noosphere/evaluation/mqs.py` and mirrored in
`docs/methods/MQS_Specification.md`. This script reads both and fails CI if
they drift.

What is checked
---------------
1. The doc contains, verbatim, the canonical formula string `COMPOSITE_FORMULA`.
2. The doc names the MQS schema string `MQS_SCHEMA`.
3. The doc declares each `SUBSCORE_WEIGHTS` entry as `"<key>": <value>`.
4. The doc has a section header for each of the five criteria.
5. The doc lists each `COMPOSITE_TIERS` tier name with its lower bound.
6. **Bidirectional constants check.** The doc carries a "Constants registry"
   table; every row must match a key in `MQS_CONSTANTS` with an equal value,
   and every key in `MQS_CONSTANTS` must appear as a row. A constant in code
   but not the spec — or in the spec but not the code — fails CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "methods" / "MQS_Specification.md"
CODE_PATH = REPO_ROOT / "noosphere" / "noosphere" / "evaluation" / "mqs.py"

# A markdown table row whose first two cells are backtick-quoted, e.g.
#   | `DS_GATE_THRESHOLD` | `0.15` | Domain-Sensitivity gate threshold |
_REGISTRY_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")


def _load_canonical():
    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    from noosphere.evaluation.mqs import (  # type: ignore
        COMPOSITE_FORMULA,
        COMPOSITE_TIERS,
        MQS_CONSTANTS,
        MQS_SCHEMA,
        SUBSCORE_WEIGHTS,
    )

    return (
        COMPOSITE_FORMULA,
        dict(SUBSCORE_WEIGHTS),
        MQS_SCHEMA,
        dict(MQS_CONSTANTS),
        tuple(COMPOSITE_TIERS),
    )


def _missing(haystack: str, needle: str) -> bool:
    return needle not in haystack


def _values_match(code_value: object, doc_value: str) -> bool:
    """True when a doc table cell matches a code constant. Numbers compare
    with a float tolerance; everything else compares as a trimmed string."""
    doc_value = doc_value.strip().strip("`").strip()
    try:
        return abs(float(doc_value) - float(code_value)) < 1e-9  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return doc_value == str(code_value)


def _parse_registry_table(doc_text: str) -> dict[str, str]:
    """Parse the rows of the doc's "Constants registry" table into a
    {name: raw_value} map. Only rows under that heading are read, so other
    backtick tables in the spec are ignored."""
    lines = doc_text.splitlines()
    out: dict[str, str] = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = "constants registry" in stripped.lower()
            continue
        if not in_section:
            continue
        m = _REGISTRY_ROW_RE.match(stripped)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def main() -> int:
    if not DOC_PATH.exists():
        print(f"Missing doc: {DOC_PATH}", file=sys.stderr)
        return 2
    if not CODE_PATH.exists():
        print(f"Missing code module: {CODE_PATH}", file=sys.stderr)
        return 2

    try:
        formula, weights, schema, constants, tiers = _load_canonical()
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

    # Every composite tier and its lower bound must appear in the doc. The
    # bound may be rendered compactly (0.4) or with two decimals (0.40).
    for tier_name, lower in tiers:
        if tier_name not in doc_text:
            failures.append(f"Doc does not name composite tier '{tier_name}'.")
            continue
        renderings = {f"{lower:g}", f"{lower:.2f}"}
        bound_pat = re.compile(
            r"\b(" + "|".join(re.escape(r) for r in renderings) + r")\b"
        )
        if not bound_pat.search(doc_text):
            failures.append(
                f"Doc does not state the lower bound {lower:g} for tier "
                f"'{tier_name}'."
            )

    # ── Bidirectional constants check ──────────────────────────────────────
    doc_constants = _parse_registry_table(doc_text)
    if not doc_constants:
        failures.append(
            "Doc has no parseable 'Constants registry' table — expected a "
            "section '## Constants registry' with rows "
            "`| `NAME` | `VALUE` | ... |`."
        )
    else:
        for name, code_value in constants.items():
            if name not in doc_constants:
                failures.append(
                    f"Constant '{name}' is in MQS_CONSTANTS but not in the "
                    f"doc's constants registry."
                )
                continue
            if not _values_match(code_value, doc_constants[name]):
                failures.append(
                    f"Constant '{name}': doc value "
                    f"'{doc_constants[name]}' != code value '{code_value}'."
                )
        for name in doc_constants:
            if name not in constants:
                failures.append(
                    f"Constant '{name}' is in the doc's constants registry "
                    f"but not in MQS_CONSTANTS."
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
