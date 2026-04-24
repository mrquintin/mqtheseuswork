"""Tests for the methods-gated CI lint script."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "check_methods_gated.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _run_lint(*extra_args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "noosphere")
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT), *extra_args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=30,
    )


def test_bypass_detected():
    """Lint detects the deliberate bypass in the fixture file."""
    result = _run_lint("--scan-dir", str(FIXTURES_DIR))
    assert result.returncode == 1, (
        f"Expected exit 1, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "bypass_example.py" in result.stdout
    assert "1 violation(s)" in result.stdout


def test_clean_repo():
    """Lint passes on the real codebase (no bypass calls outside methods/)."""
    result = _run_lint()
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
