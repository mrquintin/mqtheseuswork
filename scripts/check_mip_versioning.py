#!/usr/bin/env python3
"""CI check: detect implementation changes without a version bump.

Scans git log for commits that modify a method's implementation files
(under ``noosphere/noosphere/methods/``) without also bumping
``Method.version`` in the same commit.

A method file is identified by name: ``<method_name>.py``.  The corresponding
version is tracked in the ``@register_method(version=...)`` call inside that
file.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict


_VERSION_RE = re.compile(r'version\s*=\s*["\']([^"\']+)["\']')
_METHOD_FILE_RE = re.compile(r'^noosphere/noosphere/methods/(\w+)\.py$')


def _get_commits(since: str = "HEAD~20") -> list[str]:
    """Return a list of commit SHAs from *since* to HEAD."""
    result = subprocess.run(
        ["git", "log", "--format=%H", f"{since}..HEAD"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        # Fallback: if the ref doesn't exist (shallow repo), list all commits
        result = subprocess.run(
            ["git", "log", "--format=%H"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
    return [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]


def _files_changed(sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--root", "-r", "--name-only", sha],
        capture_output=True, text=True, timeout=15,
    )
    return [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]


def _extract_version(sha: str, filepath: str) -> str | None:
    """Extract the version string from a method file at a given commit."""
    result = subprocess.run(
        ["git", "show", f"{sha}:{filepath}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return None
    m = _VERSION_RE.search(result.stdout)
    return m.group(1) if m else None


def check_versioning(since: str = "HEAD~20") -> list[str]:
    """Return a list of violation messages."""
    commits = _get_commits(since)
    if not commits:
        return []

    method_versions: dict[str, str] = {}
    violations: list[str] = []

    for sha in reversed(commits):
        changed = _files_changed(sha)
        methods_changed: dict[str, str] = {}

        for f in changed:
            m = _METHOD_FILE_RE.match(f)
            if m:
                method_name = m.group(1)
                if method_name.startswith("_"):
                    continue
                methods_changed[method_name] = f

        for method_name, filepath in methods_changed.items():
            new_version = _extract_version(sha, filepath)
            if new_version is None:
                continue

            old_version = method_versions.get(method_name)
            if old_version is not None and new_version == old_version:
                violations.append(
                    f"Commit {sha[:8]}: method '{method_name}' implementation "
                    f"changed but version stayed at {old_version}"
                )

            method_versions[method_name] = new_version

    return violations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that method implementation changes include version bumps."
    )
    parser.add_argument(
        "--since", default="HEAD~20",
        help="Git ref to start scanning from (default: HEAD~20)",
    )
    args = parser.parse_args()

    violations = check_versioning(args.since)
    if violations:
        print("FAIL: Method implementation changed without version bump:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("OK: All method implementation changes include version bumps.")


if __name__ == "__main__":
    main()
