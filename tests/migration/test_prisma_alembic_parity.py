"""Schema parity between Prisma (Next.js / Codex DB) and SQLModel/Alembic
(noosphere internal DB).

The two surfaces are NOT a single database: Prisma owns the operator app's
Postgres schema, while SQLModel/Alembic owns the noosphere worker schema.
Many tables intentionally live on only one side. The handful of tables that
are mirrored across both must keep their columns in lockstep, because the
operator app and the worker exchange rows by name.

This test:

  * Parses the Prisma schema into a (table -> {column: info}) map.
  * Imports SQLModel metadata to get the SQL side's tables.
  * Pairs Prisma tables with their SQLModel mirror by exact-name match or by
    snake_casing the Prisma model name (the convention used in this repo).
  * For each pair, asserts column-name parity and nullability parity.
  * For every unpaired table, asserts it is listed in
    docs/architecture/Prisma_Alembic_Allowlist.md.

Failures print a structured diff naming the divergent table + column so
the operator can fix the drift before sync.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRISMA_SCHEMA = REPO_ROOT / "theseus-codex" / "prisma" / "schema.prisma"
ALLOWLIST_DOC = REPO_ROOT / "docs" / "architecture" / "Prisma_Alembic_Allowlist.md"

# Scalar types Prisma emits. Anything not in this set is treated as a
# relation field and ignored when computing the column list.
_PRISMA_SCALARS = {
    "String",
    "Int",
    "BigInt",
    "Float",
    "Decimal",
    "DateTime",
    "Boolean",
    "Bytes",
    "Json",
}


# Prisma scalar -> family. SQLAlchemy/SQLModel types are normalised into the
# same family so the comparison is type-system agnostic.
_PRISMA_FAMILY = {
    "String": "text",
    "Int": "int",
    "BigInt": "int",
    "Float": "float",
    "Decimal": "decimal",
    "DateTime": "datetime",
    "Boolean": "bool",
    "Bytes": "bytes",
    "Json": "json",
}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    family: str  # normalised type family
    nullable: bool


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: dict[str, ColumnInfo]


# ---------------------------------------------------------------------------
# Prisma schema parser.
# ---------------------------------------------------------------------------

_MODEL_RE = re.compile(r"^model\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", re.MULTILINE)
_ENUM_RE = re.compile(r"^enum\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", re.MULTILINE)


def _snake(name: str) -> str:
    """PascalCase -> snake_case. Matches Prisma's default @@map convention."""
    out: list[str] = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0 and (name[i - 1].islower() or
                                       (i + 1 < len(name) and name[i + 1].islower())):
            out.append("_")
        out.append(c.lower())
    return "".join(out)


def _read_model_blocks(text: str) -> dict[str, str]:
    """Returns model name -> body (between the braces) for every `model X { ... }`."""
    blocks: dict[str, str] = {}
    for m in _MODEL_RE.finditer(text):
        name = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        blocks[name] = body
    return blocks


def parse_prisma_schema(path: Path) -> dict[str, TableInfo]:
    text = path.read_text(encoding="utf-8")
    blocks = _read_model_blocks(text)
    enums = {m.group(1) for m in _ENUM_RE.finditer(text)}
    tables: dict[str, TableInfo] = {}
    for model_name, body in blocks.items():
        # Resolve @@map(...) → physical table name (otherwise use model name).
        map_match = re.search(r'@@map\(\s*"([^"]+)"\s*\)', body)
        table_name = map_match.group(1) if map_match else model_name

        columns: dict[str, ColumnInfo] = {}
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("@@"):
                continue
            # Field syntax: `name  Type[?|[]]  @...`
            tokens = line.split()
            if len(tokens) < 2:
                continue
            col_name = tokens[0]
            type_token = tokens[1]
            base_type = type_token.rstrip("?[]")
            # Skip relation fields (Type is another *model*). Enums are
            # scalar-shaped — store them as a text family.
            if base_type in _PRISMA_SCALARS:
                family = _PRISMA_FAMILY[base_type]
            elif base_type in enums:
                family = "text"
            else:
                continue
            # Field-level @map renames the physical column.
            map_field = re.search(r'@map\(\s*"([^"]+)"\s*\)', raw_line)
            physical_name = map_field.group(1) if map_field else col_name
            nullable = type_token.endswith("?")
            columns[physical_name] = ColumnInfo(
                name=physical_name,
                family=family,
                nullable=nullable,
            )
        tables[table_name] = TableInfo(name=table_name, columns=columns)
    return tables


def _normalise_column_name(name: str) -> str:
    """Normalise camelCase or snake_case column names to a common key.

    Prisma's convention in this repo is camelCase columns. SQLModel uses
    snake_case. Both refer to the same logical column; the parity test
    compares them on this normalised key.
    """
    return _snake(name).replace("__", "_")


# ---------------------------------------------------------------------------
# SQLModel side.
# ---------------------------------------------------------------------------


def _sqlmodel_family(coltype: object) -> str:
    name = type(coltype).__name__.lower()
    if "biginteger" in name:
        return "int"
    if "integer" in name or name == "int":
        return "int"
    if "smallint" in name:
        return "int"
    if "boolean" in name or name == "bool":
        return "bool"
    if "datetime" in name or "timestamp" in name:
        return "datetime"
    if "date" in name:
        return "datetime"
    if "float" in name or "real" in name or "double" in name:
        return "float"
    if "numeric" in name or "decimal" in name:
        return "decimal"
    if "json" in name:
        return "json"
    if "largebinary" in name or "bytea" in name or "blob" in name:
        return "bytes"
    if "uuid" in name:
        return "text"
    if "enum" in name:
        return "text"
    # Everything else (String, Text, VARCHAR, CHAR, ...) falls back to text.
    return "text"


def load_sqlmodel_tables() -> dict[str, TableInfo]:
    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    try:
        # Importing the store registers every SQLModel table on the shared
        # SQLModel.metadata. Some modules also register their own tables on
        # import; we follow the same pattern as the Alembic env.py.
        import noosphere.store  # noqa: F401
        from sqlmodel import SQLModel
    except Exception as exc:  # pragma: no cover - surfaces fast if env is broken
        pytest.skip(f"noosphere SQLModel store could not be imported: {exc!r}")
        raise

    tables: dict[str, TableInfo] = {}
    for table_name, table in SQLModel.metadata.tables.items():
        columns: dict[str, ColumnInfo] = {}
        for col in table.columns:
            columns[col.name] = ColumnInfo(
                name=col.name,
                family=_sqlmodel_family(col.type),
                nullable=bool(col.nullable),
            )
        tables[table_name] = TableInfo(name=table_name, columns=columns)
    return tables


# ---------------------------------------------------------------------------
# Allowlist parser.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Allowlist:
    prisma_only: set[str]
    sqlmodel_only: set[str]
    loose_mirrors: set[tuple[str, str]]  # (prisma_table, sqlmodel_table)


def parse_allowlist(path: Path) -> Allowlist:
    """Parse `docs/architecture/Prisma_Alembic_Allowlist.md`.

    The doc has three Markdown tables under three `## ...` headings:

      * `## Loose mirror pairs`  — two-column key, value is the reason.
      * `## Prisma-only`         — one-column key, value is the reason.
      * `## SQLModel-only`       — one-column key, value is the reason.

    Empty reasons are a parse error so the doc cannot rot into a dumping
    ground for unjustified divergences.
    """
    if not path.is_file():
        raise FileNotFoundError(f"allowlist doc not found: {path}")

    text = path.read_text(encoding="utf-8")
    prisma_only: set[str] = set()
    sqlmodel_only: set[str] = set()
    loose_mirrors: set[tuple[str, str]] = set()

    section: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## Loose mirror pairs"):
            section = "loose"
            continue
        if line.startswith("## Prisma-only"):
            section = "prisma_only"
            continue
        if line.startswith("## SQLModel-only"):
            section = "sqlmodel_only"
            continue
        if line.startswith("## ") and section is not None:
            section = None
            continue
        if section is None or not line.startswith("|"):
            continue
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        if not parts:
            continue
        # Skip Markdown header separator rows like `| --- | --- |`.
        if all(set(p) <= set("-: ") for p in parts):
            continue
        # Skip Markdown header label rows.
        first_cell = parts[0].strip("`")
        if not first_cell or first_cell.lower() in {"table", "prisma"}:
            continue

        if section == "loose":
            if len(parts) < 3:
                continue
            prisma_tbl = parts[0].strip("`")
            sql_tbl = parts[1].strip("`")
            reason = parts[2]
            if not reason or set(reason) <= set("-: "):
                raise ValueError(
                    f"loose-mirror entry {prisma_tbl!r}↔{sql_tbl!r} has no reason"
                )
            loose_mirrors.add((prisma_tbl, sql_tbl))
        else:
            if len(parts) < 2:
                continue
            table = first_cell
            reason = parts[1]
            if not reason or set(reason) <= set("-: "):
                raise ValueError(
                    f"allowlist entry for {table!r} has no reason; every row must justify itself"
                )
            if section == "prisma_only":
                prisma_only.add(table)
            elif section == "sqlmodel_only":
                sqlmodel_only.add(table)

    return Allowlist(
        prisma_only=prisma_only,
        sqlmodel_only=sqlmodel_only,
        loose_mirrors=loose_mirrors,
    )


# ---------------------------------------------------------------------------
# Pairing logic.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TablePair:
    prisma_name: str
    sqlmodel_name: str
    match_kind: str  # "exact" | "snake"


def pair_tables(
    prisma: dict[str, TableInfo],
    sqlmodel: dict[str, TableInfo],
) -> tuple[list[TablePair], set[str], set[str]]:
    pairs: list[TablePair] = []
    prisma_unpaired: set[str] = set()
    sqlmodel_paired: set[str] = set()

    for p_name in sorted(prisma):
        if p_name in sqlmodel:
            pairs.append(TablePair(p_name, p_name, "exact"))
            sqlmodel_paired.add(p_name)
            continue
        snake = _snake(p_name)
        if snake in sqlmodel:
            pairs.append(TablePair(p_name, snake, "snake"))
            sqlmodel_paired.add(snake)
            continue
        prisma_unpaired.add(p_name)

    sqlmodel_unpaired = set(sqlmodel) - sqlmodel_paired
    return pairs, prisma_unpaired, sqlmodel_unpaired


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def prisma_tables() -> dict[str, TableInfo]:
    return parse_prisma_schema(PRISMA_SCHEMA)


@pytest.fixture(scope="module")
def sqlmodel_tables() -> dict[str, TableInfo]:
    return load_sqlmodel_tables()


@pytest.fixture(scope="module")
def allowlist() -> Allowlist:
    return parse_allowlist(ALLOWLIST_DOC)


def test_allowlist_doc_parses(allowlist: Allowlist) -> None:
    assert isinstance(allowlist.prisma_only, set)
    assert isinstance(allowlist.sqlmodel_only, set)
    assert isinstance(allowlist.loose_mirrors, set)


def test_paired_tables_have_matching_columns(
    prisma_tables: dict[str, TableInfo],
    sqlmodel_tables: dict[str, TableInfo],
    allowlist: Allowlist,
) -> None:
    pairs, _, _ = pair_tables(prisma_tables, sqlmodel_tables)

    diffs: list[str] = []
    for pair in pairs:
        if (pair.prisma_name, pair.sqlmodel_name) in allowlist.loose_mirrors:
            continue
        p_cols_raw = prisma_tables[pair.prisma_name].columns
        s_cols_raw = sqlmodel_tables[pair.sqlmodel_name].columns
        # Compare on the normalised (snake_case) key. The two surfaces follow
        # different naming conventions (Prisma camelCase, SQLModel snake_case)
        # but refer to the same logical column.
        p_cols = {_normalise_column_name(k): v for k, v in p_cols_raw.items()}
        s_cols = {_normalise_column_name(k): v for k, v in s_cols_raw.items()}
        p_keys = set(p_cols)
        s_keys = set(s_cols)

        missing_in_sql = p_keys - s_keys
        missing_in_prisma = s_keys - p_keys
        for col in sorted(missing_in_sql):
            diffs.append(
                f"  {pair.prisma_name} ↔ {pair.sqlmodel_name}: "
                f"column {col!r} present in Prisma but missing in SQLModel"
            )
        for col in sorted(missing_in_prisma):
            diffs.append(
                f"  {pair.prisma_name} ↔ {pair.sqlmodel_name}: "
                f"column {col!r} present in SQLModel but missing in Prisma"
            )
        for col in sorted(p_keys & s_keys):
            p_info = p_cols[col]
            s_info = s_cols[col]
            if p_info.family != s_info.family:
                diffs.append(
                    f"  {pair.prisma_name}.{col}: type family drift "
                    f"(Prisma={p_info.family}, SQLModel={s_info.family})"
                )
            if p_info.nullable != s_info.nullable:
                diffs.append(
                    f"  {pair.prisma_name}.{col}: nullability drift "
                    f"(Prisma null={p_info.nullable}, SQLModel null={s_info.nullable})"
                )

    if diffs:
        msg = "Prisma↔SQLModel parity drift detected:\n" + "\n".join(diffs)
        pytest.fail(msg)


def test_unpaired_tables_are_documented(
    prisma_tables: dict[str, TableInfo],
    sqlmodel_tables: dict[str, TableInfo],
    allowlist: Allowlist,
) -> None:
    pairs, prisma_unpaired, sqlmodel_unpaired = pair_tables(prisma_tables, sqlmodel_tables)
    paired_prisma = {p.prisma_name for p in pairs}
    paired_sql = {p.sqlmodel_name for p in pairs}

    missing_from_prisma_only = prisma_unpaired - allowlist.prisma_only
    missing_from_sqlmodel_only = sqlmodel_unpaired - allowlist.sqlmodel_only

    msg_parts: list[str] = []
    if missing_from_prisma_only:
        msg_parts.append(
            "Prisma-only tables missing from allowlist "
            f"({ALLOWLIST_DOC.name}):\n  "
            + "\n  ".join(sorted(missing_from_prisma_only))
            + "\nAdd a row with a one-sentence reason, or give it a SQLModel mirror."
        )
    if missing_from_sqlmodel_only:
        msg_parts.append(
            "SQLModel-only tables missing from allowlist "
            f"({ALLOWLIST_DOC.name}):\n  "
            + "\n  ".join(sorted(missing_from_sqlmodel_only))
            + "\nAdd a row with a one-sentence reason, or give it a Prisma mirror."
        )

    # Reverse: nothing in the allowlist should also appear paired.
    stale_prisma = allowlist.prisma_only & paired_prisma
    stale_sql = allowlist.sqlmodel_only & paired_sql
    if stale_prisma:
        msg_parts.append(
            "Prisma-only allowlist entries that DO have a SQLModel mirror "
            f"(should be removed):\n  " + "\n  ".join(sorted(stale_prisma))
        )
    if stale_sql:
        msg_parts.append(
            "SQLModel-only allowlist entries that DO have a Prisma mirror "
            f"(should be removed):\n  " + "\n  ".join(sorted(stale_sql))
        )

    # Stale loose-mirror entries (named pair that no longer exists in either schema).
    auto_pairs = {(p.prisma_name, p.sqlmodel_name) for p in pairs}
    stale_loose = allowlist.loose_mirrors - auto_pairs
    if stale_loose:
        msg_parts.append(
            "Loose-mirror entries that no longer auto-pair (table renamed or removed):\n  "
            + "\n  ".join(f"{a} ↔ {b}" for a, b in sorted(stale_loose))
        )

    if msg_parts:
        pytest.fail("\n\n".join(msg_parts))


def test_snake_case_helper() -> None:
    assert _snake("Foo") == "foo"
    assert _snake("FooBar") == "foo_bar"
    # Acronym handling: the parser inserts an underscore only between a lower-
    # case letter and an upper-case letter, so HTTPRequest -> http_request.
    assert _snake("HTTPRequest") == "http_request"
    assert _snake("AlgorithmCalibrationSnapshot") == "algorithm_calibration_snapshot"


def test_prisma_parser_handles_relations() -> None:
    """Relation fields (capitalised non-scalar types) must not be treated as columns."""
    tables = parse_prisma_schema(PRISMA_SCHEMA)
    # Organization has explicit FK-less relations like `founders Founder[]` and
    # a scalar `slug String`. The scalar must survive, the relation must not.
    org = tables["Organization"]
    assert "slug" in org.columns
    assert "founders" not in org.columns
