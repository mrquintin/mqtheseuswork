"""Tests for publication-chain CLI commands (prompt 22).

Uses Click's CliRunner to verify each command group and subcommand.
Store-dependent commands are tested via --help or with mocked backends.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from noosphere.cli import cli as root_cli


@pytest.fixture
def runner():
    return CliRunner()


# ── Plugin discovery ────────────────────────────────────────────────────────

PUBLICATION_GROUPS = ["transfer", "docs", "interop", "gate"]


def test_publication_groups_registered(runner: CliRunner):
    result = runner.invoke(root_cli, ["--help"])
    assert result.exit_code == 0
    for group in PUBLICATION_GROUPS:
        assert group in result.output, f"'{group}' not in root --help output"


# ── --help smoke tests ──────────────────────────────────────────────────────

SUBCOMMANDS = {
    "transfer": ["package", "verify-doc"],
    "docs": ["build"],
    "interop": ["build-mip", "run-mip", "scaffold-adoption", "submit-transfer"],
    "gate": ["submit", "status", "override", "refusal-report"],
}


@pytest.mark.parametrize("group,sub", [
    (g, s) for g, subs in SUBCOMMANDS.items() for s in subs
])
def test_subcommand_help(runner: CliRunner, group: str, sub: str):
    result = runner.invoke(root_cli, [group, sub, "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "--help" in result.output


# ── transfer package (mocked) ──────────────────────────────────────────────

def test_transfer_package_json(runner: CliRunner, tmp_path: Path):
    mock_store = MagicMock()
    mock_orch = MagicMock()
    mock_orch.store = mock_store

    out = tmp_path / "pkg"

    with patch("noosphere.cli_commands.transfer._get_store", return_value=mock_store), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.transfer.package", return_value=out / "result"):
        result = runner.invoke(root_cli, [
            "transfer", "package", "test_method@1.0",
            "--out", str(out), "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "package_path" in data
    assert data["method"] == "test_method@1.0"


# ── transfer verify-doc (mocked) ───────────────────────────────────────────

def test_transfer_verify_doc_valid(runner: CliRunner, tmp_path: Path):
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()

    with patch("noosphere.cli_commands.transfer._get_store", return_value=MagicMock()), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.transfer.verify_signed_checksums", return_value=True):
        result = runner.invoke(root_cli, [
            "transfer", "verify-doc", str(doc_dir), "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["valid"] is True


def test_transfer_verify_doc_invalid(runner: CliRunner, tmp_path: Path):
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()

    with patch("noosphere.cli_commands.transfer._get_store", return_value=MagicMock()), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.transfer.verify_signed_checksums", return_value=False):
        result = runner.invoke(root_cli, [
            "transfer", "verify-doc", str(doc_dir),
        ])

    assert result.exit_code != 0


# ── docs build (mocked) ────────────────────────────────────────────────────

def test_docs_build_json(runner: CliRunner, tmp_path: Path):
    mock_doc = MagicMock()
    mock_doc.model_dump.return_value = {
        "method_ref": {"name": "m", "version": "1"},
        "spec_md_path": "spec.md",
        "template_version": "1.0",
    }

    with patch("noosphere.cli_commands.docs_cmd._get_store", return_value=MagicMock()), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.docgen.compile_method_doc", return_value=mock_doc):
        result = runner.invoke(root_cli, [
            "docs", "build", "m@1", "--out", str(tmp_path), "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "spec_md_path" in data


# ── interop build-mip (mocked) ─────────────────────────────────────────────

def test_interop_build_mip_json(runner: CliRunner, tmp_path: Path):
    out = tmp_path / "mip"

    with patch("noosphere.cli_commands.interop._get_store", return_value=MagicMock()), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.interop.build_mip", return_value=out / "result"):
        result = runner.invoke(root_cli, [
            "interop", "build-mip",
            "--name", "test-mip", "--version", "0.1",
            "--methods", "a@1,b@2", "--out", str(out), "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "test-mip"


# ── interop scaffold-adoption (mocked) ─────────────────────────────────────

def test_interop_scaffold_adoption(runner: CliRunner, tmp_path: Path):
    mip_dir = tmp_path / "mip"
    mip_dir.mkdir()
    out_dir = tmp_path / "adopt"

    with patch("noosphere.cli_commands.interop._get_store", return_value=MagicMock()), \
         patch("noosphere.interop.scaffold_adoption", return_value=out_dir):
        result = runner.invoke(root_cli, [
            "interop", "scaffold-adoption",
            "--mip", str(mip_dir), "--out", str(out_dir), "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "adoption_path" in data


# ── gate submit (mocked) ───────────────────────────────────────────────────

def _make_mock_verdict(**overrides):
    from noosphere.models import CheckResult, RigorVerdict
    defaults = {
        "verdict": "pass",
        "checks_run": [
            CheckResult(check_name="coherence", pass_=True,
                        detail="ok", ledger_entry_id="le1"),
        ],
        "conditions": [],
        "reviewed_by": [],
        "ledger_entry_id": "led-1",
    }
    defaults.update(overrides)
    return RigorVerdict(**defaults)


def test_gate_submit_json(runner: CliRunner):
    verdict = _make_mock_verdict()
    mock_gate = MagicMock()
    mock_gate.submit.return_value = verdict

    with patch("noosphere.cli_commands.gate._get_store", return_value=MagicMock()), \
         patch("noosphere.rigor_gate.Gate", return_value=mock_gate):
        result = runner.invoke(root_cli, [
            "gate", "submit", "payload-ref-1",
            "--kind", "conclusion", "--venue", "public_site", "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["verdict"] == "pass"


def test_gate_submit_rich_output(runner: CliRunner):
    verdict = _make_mock_verdict()
    mock_gate = MagicMock()
    mock_gate.submit.return_value = verdict

    with patch("noosphere.cli_commands.gate._get_store", return_value=MagicMock()), \
         patch("noosphere.rigor_gate.Gate", return_value=mock_gate):
        result = runner.invoke(root_cli, [
            "gate", "submit", "payload-ref-1",
            "--kind", "conclusion", "--venue", "public_site",
        ])

    assert result.exit_code == 0
    assert "Verdict" in result.output


# ── gate override (mocked) ─────────────────────────────────────────────────

def test_gate_override_json(runner: CliRunner):
    from noosphere.models import FounderOverride
    mock_override = FounderOverride(
        override_id="ov-1", submission_id="sub-1", founder_id="cli-user",
        overridden_checks=["coherence"], justification="test reason",
        ledger_entry_id="le-2",
    )

    with patch("noosphere.cli_commands.gate._get_store", return_value=MagicMock()), \
         patch("noosphere.ledger.KeyRing"), \
         patch("noosphere.ledger.Ledger"), \
         patch("noosphere.rigor_gate.create_override", return_value=mock_override):
        result = runner.invoke(root_cli, [
            "gate", "override", "sub-1",
            "--check", "coherence", "--reason", "test reason", "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["submission_id"] == "sub-1"


# ── gate refusal-report (mocked) ──────────────────────────────────────────

def test_gate_refusal_report_json(runner: CliRunner):
    from noosphere.rigor_gate import DashboardData
    mock_data = DashboardData(
        year_month="2026-04",
        total=10, passed=7, failed=2, pass_with_conditions=1,
        top_failure_categories={"coherence": 2},
    )

    with patch("noosphere.cli_commands.gate._get_store", return_value=MagicMock()), \
         patch("noosphere.rigor_gate.monthly_stats", return_value=mock_data):
        result = runner.invoke(root_cli, [
            "gate", "refusal-report", "--month", "2026-04", "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total"] == 10
    assert data["year_month"] == "2026-04"


# ── gate status (mocked) ──────────────────────────────────────────────────

def test_gate_status_no_overrides(runner: CliRunner):
    with patch("noosphere.cli_commands.gate._get_store", return_value=MagicMock()), \
         patch("noosphere.rigor_gate.overrides_for_display", return_value=[]):
        result = runner.invoke(root_cli, [
            "gate", "status", "nonexistent-id", "--json",
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["overrides"] == []
