"""Tests for the migration tooling.

Two levels of coverage:

  * Pure-Python tests over scripts/check_migration_linearity.py against
    synthetic migration directories. These always run.

  * Optional Postgres-container tests that exercise the dry-run + apply
    path. They run only when MIGRATION_TEST_DATABASE_URL points at a
    reachable, throw-away Postgres database. CI is expected to provision
    one; local devs can skip.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_migration_linearity.py"
DRY_RUN_PATH = REPO_ROOT / "scripts" / "migrate_production_dry_run.sh"
APPLY_PATH = REPO_ROOT / "scripts" / "migrate_production.sh"
PRISMA_MIGRATIONS_DIR = REPO_ROOT / "theseus-codex" / "prisma" / "migrations"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_migration_linearity", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load_module()


def _write_migration(root: Path, name: str, sql: str) -> Path:
    migration_dir = root / name
    migration_dir.mkdir(parents=True, exist_ok=True)
    sql_path = migration_dir / "migration.sql"
    sql_path.write_text(textwrap.dedent(sql).lstrip(), encoding="utf-8")
    return sql_path


class TestParseMigration:
    def test_create_table(self, tmp_path: Path) -> None:
        sql_path = _write_migration(
            tmp_path,
            "20260101000000_init",
            """
            CREATE TABLE "Foo" (
              "id" TEXT NOT NULL,
              CONSTRAINT "Foo_pkey" PRIMARY KEY ("id")
            );
            """,
        )
        ops = MOD.parse_migration(sql_path)
        kinds = [(op.kind, op.table, op.column) for op in ops]
        assert ("CREATE_TABLE", "Foo", None) in kinds

    def test_add_and_drop_column(self, tmp_path: Path) -> None:
        sql_path = _write_migration(
            tmp_path,
            "20260101010000_alter",
            """
            ALTER TABLE "Foo" ADD COLUMN "bar" TEXT;
            ALTER TABLE "Foo" DROP COLUMN "baz";
            """,
        )
        ops = MOD.parse_migration(sql_path)
        kinds = [(op.kind, op.table, op.column) for op in ops]
        assert ("ADD_COLUMN", "Foo", "bar") in kinds
        assert ("DROP_COLUMN", "Foo", "baz") in kinds

    def test_comments_are_ignored(self, tmp_path: Path) -> None:
        sql_path = _write_migration(
            tmp_path,
            "20260101020000_comment",
            """
            -- ALTER TABLE "Foo" DROP COLUMN "ghost";
            /* CREATE TABLE "AlsoGhost" (id TEXT); */
            CREATE TABLE "Real" (id TEXT);
            """,
        )
        ops = MOD.parse_migration(sql_path)
        tables = sorted({op.table for op in ops if op.kind == "CREATE_TABLE"})
        assert tables == ["Real"]


class TestFindContradictions:
    def test_clean_history(self) -> None:
        ops = [
            MOD.Operation("CREATE_TABLE", "Foo", None, "m1"),
            MOD.Operation("ADD_COLUMN", "Foo", "bar", "m2"),
            MOD.Operation("DROP_COLUMN", "Foo", "bar", "m3"),
            MOD.Operation("ADD_COLUMN", "Foo", "bar", "m4"),
        ]
        assert MOD.find_contradictions(ops) == []

    def test_double_create_table(self) -> None:
        ops = [
            MOD.Operation("CREATE_TABLE", "Foo", None, "m1"),
            MOD.Operation("CREATE_TABLE", "Foo", None, "m2"),
        ]
        contradictions = MOD.find_contradictions(ops)
        assert len(contradictions) == 1
        assert contradictions[0].kind == "DOUBLE_CREATE_TABLE"
        assert contradictions[0].first_migration == "m1"
        assert contradictions[0].second_migration == "m2"

    def test_double_add_column(self) -> None:
        ops = [
            MOD.Operation("ADD_COLUMN", "Foo", "bar", "m1"),
            MOD.Operation("ADD_COLUMN", "Foo", "bar", "m2"),
        ]
        contradictions = MOD.find_contradictions(ops)
        assert len(contradictions) == 1
        assert contradictions[0].kind == "DOUBLE_ADD_COLUMN"
        assert contradictions[0].column == "bar"

    def test_drop_then_create_table_is_fine(self) -> None:
        ops = [
            MOD.Operation("CREATE_TABLE", "Foo", None, "m1"),
            MOD.Operation("DROP_TABLE", "Foo", None, "m2"),
            MOD.Operation("CREATE_TABLE", "Foo", None, "m3"),
        ]
        assert MOD.find_contradictions(ops) == []


class TestDiscoverAndCli:
    def test_discover_finds_real_prisma_migrations(self) -> None:
        migrations = MOD.discover_migrations(PRISMA_MIGRATIONS_DIR)
        assert len(migrations) > 0
        for path in migrations:
            assert path.name == "migration.sql"

    def test_cli_passes_on_real_history(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_cli_reports_contradictions_tabularly(self, tmp_path: Path) -> None:
        _write_migration(
            tmp_path,
            "20260101000000_a",
            'CREATE TABLE "Foo" (id TEXT);',
        )
        _write_migration(
            tmp_path,
            "20260101010000_b",
            'CREATE TABLE "Foo" (id TEXT);',
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--migrations-dir", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "DOUBLE_CREATE_TABLE" in result.stdout
        assert "Foo" in result.stdout
        assert "20260101000000_a" in result.stdout
        assert "20260101010000_b" in result.stdout

    def test_cli_missing_dir(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--migrations-dir",
                str(tmp_path / "does-not-exist"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Optional integration tests against a synthetic Postgres container.
# ---------------------------------------------------------------------------

INTEGRATION_DB_URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")

integration = pytest.mark.skipif(
    not INTEGRATION_DB_URL,
    reason="MIGRATION_TEST_DATABASE_URL not set; integration tests skipped",
)


def _have_command(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def _reset_database(url: str) -> None:
    subprocess.run(
        [
            "psql",
            url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        ],
        check=True,
        capture_output=True,
    )


@integration
def test_dry_run_reports_pending_operations() -> None:
    assert _have_command("psql"), "psql is required for integration tests"
    assert _have_command("npx"), "npx is required for integration tests"
    _reset_database(INTEGRATION_DB_URL)

    env = os.environ.copy()
    env["DATABASE_URL"] = INTEGRATION_DB_URL
    # Confirm the host non-interactively.
    host = INTEGRATION_DB_URL.split("@", 1)[-1].split(":", 1)[0].split("/", 1)[0]

    result = subprocess.run(
        ["bash", str(DRY_RUN_PATH), "--allow-localhost"],
        input=f"{host}\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert "Total pending migrations:" in combined
    # On a freshly reset DB we expect strictly more than 0 pending migrations.
    assert "Dry-run OK" in result.stdout, combined


@integration
def test_apply_is_idempotent() -> None:
    assert _have_command("psql"), "psql is required for integration tests"
    assert _have_command("npx"), "npx is required for integration tests"
    assert _have_command("alembic"), "alembic is required for integration tests"
    _reset_database(INTEGRATION_DB_URL)

    env = os.environ.copy()
    env["DATABASE_URL"] = INTEGRATION_DB_URL
    host = INTEGRATION_DB_URL.split("@", 1)[-1].split(":", 1)[0].split("/", 1)[0]

    # First apply.
    first = subprocess.run(
        ["bash", str(APPLY_PATH), "--allow-localhost", "--skip-snapshot"],
        input=f"{host}\nyes\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    # Second apply against the now-current schema should detect zero pending
    # migrations during the post-check and exit cleanly.
    second = subprocess.run(
        ["bash", str(APPLY_PATH), "--allow-localhost", "--skip-snapshot", "--dry-run"],
        input=f"{host}\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = second.stdout + second.stderr
    assert "Total pending migrations: 0" in combined, combined
