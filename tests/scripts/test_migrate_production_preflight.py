from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "migrate_production.sh"


def _run_script(
    *,
    database_url: str | None,
    input_text: str = "",
    path: str | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": path or os.environ.get("PATH", ""),
    }
    if database_url is not None:
        env["DATABASE_URL"] = database_url

    return subprocess.run(
        [str(SCRIPT), *(args or [])],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _fake_command_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("psql", "npx", "alembic"):
        command = bin_dir / name
        command.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        command.chmod(command.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _fake_clean_plan_command_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "plan-bin"
    bin_dir.mkdir()

    psql = bin_dir / "psql"
    psql.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    psql.chmod(psql.stat().st_mode | stat.S_IXUSR)

    npx = bin_dir / "npx"
    npx.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'if [[ "$*" == "prisma migrate status" ]]; then',
                '  echo "Database schema is up to date!"',
                "  exit 0",
                "fi",
                'echo "unexpected npx invocation: $*" >&2',
                "exit 99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)

    alembic = bin_dir / "alembic"
    alembic.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'if [[ "$*" == "current" ]]; then',
                '  echo "006_currents_metrics (head)"',
                "  exit 0",
                "fi",
                'if [[ "$*" == "history --indicate-current" ]]; then',
                '  echo "005_opinion_citation_revoked_at -> 006_currents_metrics (head) (current), Current event significance metrics"',
                '  echo "004_forecasts_data_model -> 005_opinion_citation_revoked_at, Opinion citation revocation timestamp"',
                "  exit 0",
                "fi",
                'echo "unexpected alembic invocation: $*" >&2',
                "exit 99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    alembic.chmod(alembic.stat().st_mode | stat.S_IXUSR)

    return bin_dir


def _fake_pending_prisma_command_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "pending-plan-bin"
    bin_dir.mkdir()

    psql = bin_dir / "psql"
    psql.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    psql.chmod(psql.stat().st_mode | stat.S_IXUSR)

    npx = bin_dir / "npx"
    npx.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'if [[ "$*" == "prisma migrate status" ]]; then',
                '  echo "Loaded Prisma config from prisma.config.ts."',
                '  echo "Prisma schema loaded from prisma/schema.prisma."',
                '  echo "Following migration have not yet been applied:"',
                '  echo "round18_consolidation"',
                '  echo ""',
                '  echo "To apply migrations in production run prisma migrate deploy."',
                "  exit 1",
                "fi",
                'echo "unexpected npx invocation: $*" >&2',
                "exit 99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)

    alembic = bin_dir / "alembic"
    alembic.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'if [[ "$*" == "current" ]]; then',
                '  echo "006_currents_metrics (head)"',
                "  exit 0",
                "fi",
                'if [[ "$*" == "history --indicate-current" ]]; then',
                '  echo "005_opinion_citation_revoked_at -> 006_currents_metrics (head) (current), Current event significance metrics"',
                "  exit 0",
                "fi",
                'echo "unexpected alembic invocation: $*" >&2',
                "exit 99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    alembic.chmod(alembic.stat().st_mode | stat.S_IXUSR)

    return bin_dir


def test_missing_database_url_aborts_with_specific_message() -> None:
    result = _run_script(database_url=None)

    assert result.returncode != 0
    assert "DATABASE_URL is not set" in result.stderr


def test_malformed_database_url_aborts_with_specific_message() -> None:
    result = _run_script(database_url="postgresql://user:pass@db.example.com")

    assert result.returncode != 0
    assert "DATABASE_URL is malformed: missing database name" in result.stderr


def test_localhost_without_allow_flag_aborts_before_command_checks() -> None:
    result = _run_script(
        database_url="postgresql://user:super-secret@localhost:5432/theseus"
    )

    assert result.returncode != 0
    assert "refusing local DATABASE_URL host 'localhost' without --allow-localhost" in (
        result.stderr
    )
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr


def test_hostname_typo_aborts_without_printing_credentials(tmp_path: Path) -> None:
    fake_bin = _fake_command_dir(tmp_path)
    result = _run_script(
        database_url=(
            "postgresql://operator:super-secret@db.example.com:5432/theseus"
            "?sslmode=require"
        ),
        input_text="db.exampel.com\n",
        path=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )

    assert result.returncode != 0
    assert "hostname confirmation mismatch" in result.stderr
    assert "db.example.com:5432 + theseus" in result.stdout
    assert "operator" not in result.stdout
    assert "operator" not in result.stderr
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr


def test_dry_run_trusts_prisma_pending_block_with_non_timestamp_name(
    tmp_path: Path,
) -> None:
    fake_bin = _fake_pending_prisma_command_dir(tmp_path)
    result = _run_script(
        database_url=(
            "postgresql://operator:super-secret@db.example.com:5432/theseus"
            "?sslmode=require"
        ),
        input_text="db.example.com\n",
        path=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        args=["--dry-run"],
    )

    assert result.returncode != 0
    assert "Prisma pending migrations: 1" in result.stdout
    assert "Total pending migrations: 1" in result.stdout
    assert "prisma migrate status failed before a migration plan could be trusted" not in (
        result.stderr
    )
    assert "operator" not in result.stdout
    assert "operator" not in result.stderr
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr


def test_dry_run_clean_plan_exits_zero_without_printing_credentials(
    tmp_path: Path,
) -> None:
    fake_bin = _fake_clean_plan_command_dir(tmp_path)
    result = _run_script(
        database_url=(
            "postgresql://operator:super-secret@db.example.com:5432/theseus"
            "?sslmode=require"
        ),
        input_text="db.example.com\n",
        path=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        args=["--dry-run"],
    )

    assert result.returncode == 0
    assert "Prisma pending migrations: 0" in result.stdout
    assert "Alembic pending migrations: 0" in result.stdout
    assert "Dry run only; Prisma deploy and Alembic upgrade were not executed." in (
        result.stdout
    )
    assert "operator" not in result.stdout
    assert "operator" not in result.stderr
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr
