"""
Regression tests for the Round-19 module hierarchy.

These tests assert three properties of the refactored layout:

1. Each new facade package (``noosphere.core``, ``noosphere.inquiry``,
   ``noosphere.io``, ``noosphere.cli``) imports cleanly and exposes its
   documented public surface.
2. The legacy CLI surface (``noosphere.cli.cli``, ``get_orchestrator``,
   parsing helpers, every Click subcommand) is preserved by the package
   shim — internal callers in ``cli_commands/*`` continue to work.
3. The ``import-linter`` contract declared in ``noosphere/.import-linter``
   passes against the live package, if ``import-linter`` is installed.
   The lint step is skipped (not failed) when the dependency is missing,
   so the test passes on a vanilla checkout; CI installs the dependency
   and converts the skip into a hard check.
"""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest


# ── 1. Facade packages import and re-export their documented surface. ──────


def test_core_facade_exposes_documented_surface() -> None:
    core = importlib.import_module("noosphere.core")
    required = {
        # Persistence + orchestrator
        "Store",
        "OntologyGraph",
        "NoosphereOrchestrator",
        # Ledger
        "Ledger",
        "KeyRing",
        "verify",
        "sign_publication",
        "verify_signature",
        # Models
        "Claim",
        "Principle",
        "Artifact",
        "Chunk",
        "Episode",
        "Speaker",
        # Observability
        "get_logger",
        "configure_logging",
        "start_span",
        "current_trace",
    }
    missing = required - set(vars(core))
    assert not missing, f"noosphere.core missing exports: {sorted(missing)}"


def test_inquiry_facade_reexports_subpackages() -> None:
    inquiry = importlib.import_module("noosphere.inquiry")
    for sub in ("coherence", "evaluation", "peer_review", "mitigations", "redteam"):
        assert hasattr(inquiry, sub), f"noosphere.inquiry.{sub} not re-exported"
        # And the real implementation module loads.
        importlib.import_module(f"noosphere.{sub}")


def test_io_facade_reexports_perimeter_modules() -> None:
    io = importlib.import_module("noosphere.io")
    for sub in ("codex_bridge", "storage_client", "ingester", "ingest_artifacts"):
        assert hasattr(io, sub), f"noosphere.io.{sub} not re-exported"
    # Documented helpers are pulled to the top.
    assert hasattr(io, "LocalDiskStorage")
    assert hasattr(io, "StorageClient")


def test_cli_facade_exposes_typer_and_legacy_click() -> None:
    cli_pkg = importlib.import_module("noosphere.cli")
    # Typer surface
    assert hasattr(cli_pkg, "app"), "Typer app missing from noosphere.cli"
    assert callable(getattr(cli_pkg, "main", None)), "main() missing or not callable"
    # Legacy Click surface — the entry points the operator runbook + tests use.
    assert hasattr(cli_pkg, "cli"), "Click root group 'cli' missing"
    assert callable(getattr(cli_pkg, "get_orchestrator", None))
    assert callable(getattr(cli_pkg, "parse_date", None))
    # ``cli_commands`` plugin registry is reachable.
    assert hasattr(cli_pkg, "cli_commands")


def test_cli_package_is_directly_executable() -> None:
    """``python -m noosphere.cli`` must keep the legacy Click surface alive."""

    result = subprocess.run(
        [sys.executable, "-m", "noosphere.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "benchmark" in result.stdout


# ── 2. CLI subcommand surface is preserved post-shim. ──────────────────────


def test_legacy_cli_subcommands_register() -> None:
    """The CLI runbook documents ``noosphere ingest``, ``noosphere coherence``,
    etc. — verify every plugin command is still attached after the package
    shim executes the legacy source."""

    from noosphere.cli import cli as root_cli  # noqa: WPS433

    # Spot-check a representative slice of the operator runbook commands.
    expected = {
        "ingest",
        "ask",
        "coherence",
        "stats",
        "search",
        "contradictions",
        "principles",
        "calibration",
        "conclusions",
    }
    missing = expected - set(root_cli.commands)
    assert not missing, f"CLI subcommands missing: {sorted(missing)}"


def test_cli_commands_plugin_modules_all_import() -> None:
    """Every module under ``noosphere.cli_commands`` must import cleanly —
    they each do ``from noosphere.cli import get_orchestrator`` lazily, so
    if the package shim ever stopped re-exporting that helper, this test
    would catch it."""

    import noosphere.cli_commands as pkg  # noqa: WPS433

    for _importer, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"noosphere.cli_commands.{modname}")


# ── 3. import-linter contract holds when the dep is installed. ─────────────


def _import_linter_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".import-linter"


def test_import_linter_config_present_and_well_formed() -> None:
    cfg = _import_linter_config_path()
    assert cfg.is_file(), f"missing {cfg}"
    text = cfg.read_text(encoding="utf-8")
    # The config must declare each facade-level contract used by Round 19.
    for marker in (
        "[importlinter]",
        "[importlinter:contract:core-leaf]",
        "[importlinter:contract:inquiry-bounds]",
        "[importlinter:contract:io-bounds]",
    ):
        assert marker in text, f"{marker} missing from .import-linter"


def test_import_linter_contract_holds() -> None:
    """Run import-linter against the live package, if it is installed.

    Skipped (not failed) when the dependency is absent so the test passes
    on a vanilla checkout. CI installs ``import-linter`` to convert this
    skip into a hard check.
    """

    importlinter = pytest.importorskip("importlinter")

    from importlinter.application.use_cases import read_user_options
    from importlinter.application.use_cases import create_report

    cfg = _import_linter_config_path()
    user_options = read_user_options(config_filename=str(cfg))
    report = create_report(user_options)
    assert not report.contains_failures, "\n".join(
        f"contract failed: {c.metadata.name}"
        for c in report.get_contracts_and_checks()
        if not c[1].kept
    )
