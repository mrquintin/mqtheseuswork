#!/usr/bin/env python3
"""Migration linearity check.

Reads the Prisma migrations directory and asserts that no two migrations
touch the same table in mutually-contradictory ways. Contradictions covered:

  * a CREATE TABLE for a table after a DROP TABLE for that table, with no
    intervening re-create;
  * a DROP COLUMN followed by a later migration that references the same
    (table, column) it just dropped (ADD COLUMN with the same name is fine
    -- that is a re-add, not a contradiction; ALTER on a dropped column is
    not);
  * two ADD COLUMN statements creating the same (table, column) without a
    DROP COLUMN between them.

The check runs against the on-disk Prisma migration files in lexicographic
order, which matches Prisma's apply order. Failures print a tabular report
and exit non-zero. The goal is a fast static gate that catches obvious
non-linear history before `prisma migrate deploy` runs against production.

Usage:
    python scripts/check_migration_linearity.py
    python scripts/check_migration_linearity.py --migrations-dir <path>

Exit codes:
    0  no contradictions detected.
    1  contradictions detected; tabular report printed to stdout.
    2  configuration error (directory missing, unreadable, etc.).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "theseus-codex" / "prisma" / "migrations"
DEFAULT_ALEMBIC_DIR = REPO_ROOT / "noosphere" / "alembic" / "versions"

# Directories inside the Prisma migrations dir that are NOT migrations and
# should be skipped by linearity checks. The "round18_consolidation" directory
# is a documentation-only consolidation note, kept for history.
_PRISMA_NON_MIGRATION_DIRS = {"round18_consolidation"}

# 14-digit YYYYMMDDHHMMSS prefix followed by _<name>.
_PRISMA_PREFIX_RE = re.compile(r"^(\d{14})_[A-Za-z0-9_]+$")


# Regexes target the SQL Prisma emits. They are intentionally permissive about
# trailing whitespace and quoted identifiers but require an explicit table name.
_CREATE_TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)
_DROP_TABLE_RE = re.compile(
    r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)
_ALTER_TABLE_RE = re.compile(
    r'ALTER\s+TABLE\s+(?:ONLY\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?\s+(.*?)(?:;|$)',
    re.IGNORECASE | re.DOTALL,
)
_ADD_COLUMN_RE = re.compile(
    r'ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)
_DROP_COLUMN_RE = re.compile(
    r'DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?"?([A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Operation:
    kind: str  # CREATE_TABLE | DROP_TABLE | ADD_COLUMN | DROP_COLUMN
    table: str
    column: str | None
    migration: str


@dataclass(frozen=True)
class Contradiction:
    table: str
    column: str | None
    kind: str
    first_migration: str
    second_migration: str
    explanation: str


def _strip_sql_comments(sql: str) -> str:
    # Remove `--` single-line comments and /* */ blocks so we don't match SQL
    # tokens inside justification comments like "-- DROP COLUMN safe because".
    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", no_block)


def parse_migration(path: Path) -> list[Operation]:
    raw = path.read_text(encoding="utf-8")
    sql = _strip_sql_comments(raw)
    name = path.parent.name
    ops: list[Operation] = []

    for match in _CREATE_TABLE_RE.finditer(sql):
        ops.append(Operation("CREATE_TABLE", match.group(1), None, name))

    for match in _DROP_TABLE_RE.finditer(sql):
        ops.append(Operation("DROP_TABLE", match.group(1), None, name))

    for alter in _ALTER_TABLE_RE.finditer(sql):
        table = alter.group(1)
        body = alter.group(2)
        for column_match in _ADD_COLUMN_RE.finditer(body):
            ops.append(Operation("ADD_COLUMN", table, column_match.group(1), name))
        for column_match in _DROP_COLUMN_RE.finditer(body):
            ops.append(Operation("DROP_COLUMN", table, column_match.group(1), name))

    return ops


def discover_migrations(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"migrations directory not found: {migrations_dir}")
    sql_files = sorted(
        p for p in migrations_dir.glob("*/migration.sql") if p.is_file()
    )
    return sql_files


def find_contradictions(operations: Iterable[Operation]) -> list[Contradiction]:
    contradictions: list[Contradiction] = []
    table_state: dict[str, tuple[str, str]] = {}  # table -> (state, migration)
    column_state: dict[tuple[str, str], tuple[str, str]] = {}

    for op in operations:
        if op.kind == "CREATE_TABLE":
            prev = table_state.get(op.table)
            if prev is not None and prev[0] == "exists":
                contradictions.append(
                    Contradiction(
                        table=op.table,
                        column=None,
                        kind="DOUBLE_CREATE_TABLE",
                        first_migration=prev[1],
                        second_migration=op.migration,
                        explanation=(
                            "table created twice without an intervening DROP TABLE"
                        ),
                    )
                )
            table_state[op.table] = ("exists", op.migration)

        elif op.kind == "DROP_TABLE":
            table_state[op.table] = ("dropped", op.migration)
            for key in list(column_state):
                if key[0] == op.table:
                    column_state.pop(key, None)

        elif op.kind == "ADD_COLUMN":
            key = (op.table, op.column or "")
            prev = column_state.get(key)
            if prev is not None and prev[0] == "exists":
                contradictions.append(
                    Contradiction(
                        table=op.table,
                        column=op.column,
                        kind="DOUBLE_ADD_COLUMN",
                        first_migration=prev[1],
                        second_migration=op.migration,
                        explanation=(
                            "column added twice without an intervening DROP COLUMN"
                        ),
                    )
                )
            column_state[key] = ("exists", op.migration)

        elif op.kind == "DROP_COLUMN":
            key = (op.table, op.column or "")
            column_state[key] = ("dropped", op.migration)

    return contradictions


@dataclass(frozen=True)
class LinearityViolation:
    """A non-linear-history finding shared by both Prisma and Alembic checks."""

    surface: str  # "prisma" | "alembic"
    kind: str
    detail: str


def check_prisma_linearity(migrations_dir: Path) -> list[LinearityViolation]:
    """Verify Prisma migration timestamps form an unbroken strict total order.

    Rules:
      * every migration directory name matches `^\\d{14}_<slug>$`.
      * timestamp prefixes are unique across directories.
      * the sorted-by-name order is also the sorted-by-timestamp order
        (i.e. filesystem lex order matches the apply order Prisma uses).
    """
    if not migrations_dir.is_dir():
        return [
            LinearityViolation(
                "prisma",
                "MISSING_DIR",
                f"Prisma migrations directory not found: {migrations_dir}",
            )
        ]

    entries = []
    for child in sorted(migrations_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _PRISMA_NON_MIGRATION_DIRS:
            continue
        entries.append(child)

    violations: list[LinearityViolation] = []
    seen_prefix: dict[str, str] = {}
    parsed: list[tuple[str, str]] = []  # (prefix, dirname)

    for entry in entries:
        m = _PRISMA_PREFIX_RE.match(entry.name)
        if not m:
            violations.append(
                LinearityViolation(
                    "prisma",
                    "BAD_PREFIX",
                    f"directory name does not match YYYYMMDDHHMMSS_<slug>: {entry.name}",
                )
            )
            continue
        prefix = m.group(1)
        if prefix in seen_prefix:
            violations.append(
                LinearityViolation(
                    "prisma",
                    "DUPLICATE_TIMESTAMP",
                    f"two migrations share timestamp {prefix}: "
                    f"{seen_prefix[prefix]} and {entry.name}",
                )
            )
        else:
            seen_prefix[prefix] = entry.name
        parsed.append((prefix, entry.name))

        if not (entry / "migration.sql").is_file():
            violations.append(
                LinearityViolation(
                    "prisma",
                    "MISSING_SQL",
                    f"migration.sql missing in {entry.name}",
                )
            )

    # Linear order: sorted by directory name must equal sorted by timestamp.
    by_name = [name for _, name in sorted(parsed, key=lambda x: x[1])]
    by_ts = [name for _, name in sorted(parsed, key=lambda x: x[0])]
    if by_name != by_ts:
        for a, b in zip(by_name, by_ts):
            if a != b:
                violations.append(
                    LinearityViolation(
                        "prisma",
                        "ORDER_DRIFT",
                        f"filename-sort order disagrees with timestamp order at {a!r} vs {b!r}",
                    )
                )
                break

    return violations


def parse_alembic_revision(path: Path) -> tuple[str | None, str | None]:
    """Extract `revision` and `down_revision` from an Alembic file.

    Uses regex rather than importing because importing every revision
    pulls in SQLAlchemy plus app models — too heavy for a pre-commit hook.
    Returns (revision, down_revision); either may be None.
    """
    text = path.read_text(encoding="utf-8")
    rev_m = re.search(r"^revision\s*[:\w\[\]\s|]*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    down_m = re.search(
        r"^down_revision\s*[:\w\[\]\s|]*=\s*(None|['\"]([^'\"]+)['\"])",
        text,
        re.MULTILINE,
    )
    revision = rev_m.group(1) if rev_m else None
    if down_m:
        if down_m.group(1) == "None":
            down_revision = None
        else:
            down_revision = down_m.group(2)
    else:
        down_revision = None
    return revision, down_revision


def check_alembic_linearity(versions_dir: Path) -> list[LinearityViolation]:
    """Walk every Alembic revision file and assert a single, unbranched chain.

    Rules:
      * every revision id is unique
      * exactly one revision has `down_revision = None` (the base)
      * every other revision's `down_revision` points to an existing id
      * no two revisions share the same `down_revision` (no branches)
      * walking from base via reverse `down_revision` links visits every
        revision exactly once (no orphans, no cycles)
    """
    if not versions_dir.is_dir():
        return [
            LinearityViolation(
                "alembic",
                "MISSING_DIR",
                f"Alembic versions directory not found: {versions_dir}",
            )
        ]

    revisions: dict[str, str | None] = {}
    file_for: dict[str, str] = {}
    violations: list[LinearityViolation] = []

    for path in sorted(versions_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        rev, down = parse_alembic_revision(path)
        if rev is None:
            violations.append(
                LinearityViolation(
                    "alembic",
                    "MISSING_REVISION_ID",
                    f"no `revision = ...` line found in {path.name}",
                )
            )
            continue
        if rev in revisions:
            violations.append(
                LinearityViolation(
                    "alembic",
                    "DUPLICATE_REVISION",
                    f"revision id {rev!r} appears in both {file_for[rev]} and {path.name}",
                )
            )
        revisions[rev] = down
        file_for[rev] = path.name

    if not revisions:
        return violations

    # Exactly one base.
    bases = [r for r, d in revisions.items() if d is None]
    if len(bases) == 0:
        violations.append(
            LinearityViolation(
                "alembic",
                "NO_BASE",
                "no revision has down_revision=None; cannot identify chain root",
            )
        )
    elif len(bases) > 1:
        violations.append(
            LinearityViolation(
                "alembic",
                "MULTIPLE_BASES",
                f"more than one revision has down_revision=None: {bases}",
            )
        )

    # No two revisions share the same down_revision (would be a fork).
    child_count: dict[str, list[str]] = {}
    for rev, down in revisions.items():
        if down is None:
            continue
        child_count.setdefault(down, []).append(rev)
    for parent, children in child_count.items():
        if len(children) > 1:
            violations.append(
                LinearityViolation(
                    "alembic",
                    "BRANCH",
                    f"revision {parent!r} has multiple children: {children}",
                )
            )

    # Every down_revision must point to an existing revision.
    for rev, down in revisions.items():
        if down is not None and down not in revisions:
            violations.append(
                LinearityViolation(
                    "alembic",
                    "ORPHAN_DOWN_REVISION",
                    f"revision {rev!r} (file {file_for[rev]}) names a "
                    f"down_revision {down!r} that does not exist",
                )
            )

    # Chain walk from base to head: must visit every revision once.
    if len(bases) == 1 and not any(v.kind == "ORPHAN_DOWN_REVISION" for v in violations):
        # Build child map (already enforced single-child above for happy path).
        children_of: dict[str | None, list[str]] = {}
        for rev, down in revisions.items():
            children_of.setdefault(down, []).append(rev)
        seen: set[str] = set()
        cur: str | None = bases[0]
        while cur is not None:
            if cur in seen:
                violations.append(
                    LinearityViolation(
                        "alembic",
                        "CYCLE",
                        f"cycle detected while walking chain at {cur!r}",
                    )
                )
                break
            seen.add(cur)
            kids = children_of.get(cur, [])
            cur = kids[0] if len(kids) == 1 else None if not kids else None
        missing = set(revisions) - seen
        if missing:
            violations.append(
                LinearityViolation(
                    "alembic",
                    "UNREACHABLE",
                    f"revisions unreachable from base via forward walk: {sorted(missing)}",
                )
            )

    return violations


def format_linearity_report(violations: list[LinearityViolation]) -> str:
    if not violations:
        return ""
    rows = [("SURFACE", "KIND", "DETAIL")]
    for v in violations:
        rows.append((v.surface, v.kind, v.detail))
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    out: list[str] = []
    for idx, row in enumerate(rows):
        out.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if idx == 0:
            out.append("  ".join("-" * widths[i] for i in range(3)))
    return "\n".join(out)


def format_report(contradictions: list[Contradiction]) -> str:
    if not contradictions:
        return ""
    header = ("KIND", "TABLE", "COLUMN", "FIRST", "SECOND", "EXPLANATION")
    rows = [header]
    for c in contradictions:
        rows.append(
            (
                c.kind,
                c.table,
                c.column or "-",
                c.first_migration,
                c.second_migration,
                c.explanation,
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = []
    for idx, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line)
        if idx == 0:
            lines.append("  ".join("-" * widths[i] for i in range(len(header))))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="Path to the Prisma migrations directory.",
    )
    parser.add_argument(
        "--alembic-dir",
        type=Path,
        default=DEFAULT_ALEMBIC_DIR,
        help="Path to the Alembic versions directory.",
    )
    parser.add_argument(
        "--skip-alembic",
        action="store_true",
        help="Skip Alembic chain checks (useful when running against a Prisma-only fixture).",
    )
    parser.add_argument(
        "--skip-prisma-linearity",
        action="store_true",
        help="Skip Prisma timestamp linearity checks (still runs contradictions).",
    )
    args = parser.parse_args(argv)

    try:
        migrations = discover_migrations(args.migrations_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not migrations:
        print(f"ERROR: no migrations found in {args.migrations_dir}", file=sys.stderr)
        return 2

    overall_exit = 0
    linearity_violations: list[LinearityViolation] = []

    if not args.skip_prisma_linearity:
        linearity_violations.extend(check_prisma_linearity(args.migrations_dir))

    if not args.skip_alembic:
        linearity_violations.extend(check_alembic_linearity(args.alembic_dir))

    if linearity_violations:
        print(format_linearity_report(linearity_violations))
        print(
            f"\n{len(linearity_violations)} linearity violation(s) detected.",
            file=sys.stderr,
        )
        overall_exit = 1

    operations: list[Operation] = []
    for path in migrations:
        operations.extend(parse_migration(path))

    contradictions = find_contradictions(operations)
    if contradictions:
        if linearity_violations:
            print()
        print(format_report(contradictions))
        print(
            f"\n{len(contradictions)} contradiction(s) across "
            f"{len(migrations)} migration(s).",
            file=sys.stderr,
        )
        overall_exit = 1

    if overall_exit == 0:
        print(f"OK: {len(migrations)} migration(s), no contradictions, chain is linear.")
    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
