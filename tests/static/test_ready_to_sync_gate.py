"""Meta-tests for the ready-to-sync gate (scripts/ready-to-sync.sh).

The gate is the last line of defense before sync — it must halt on the
first failing step, capture per-step logs, record skip events, respond
cleanly to SIGINT, and produce a structured report. These tests drive
the actual gate script via subprocess against an isolated temp git repo,
using the gate's ``READY_TO_SYNC_CMD_<N>`` overrides to plant fixture
commands per step. The fixtures live under
``tests/static/fixtures/ready_to_sync_broken/``.

Each test creates its own ephemeral repo so the suite never touches the
real working tree.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent
GATE = ROOT / "scripts" / "ready-to-sync.sh"
FIXTURES = Path(__file__).parent / "fixtures" / "ready_to_sync_broken"


def _init_temp_repo(tmp_path: Path) -> Path:
    """Spin up a minimal git repo so `git rev-parse --show-toplevel` works."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
         "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def _all_pass_env(**overrides: str) -> dict[str, str]:
    """Env that points every step at /bin/true except those overridden."""
    env = os.environ.copy()
    for i in range(1, 9):
        env[f"READY_TO_SYNC_CMD_{i}"] = "true"
    env.update(overrides)
    return env


def _run(cwd: Path, env: dict[str, str], *args: str,
         timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(GATE), "--no-color", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ── exit-code contract ────────────────────────────────────────────────────────


def test_all_steps_pass_exits_zero(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    result = _run(repo, _all_pass_env())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Gate PASSED" in result.stdout


def test_step_failure_exits_non_zero(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    result = _run(repo, _all_pass_env(READY_TO_SYNC_CMD_4="false"))
    assert result.returncode == 1
    assert "Gate FAILED at step 4" in result.stdout


# ── halt-on-first-failure ─────────────────────────────────────────────────────


def test_gate_halts_at_first_failure_does_not_run_later_steps(
    tmp_path: Path,
) -> None:
    repo = _init_temp_repo(tmp_path)
    # Use a marker file: if step 8 runs, it'll be written. After step 2 fails
    # the gate must NOT execute later steps, so the marker should be absent.
    marker = repo / "step8_ran.marker"
    result = _run(
        repo,
        _all_pass_env(
            READY_TO_SYNC_CMD_2="false",
            READY_TO_SYNC_CMD_8=f"touch {marker}",
        ),
    )
    assert result.returncode == 1
    assert "Gate FAILED at step 2" in result.stdout
    assert not marker.exists(), "step 8 ran after step 2 failed"


# ── --from / --only filters ───────────────────────────────────────────────────


def test_from_skips_earlier_steps(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    early_marker = repo / "early.marker"
    # Step 1's override would write the marker — but --from 3 must skip it.
    result = _run(
        repo,
        _all_pass_env(READY_TO_SYNC_CMD_1=f"touch {early_marker}"),
        "--from", "3",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not early_marker.exists(), "step 1 ran despite --from 3"
    # And steps 3-8 ran (none failed):
    assert "Gate PASSED" in result.stdout


def test_only_runs_just_that_step(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    other = repo / "other.marker"
    # Step 4 is the only allowed run; every other override would touch the
    # marker but must NOT execute.
    cmds = {f"READY_TO_SYNC_CMD_{i}": f"touch {other}" for i in range(1, 9)}
    cmds["READY_TO_SYNC_CMD_4"] = "true"
    env = _all_pass_env(**cmds)
    result = _run(repo, env, "--only", "4")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not other.exists(), "a non-target step ran under --only"


# ── --skip + audit log ────────────────────────────────────────────────────────


def test_skip_records_audit_entry(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    result = _run(
        repo,
        _all_pass_env(),
        "--skip", "3",
        "--skip-reason", "smoke harness flaky on this fixture host",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = repo / "docs" / "verification" / "ready_to_sync_skips.log"
    assert log.exists(), "skip audit log was not written"
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["step"] == 3
    assert entry["step_name"] == "smoke-harness"
    assert entry["reason"] == "smoke harness flaky on this fixture host"
    # The audit entry must carry an ISO-8601 UTC timestamp.
    assert entry["ts"].endswith("Z")
    assert "T" in entry["ts"]


def test_skip_multiple_steps(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    # Plant failing commands at the steps we're skipping; success proves
    # the gate honoured the skip instead of executing them.
    result = _run(
        repo,
        _all_pass_env(
            READY_TO_SYNC_CMD_3="false",
            READY_TO_SYNC_CMD_6="false",
        ),
        "--skip", "3,6",
        "--skip-reason", "test-multiskip",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = repo / "docs" / "verification" / "ready_to_sync_skips.log"
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    steps = sorted(json.loads(ln)["step"] for ln in lines)
    assert steps == [3, 6]


# ── planted-broken fixtures (the prompt-specified cases) ──────────────────────


def test_broken_migration_fixture_fails_step_1(tmp_path: Path) -> None:
    """A planted broken migration script must surface at step 1."""
    repo = _init_temp_repo(tmp_path)
    fixture = FIXTURES / "broken_migration.py"
    assert fixture.is_file(), "missing test fixture"
    result = _run(
        repo,
        _all_pass_env(READY_TO_SYNC_CMD_1=f"python3 {fixture}"),
    )
    assert result.returncode == 1
    assert "Gate FAILED at step 1" in result.stdout
    # And the per-step log must capture the fixture's stderr.
    report_dirs = list((repo / "docs/verification/ready_to_sync").iterdir())
    assert len(report_dirs) == 1
    log = next(report_dirs[0].glob("step1_*.log"))
    text = log.read_text()
    assert "FIXTURE: planted broken Prisma migration chain" in text


def test_broken_import_cycle_fixture_fails_step_2(tmp_path: Path) -> None:
    """A planted broken import-cycle script must surface at step 2."""
    repo = _init_temp_repo(tmp_path)
    fixture = FIXTURES / "broken_import_cycle.py"
    assert fixture.is_file(), "missing test fixture"
    result = _run(
        repo,
        _all_pass_env(READY_TO_SYNC_CMD_2=f"python3 {fixture}"),
    )
    assert result.returncode == 1
    assert "Gate FAILED at step 2" in result.stdout
    report_dirs = list((repo / "docs/verification/ready_to_sync").iterdir())
    log = next(report_dirs[0].glob("step2_*.log"))
    text = log.read_text()
    assert "import cycle detected" in text
    # Resume hint must point at step 2.
    assert "--from 2" in result.stdout


# ── report contents ───────────────────────────────────────────────────────────


def test_report_md_contains_per_step_table(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    _run(repo, _all_pass_env())
    report = next(
        (repo / "docs/verification/ready_to_sync").glob("*/REPORT.md")
    )
    text = report.read_text()
    assert "# Ready-to-Sync Gate Report" in text
    assert "Migration linearity + parity" in text
    assert "Bug-replay regression catalog" in text
    # Verdict line:
    assert "PASS" in text


# ── full-gate runtime budget ──────────────────────────────────────────────────


def test_full_gate_completes_under_twelve_minutes_on_fixtures(
    tmp_path: Path,
) -> None:
    """The gate, against fixture commands, should complete well under 12m."""
    repo = _init_temp_repo(tmp_path)
    start = time.monotonic()
    result = _run(repo, _all_pass_env(), timeout=720.0)
    elapsed = time.monotonic() - start
    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 720.0, f"gate took {elapsed:.1f}s against fixtures"


# ── SIGINT handling ───────────────────────────────────────────────────────────


def test_sigint_during_step_3_prints_resume_hint(tmp_path: Path) -> None:
    """SIGINT while a step is running must surface the resume command."""
    repo = _init_temp_repo(tmp_path)
    env = _all_pass_env(
        # Steps 1 and 2 finish instantly; step 3 sleeps long enough for the
        # test to deliver SIGINT before it would otherwise complete.
        READY_TO_SYNC_CMD_3="sleep 30",
    )
    proc = subprocess.Popen(
        [str(GATE), "--no-color"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait until the gate has actually started step 3 (its banner appears).
    deadline = time.monotonic() + 10.0
    seen_step_3 = False
    captured = []
    assert proc.stdout is not None
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
            continue
        captured.append(line)
        if "[3/8]" in line:
            seen_step_3 = True
            break
    assert seen_step_3, "never observed step 3 starting: " + "".join(captured)

    proc.send_signal(signal.SIGINT)
    try:
        remaining, _ = proc.communicate(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    output = "".join(captured) + (remaining or "")
    assert proc.returncode == 130, (
        f"expected SIGINT exit 130, got {proc.returncode}\n{output}"
    )
    assert "--from 3" in output, output
    assert "SIGINT received during step 3" in output, output


# ── flag validation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "args",
    [
        ("--from", "9"),
        ("--from", "0"),
        ("--from", "abc"),
        ("--only", "12"),
        ("--skip", "5,99"),
    ],
)
def test_invalid_flag_values_exit_2(tmp_path: Path, args: tuple[str, ...]) -> None:
    repo = _init_temp_repo(tmp_path)
    result = _run(repo, _all_pass_env(), *args)
    assert result.returncode == 2, result.stdout + result.stderr
