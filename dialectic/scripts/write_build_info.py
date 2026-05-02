"""Write Dialectic build metadata before packaging.

PyInstaller bundles imported Python modules, so the release build embeds the
commit that produced it without requiring runtime git access.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dialectic" / "build_info.py"


def _git_output(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT.parent), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def main() -> None:
    version = os.environ.get("DIALECTIC_BUILD_VERSION") or _project_version()
    commit = (
        os.environ.get("DIALECTIC_BUILD_COMMIT")
        or os.environ.get("GITHUB_SHA")
        or _git_output("rev-parse", "HEAD")
    )
    build_id = (
        os.environ.get("DIALECTIC_BUILD_ID")
        or os.environ.get("GITHUB_RUN_ID")
        or ""
    )
    source = "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local"

    TARGET.write_text(
        "\n".join(
            [
                '"""Build metadata embedded into Dialectic release bundles."""',
                "",
                f"BUILD_VERSION = {version!r}",
                f"BUILD_COMMIT = {commit!r}",
                f"BUILD_ID = {build_id!r}",
                f"BUILD_SOURCE = {source!r}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
