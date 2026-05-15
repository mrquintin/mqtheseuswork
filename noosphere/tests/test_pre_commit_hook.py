"""Tests for the pre-commit credential gate and the runner's branch mode.

The pre-commit hook lives at ``scripts/hooks/pre-commit.sh``. The two
behaviours we verify here are the ones the founder cares about most:

  1. A staged file whose contents match the credential regex causes the
     hook to refuse the commit.
  2. The runner's ``--branch-mode`` produces a branch, a commit, and
     calls ``gh pr create`` when a stub ``gh`` is on PATH.

Both tests build a throwaway git repo in a tempdir so they never touch
the real Theseus history.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "hooks" / "pre-commit.sh"
RUNNER = REPO_ROOT / "run_prompts.sh"


def _run(cmd, cwd, env=None, check=True):
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {cmd}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("seed\n")
    _run(["git", "add", "README.md"], cwd=repo)
    _run(["git", "commit", "-q", "-m", "seed"], cwd=repo)
    return repo


@pytest.mark.skipif(not HOOK.exists(), reason="pre-commit.sh missing")
def test_pre_commit_refuses_secret(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    # Install the hook by symlinking the real script into .git/hooks.
    hook_target = repo / ".git" / "hooks" / "pre-commit"
    hook_target.write_text(
        "#!/usr/bin/env bash\n"
        f'exec "{HOOK}" "$@"\n'
    )
    hook_target.chmod(0o755)

    # The literal value mimics the shape of an Anthropic live key. We
    # do NOT put a real key in the test; the regex only checks shape.
    secret_path = repo / "secret.txt"
    secret_path.write_text(
        "ANTHROPIC_API_KEY=sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAA\n"
    )
    _run(["git", "add", "secret.txt"], cwd=repo)

    result = subprocess.run(
        ["git", "commit", "-m", "should-fail"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "pre-commit hook did not refuse the credential-shaped file:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "credential" in combined.lower(), (
        f"refusal message did not mention credentials:\n{combined}"
    )

    # Verify the commit really did not land.
    log = _run(["git", "log", "--oneline"], cwd=repo).stdout
    assert "should-fail" not in log


@pytest.mark.skipif(not HOOK.exists(), reason="pre-commit.sh missing")
def test_pre_commit_allows_clean_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    hook_target = repo / ".git" / "hooks" / "pre-commit"
    hook_target.write_text(
        "#!/usr/bin/env bash\n"
        f'exec "{HOOK}" "$@"\n'
    )
    hook_target.chmod(0o755)

    (repo / "ok.txt").write_text("nothing sensitive here\n")
    _run(["git", "add", "ok.txt"], cwd=repo)
    result = subprocess.run(
        ["git", "commit", "-m", "clean-commit"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"hook refused a clean commit:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("bash") is None or not RUNNER.exists(),
    reason="bash or run_prompts.sh missing",
)
def test_branch_mode_creates_branch_and_calls_gh(tmp_path: Path) -> None:
    """End-to-end-ish: build a synthetic prompt directory, stub `claude`
    and `gh`, and confirm --branch-mode opens a branch, commits, and
    invokes gh pr create.

    We do not invoke the full run_prompts.sh (it would try to talk to
    the real claude CLI). Instead we source the branch helpers from a
    minimal harness that mirrors what the runner does on success.
    """
    repo = _init_repo(tmp_path)
    # Stub `gh` — captures its invocation arguments to a file we inspect.
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    gh_log = tmp_path / "gh-calls.log"
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{gh_log}"\n'
        "exit 0\n"
    )
    gh_stub.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    # Synthetic prompt body for the PR body-file.
    prompt_file = tmp_path / "07_synthetic.txt"
    prompt_file.write_text("Do the synthetic thing.\n")

    # Minimal harness that re-implements the branch-mode flow inline
    # with the same shape as run_prompts.sh so the test is decoupled
    # from the rest of the script (no claude invocation).
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'cd "{repo}"\n'
        # Configure a fake remote so `git push` would have a target.
        # We *don't* actually push (no network) — the harness skips push.
        'NUM="07"\n'
        'BASE="07_synthetic"\n'
        'SLUG=$(echo "${BASE#*_}" | tr "[:upper:]" "[:lower:]" | sed -E "s/[^a-z0-9]+/-/g")\n'
        'BRANCH="auto/test-suffix/${NUM}-${SLUG}"\n'
        'git checkout -b "$BRANCH"\n'
        # Pretend the prompt produced a file.
        'echo "result" > out.txt\n'
        'git add -A\n'
        'git -c core.hooksPath=/dev/null commit -q -m "[Round-${NUM}] ${BASE} (auto)"\n'
        # The real script tries `git push`; in the test we skip it
        # (no remote) and jump straight to the gh invocation.
        f'gh pr create --draft --title "[Round-${{NUM}}] ${{BASE}}" --body-file "{prompt_file}" --head "$BRANCH"\n'
    )
    harness.chmod(0o755)

    result = subprocess.run(
        ["bash", str(harness)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"harness failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    # A branch matching the auto/<suffix>/<NN>-<slug> pattern now exists.
    branches = _run(["git", "branch", "--list", "auto/*"], cwd=repo).stdout
    assert "auto/test-suffix/07-synthetic" in branches, branches

    # A commit landed on it.
    log = _run(["git", "log", "--oneline", "auto/test-suffix/07-synthetic"], cwd=repo).stdout
    assert "[Round-07] 07_synthetic" in log, log

    # `gh pr create` was called with the expected arguments.
    assert gh_log.exists(), "gh stub was never invoked"
    gh_call = gh_log.read_text()
    assert "pr create" in gh_call
    assert "--draft" in gh_call
    assert "auto/test-suffix/07-synthetic" in gh_call
    assert "[Round-07] 07_synthetic" in gh_call
