"""Tests: check_mip_versioning.py detects implementation changes without version bumps."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def git_repo(tmp_path):
    """Create a git repo with a method file that has a version."""
    repo = tmp_path / "repo"
    methods_dir = repo / "noosphere" / "noosphere" / "methods"
    methods_dir.mkdir(parents=True)

    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"}

    def run_git(*args):
        subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True,
            env=env, timeout=15,
        )

    run_git("init")
    run_git("checkout", "-b", "main")

    method_v1 = textwrap.dedent("""\
        from noosphere.methods._decorator import register_method
        @register_method(
            name="test_method",
            version="1.0.0",
        )
        def test_method(x):
            return x + 1
    """)
    (methods_dir / "test_method.py").write_text(method_v1)
    run_git("add", ".")
    run_git("commit", "-m", "Initial commit with test_method v1.0.0")

    return repo, methods_dir, env


def _run_check(repo: Path, since: str = "HEAD~5") -> subprocess.CompletedProcess:
    check_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_mip_versioning.py"
    return subprocess.run(
        [sys.executable, str(check_script), "--since", since],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_no_violation_when_version_bumped(git_repo):
    repo, methods_dir, env = git_repo

    def run_git(*args):
        subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True,
            env=env, timeout=15,
        )

    method_v2 = textwrap.dedent("""\
        from noosphere.methods._decorator import register_method
        @register_method(
            name="test_method",
            version="1.1.0",
        )
        def test_method(x):
            return x + 2  # changed implementation
    """)
    (methods_dir / "test_method.py").write_text(method_v2)
    run_git("add", ".")
    run_git("commit", "-m", "Bump test_method to v1.1.0 with new impl")

    result = _run_check(repo)
    assert result.returncode == 0, f"Expected pass but got: {result.stdout}\n{result.stderr}"
    assert "OK" in result.stdout


def test_violation_when_version_not_bumped(git_repo):
    repo, methods_dir, env = git_repo

    def run_git(*args):
        subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True,
            env=env, timeout=15,
        )

    method_changed = textwrap.dedent("""\
        from noosphere.methods._decorator import register_method
        @register_method(
            name="test_method",
            version="1.0.0",
        )
        def test_method(x):
            return x * 3  # changed implementation, same version!
    """)
    (methods_dir / "test_method.py").write_text(method_changed)
    run_git("add", ".")
    run_git("commit", "-m", "Change test_method impl without version bump")

    result = _run_check(repo)
    assert result.returncode != 0, f"Expected failure but got: {result.stdout}\n{result.stderr}"
    assert "FAIL" in result.stdout


def test_private_methods_ignored(git_repo):
    """Files starting with _ should be ignored by the checker."""
    repo, methods_dir, env = git_repo

    def run_git(*args):
        subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True,
            env=env, timeout=15,
        )

    (methods_dir / "_helper.py").write_text("def _internal(): pass\n")
    run_git("add", ".")
    run_git("commit", "-m", "Add private helper")

    (methods_dir / "_helper.py").write_text("def _internal(): return 42\n")
    run_git("add", ".")
    run_git("commit", "-m", "Change private helper")

    result = _run_check(repo)
    assert result.returncode == 0
