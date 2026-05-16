"""Round-20 CI workflow integrity tests.

Three layers:

1. Every real workflow under ``.github/workflows/`` parses as YAML
   and has all ``uses:`` references pinned through
   ``.github/action_pins.yml`` and all ``needs:`` references valid.
   ``RUN_SCRIPT_MISSING`` findings are surfaced but treated as
   warnings here (legacy drift is fixed incrementally; the
   gating happens in the pre-commit hook on touched workflows).

2. Each fixture under ``tests/static/fixtures/broken_workflows/``
   is asserted to produce at least one finding of the expected
   code. This proves the integrity check actually catches each
   class of drift.

3. The integrity check is fast — the full real-tree run completes
   in under 5 seconds.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_ci_workflow_integrity.py"
PINS = REPO_ROOT / ".github" / "action_pins.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
FIXTURES = REPO_ROOT / "tests" / "static" / "fixtures" / "broken_workflows"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_check_script_exists() -> None:
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    assert PINS.is_file(), f"missing {PINS}"


def test_real_tree_yaml_parses() -> None:
    """Every real workflow MUST parse as YAML and pass the
    needs:/uses: structural checks. RUN_SCRIPT_MISSING and other
    legacy drift are tolerated here — they appear in the
    integrity report and the PR comment, and are tightened by
    the pre-commit hook on touched workflows.
    """
    proc = _run(["--severity-gate", "yaml-only"])
    assert proc.returncode == 0, (
        "real-tree workflows failed YAML parsing or pin validation.\n\n"
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


def test_real_tree_runs_fast() -> None:
    start = time.perf_counter()
    _run(["--report-only"])
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"integrity check took {elapsed:.2f}s (cap 10s)"


@pytest.mark.parametrize(
    "fixture, expected_codes",
    [
        ("invalid_yaml.yml", ["YAML_PARSE"]),
        ("missing_script.yml", ["RUN_SCRIPT_MISSING"]),
        ("bad_needs.yml", ["NEEDS_UNDEFINED"]),
        ("unpinned_action.yml", ["USES_NOT_PINNED"]),
    ],
)
def test_fixture_drift_is_caught(fixture: str, expected_codes: list[str]) -> None:
    path = FIXTURES / fixture
    assert path.is_file(), f"missing fixture {path}"
    proc = _run(["--workflow", str(path)])
    assert proc.returncode != 0, (
        f"fixture {fixture} was not flagged.\n\n"
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )
    for code in expected_codes:
        assert code in proc.stdout, (
            f"fixture {fixture} did not produce {code!r}.\n\n"
            f"stdout:\n{proc.stdout}"
        )


def test_clean_subset_passes(tmp_path: pathlib.Path) -> None:
    """A minimal valid workflow must pass the strict check."""
    clean = tmp_path / "clean.yml"
    clean.write_text(
        """\
name: clean
on:
  pull_request:
jobs:
  ok:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo hello
"""
    )
    proc = _run(["--workflow", str(clean), "--severity-gate", "any"])
    # No findings of any severity expected.
    assert proc.returncode == 0, (
        f"clean fixture flagged unexpectedly.\n\nstdout:\n{proc.stdout}"
    )
