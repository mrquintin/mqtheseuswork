"""Round-20 doc-freshness tests.

Three checks:

1. The freshness scan over the real tree exits 0 — every broken
   link is either fixed or recorded in the allowlist at
   ``.github/doc_freshness_allowlist.txt``.

2. The broken-fixture markdown under
   ``tests/static/fixtures/broken_doc_links/`` produces the
   expected ``LINK_BROKEN`` finding for each planted dead path.

3. The surface map check (when the README has the section) only
   complains about routes that genuinely do not exist under
   ``theseus-codex/src/app/``.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_doc_freshness.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "static" / "fixtures" / "broken_doc_links"


def _run(extra: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + extra,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_script_exists() -> None:
    assert SCRIPT.is_file(), f"missing {SCRIPT}"


def test_real_tree_passes() -> None:
    proc = _run([])
    assert proc.returncode == 0, (
        "real-tree doc freshness flagged unexpected drift.\n\n"
        "Either fix the broken link or add it to "
        ".github/doc_freshness_allowlist.txt with a reason.\n\n"
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


def test_broken_fixture_is_flagged() -> None:
    fixture = FIXTURE_DIR / "has_broken_link.md"
    assert fixture.is_file()
    proc = _run(["--paths", str(fixture.relative_to(REPO_ROOT))])
    assert proc.returncode != 0, (
        f"fixture {fixture} was not flagged.\n\nstdout:\n{proc.stdout}"
    )
    assert "LINK_BROKEN" in proc.stdout, proc.stdout
    # The broken image should also be flagged.
    assert "missing_image.png" in proc.stdout


def test_external_links_ignored(tmp_path: pathlib.Path) -> None:
    """External http(s) targets and bare anchors must NOT be flagged."""
    sample = tmp_path / "external.md"
    sample.write_text(
        textwrap.dedent(
            """\
            # Externals
            - [anthropic](https://anthropic.com)
            - [github](http://github.com)
            - [mail](mailto:hi@example.com)
            - [anchor](#section)
            """
        )
    )
    # Place inside a synthetic root so it's discovered.
    root = tmp_path
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--allowlist",
            "/dev/null",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout


def test_allowlist_silences_known_breakage(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "doc.md"
    sample.write_text("[broken](./does-not-exist.md)\n")
    allow = tmp_path / "allow.txt"
    allow.write_text("./does-not-exist.md\n")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--allowlist",
            str(allow),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout


@pytest.mark.skipif(
    not (REPO_ROOT / "theseus-codex" / "src" / "app").is_dir(),
    reason="app tree absent; surface map check is opt-in",
)
def test_surface_map_is_in_sync_or_absent(tmp_path: pathlib.Path) -> None:
    """If README has a Surface map section, every listed route must
    resolve to a page in the Next.js app tree. If the section is
    absent, no check fires (opt-in).
    """
    readme = REPO_ROOT / "README.md"
    text = readme.read_text(errors="replace") if readme.is_file() else ""
    if "## Surface map" not in text:
        pytest.skip("README has no surface map section; check is opt-in")
    proc = _run([])
    assert proc.returncode == 0, proc.stdout
