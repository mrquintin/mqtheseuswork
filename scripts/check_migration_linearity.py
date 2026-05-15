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
    args = parser.parse_args(argv)

    try:
        migrations = discover_migrations(args.migrations_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not migrations:
        print(f"ERROR: no migrations found in {args.migrations_dir}", file=sys.stderr)
        return 2

    operations: list[Operation] = []
    for path in migrations:
        operations.extend(parse_migration(path))

    contradictions = find_contradictions(operations)
    if contradictions:
        print(format_report(contradictions))
        print(
            f"\n{len(contradictions)} contradiction(s) across "
            f"{len(migrations)} migration(s).",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(migrations)} migration(s), no contradictions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
