#!/usr/bin/env python3
"""CI guard: docs/architecture/Schema_Audit_Round18.md must agree with
the actual Prisma schema it audits.

The audit document inventories Round-17 models, names indices it
considers redundant, and documents the FK / timestamp conventions. If
the schema gains a new model, drops one, or moves a previously-flagged
index back in, the audit drifts and a future reader gets a misleading
picture. This script runs in CI to keep the two files honest.

Checks:

1. Every Round-17 model named in `schema-shape.test.ts`'s `ROUND_17`
   array exists in `schema.prisma` AND is mentioned by name in the
   audit doc. The two lists are coupled by THIS script.

2. Every model that the audit's §1 inventory table mentions in a
   `Model` cell of the inventory grid actually exists in the schema —
   so a deletion would be caught.

3. The audit's "indices dropped" section names indices that are NOT
   present in the live schema text. If a dropped index reappears, the
   audit is lying.

4. The schema parses to at least 40 models — defends against parser
   regression that would silently pass every other check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "theseus-codex" / "prisma" / "schema.prisma"
AUDIT_PATH = REPO_ROOT / "docs" / "architecture" / "Schema_Audit_Round18.md"
SHAPE_TEST_PATH = (
    REPO_ROOT / "theseus-codex" / "src" / "__tests__" / "schema-shape.test.ts"
)

MODEL_RE = re.compile(r"^model\s+(\w+)\s*\{", re.MULTILINE)


def _read(path: Path) -> str:
    if not path.exists():
        print(f"ERROR: missing required file: {path}", file=sys.stderr)
        sys.exit(2)
    return path.read_text(encoding="utf-8")


def _models_in_schema(schema: str) -> list[str]:
    return MODEL_RE.findall(schema)


def _round17_list_from_test(test_src: str) -> list[str]:
    # Mirror the ROUND_17 array in src/__tests__/schema-shape.test.ts.
    # We parse it textually rather than imitating it here so the two
    # files stay coupled.
    m = re.search(
        r"const\s+ROUND_17\s*=\s*\[(.*?)\];",
        test_src,
        re.DOTALL,
    )
    if not m:
        print(
            "ERROR: ROUND_17 array not found in schema-shape.test.ts",
            file=sys.stderr,
        )
        sys.exit(2)
    body = m.group(1)
    return re.findall(r'"(\w+)"', body)


def _model_names_referenced_in_audit(audit: str) -> set[str]:
    # Pull anything that looks like a PascalCase identifier appearing in
    # backticks. Filter out:
    #   * Prisma FK action keywords (Cascade, Restrict, NoAction, SetNull)
    #   * Hypothetical / never-existed models the audit explicitly
    #     names as NOT existing (e.g. the hypothetical duplicates §4
    #     considers and rejects)
    #   * Generic Prisma type names that may appear in prose
    candidates = set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", audit))
    # Plausible-model filter: at least one lowercase letter (excludes
    # acronyms like `MQS`, `JSON`).
    candidates = {c for c in candidates if re.search(r"[a-z]", c)}
    NOT_MODELS = {
        # Prisma FK action keywords
        "Cascade",
        "Restrict",
        "NoAction",
        "SetNull",
        # Prisma scalar / type names
        "DateTime",
        "Boolean",
        "String",
        "Float",
        "Int",
        "Json",
        "Bytes",
        # Hypothetical / never-existed models the audit considers and
        # rejects (see §4 of the audit doc)
        "MethodCalibration",
        "MethodOutcome",
        "MethodFailureMode",
        "MethodDriftEvent",
        # Misc identifiers in prose / keywords
        "Value",
    }
    return candidates - NOT_MODELS


def _dropped_indices_from_audit(audit: str) -> list[str]:
    # Pulls index names mentioned under §5.1 "Indices dropped".
    section = re.search(
        r"### 5\.1 Indices dropped(.*?)### 5\.2",
        audit,
        re.DOTALL,
    )
    if not section:
        return []
    return re.findall(r"`([A-Za-z]+_[A-Za-z_]+_idx)`", section.group(1))


def _index_present(schema: str, index_name: str) -> bool:
    # Index names like `Founder_organizationId_idx` correspond to
    # `@@index([organizationId])` inside `model Founder`. Decompose and
    # check the schema text.
    m = re.match(r"^([A-Z]\w+)_(.+)_idx$", index_name)
    if not m:
        return False
    model, cols = m.group(1), m.group(2)
    cols_token = "[" + ", ".join(cols.split("_")) + "]"
    block = re.search(
        rf"^model\s+{model}\s*\{{(.*?)^\}}",
        schema,
        re.DOTALL | re.MULTILINE,
    )
    if not block:
        return False
    return f"@@index({cols_token})" in block.group(1)


def main() -> int:
    schema = _read(SCHEMA_PATH)
    audit = _read(AUDIT_PATH)
    shape = _read(SHAPE_TEST_PATH)

    failures: list[str] = []

    schema_models = _models_in_schema(schema)
    if len(schema_models) < 40:
        failures.append(
            f"schema.prisma parsed only {len(schema_models)} models "
            f"(expected at least 40) — parser is wrong or schema regressed."
        )
    schema_set = set(schema_models)

    # 1 + 3. Round-17 list in the test must be a subset of schema models
    #         AND every entry must be mentioned in the audit doc.
    round17 = _round17_list_from_test(shape)
    if not round17:
        failures.append(
            "ROUND_17 list in schema-shape.test.ts parsed empty — refusing "
            "to declare consistency."
        )
    for name in round17:
        if name not in schema_set:
            failures.append(
                f"schema-shape.test.ts ROUND_17 lists `{name}` but the "
                f"schema has no such model."
            )
        if name not in audit:
            failures.append(
                f"schema-shape.test.ts ROUND_17 lists `{name}` but the "
                f"audit doc never mentions it."
            )

    # 2. Every Model name appearing in the audit's inventory must still
    #    exist in the schema (catches a model deletion the audit didn't
    #    learn about).
    for name in _model_names_referenced_in_audit(audit):
        if name not in schema_set:
            failures.append(
                f"Audit doc references model `{name}` that no longer exists "
                f"in schema.prisma — update the audit or restore the model."
            )

    # 4. Indices the audit claims it dropped must actually be absent.
    for idx in _dropped_indices_from_audit(audit):
        if _index_present(schema, idx):
            failures.append(
                f"Audit claims index `{idx}` was dropped, but it is still "
                f"present in schema.prisma."
            )

    if failures:
        print("Schema/audit consistency check FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"OK — schema ({len(schema_models)} models) and "
        f"Schema_Audit_Round18.md agree."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
