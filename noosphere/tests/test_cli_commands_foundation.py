"""Tests for CLI command modules (prompt 21).

Uses Click's CliRunner to invoke each command group and subcommand,
asserting non-error exit and valid output shape. Store-dependent commands
are tested via --help (which never touches the store).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from noosphere.cli import cli as root_cli


@pytest.fixture
def runner():
    return CliRunner()


# ── Plugin discovery ────────────────────────────────────────────────────────

EXPECTED_GROUPS = [
    "methods", "ledger", "cascade", "eval", "inverse",
    "battery", "review", "decay",
]


def test_all_groups_registered(runner: CliRunner):
    result = runner.invoke(root_cli, ["--help"])
    assert result.exit_code == 0
    for group in EXPECTED_GROUPS:
        assert group in result.output, f"'{group}' not in root --help output"


def test_existing_commands_still_present(runner: CliRunner):
    result = runner.invoke(root_cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "ask", "graph", "coherence", "stats", "search",
                "classify", "calibration", "conclusions", "founders"):
        assert cmd in result.output, f"Existing cmd '{cmd}' missing from --help"


# ── --help smoke tests for every subcommand ─────────────────────────────────

SUBCOMMANDS = {
    "methods": ["list", "show", "run", "diff", "extract-candidates"],
    "ledger": ["verify", "export"],
    "cascade": ["explain", "cut", "export", "diagnostics"],
    "eval": ["counterfactual"],
    "inverse": ["run", "show"],
    "battery": ["fetch", "run", "show", "report"],
    "review": ["run", "rebuttals-pending", "reviewer-calibration"],
    "decay": ["status", "revalidate", "schedule", "retire"],
}


@pytest.mark.parametrize("group,sub", [
    (g, s) for g, subs in SUBCOMMANDS.items() for s in subs
])
def test_subcommand_help(runner: CliRunner, group: str, sub: str):
    result = runner.invoke(root_cli, [group, sub, "--help"])
    assert result.exit_code == 0
    assert "--help" in result.output or "Usage" in result.output


def test_eval_counterfactual_subcommands(runner: CliRunner):
    result = runner.invoke(root_cli, ["eval", "counterfactual", "--help"])
    assert result.exit_code == 0
    for sub in ("run", "show", "report"):
        assert sub in result.output


# ── methods list (mocked) ──────────────────────────────────────────────────

def _make_mock_method(**overrides):
    from noosphere.models import MethodType
    defaults = dict(
        method_id="m-001", name="test_method", version="1.0.0",
        method_type=MethodType.EXTRACTION, input_schema={}, output_schema={},
        description="A test method", rationale="testing", preconditions=[],
        postconditions=[], dependencies=[], implementation=MagicMock(),
        owner="tester", status="active", nondeterministic=False,
        created_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    m.model_dump.return_value = defaults
    return m


@patch("noosphere.methods.REGISTRY")
def test_methods_list_json(mock_registry, runner: CliRunner):
    mock_method = _make_mock_method()
    mock_registry.list.return_value = [mock_method]
    result = runner.invoke(root_cli, ["methods", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "test_method"


@patch("noosphere.methods.REGISTRY")
def test_methods_list_table(mock_registry, runner: CliRunner):
    mock_method = _make_mock_method()
    mock_registry.list.return_value = [mock_method]
    result = runner.invoke(root_cli, ["methods", "list"])
    assert result.exit_code == 0
    assert "test_method" in result.output


@patch("noosphere.methods.REGISTRY")
def test_methods_extract_candidates_json(mock_registry, runner: CliRunner):
    exp = _make_mock_method(status="experimental", name="candidate_m")
    mock_registry.list.return_value = [exp]
    result = runner.invoke(root_cli, ["methods", "extract-candidates", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "candidate_m"


# ── ledger verify (mocked) ─────────────────────────────────────────────────

@patch("noosphere.ledger.verify", create=True)
@patch("noosphere.ledger.KeyRing")
@patch("noosphere.cli_commands.ledger._get_store")
def test_ledger_verify_json(mock_store, mock_keyring_cls, mock_verify, runner: CliRunner):
    report = MagicMock()
    report.total_entries = 5
    report.chain_valid = True
    report.signatures_valid = True
    report.ok = True
    report.issues = []
    mock_verify.return_value = report
    result = runner.invoke(root_cli, ["ledger", "verify", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["total_entries"] == 5


# ── cascade diagnostics (mocked) ──────────────────────────────────────────

@patch("noosphere.cascade.diagnostics.run_diagnostics")
@patch("noosphere.cascade.graph.CascadeGraph")
@patch("noosphere.cli_commands.cascade._get_store")
def test_cascade_diagnostics_json(mock_store, mock_graph_cls, mock_diag, runner: CliRunner):
    from noosphere.cascade import DiagnosticsReport
    mock_graph = MagicMock()
    mock_graph.iter_edges.return_value = iter([])
    mock_graph_cls.return_value = mock_graph
    report = DiagnosticsReport()
    mock_diag.return_value = report
    result = runner.invoke(root_cli, ["cascade", "diagnostics", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["edge_count"] == 0


# ── decay status (mocked) ────────────────────────────────────────────────

@patch("noosphere.decay.freshness.compute_freshness")
@patch("noosphere.cli_commands.decay._get_store")
def test_decay_status_json(mock_store_fn, mock_freshness, runner: CliRunner):
    mock_store = MagicMock()
    mock_conclusion = MagicMock()
    mock_conclusion.id = "conc-001"
    mock_conclusion.tier = "firm"
    mock_store.list_conclusions.return_value = [mock_conclusion]
    mock_store_fn.return_value = mock_store

    from noosphere.models import Freshness
    mock_freshness.return_value = Freshness.FRESH

    result = runner.invoke(root_cli, ["decay", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["freshness"] == "fresh"


# ── review rebuttals-pending (mocked) ──────────────────────────────────────

@patch("noosphere.cli_commands.review._get_store")
def test_review_rebuttals_pending_empty(mock_store_fn, runner: CliRunner):
    mock_store = MagicMock()
    mock_store.list_conclusions.return_value = []
    mock_store_fn.return_value = mock_store
    result = runner.invoke(root_cli, ["review", "rebuttals-pending", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


# ── review reviewer-calibration (mocked) ────────────────────────────────────

def test_review_calibration_empty(runner: CliRunner):
    result = runner.invoke(root_cli, ["review", "reviewer-calibration", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {}


# ── battery fetch with no adapters ────────────────────────────────────────

@patch("noosphere.cli_commands.battery._discover_adapters")
def test_battery_fetch_no_adapters(mock_discover, runner: CliRunner):
    mock_discover.return_value = {}
    result = runner.invoke(root_cli, ["battery", "fetch"])
    assert result.exit_code == 0
    assert "No corpus adapters" in result.output
