"""Smoke-test for scripts/build_template.sh.

Constructs a tiny synthetic source tree with its own manifest, runs the
extraction script against it, and asserts the four guarantees from
coding_prompts/68_theseus_template_extraction.txt:

  * every CORE file is present in the output
  * no FIRM file is present in the output
  * every CONFIG token has been substituted
  * the output git log has exactly one commit
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_template.sh"

CORE_FILES = {
    "Makefile": "all:\n\techo build\n",
    "noosphere/__init__.py": "VERSION = '1.0'\n",
    "docs/guides/01_Quick_Start.tex": "Quick start.\n",
    "README_CORE.md": "Generic platform doc.\n",
}

CONFIG_FILES = {
    "pyproject.toml": textwrap.dedent(
        """
        [project]
        name = "THESEUS_ORG_NAME"
        description = "Theseus platform for Theseus"
        """
    ).lstrip(),
    ".env.live.template": textwrap.dedent(
        """
        THESEUS_ORG_NAME=Theseus
        THESEUS_ORG_SLUG=theseus-local
        ANTHROPIC_API_KEY=
        FOUNDER_DISPLAY=Michael Quintin
        """
    ).lstrip(),
}

FIRM_FILES = {
    "FOUNDERS_READING_AND_RESEARCH.md": "founder curriculum\n",
    "benchmarks/quintin_hypothesis/v1/results.md": "Quintin Hypothesis results\n",
    "coding_prompts/archive_round17/01_qh.txt": "qh round 17\n",
    ".claude_code_runs/20260101_run.jsonl": "{}\n",
    "docs/research/QH_Benchmark_v1_Results.tex": "QH benchmark tex\n",
}

SEED_DIRS = ["noosphere_data", "theseus-public/content"]

PAYLOAD_FILES = {
    "theseus-template/README.md": "# Tenant readme — overwrites any source README.\n",
    "theseus-template/scripts/bootstrap.sh": "#!/usr/bin/env bash\necho bootstrap stub\n",
}


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _build_synthetic_source(root: Path) -> Path:
    """Lay out a small synthetic source tree under `root`."""
    for rel, body in {**CORE_FILES, **CONFIG_FILES, **FIRM_FILES}.items():
        _write(root, rel, body)
    for d in SEED_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
        _write(root, f"{d}/firm_filled_seed.md", "firm-seeded content\n")
    for rel, body in PAYLOAD_FILES.items():
        _write(root, rel, body)
    (root / "theseus-template" / "scripts" / "bootstrap.sh").chmod(0o755)

    manifest = {
        "version": 1,
        "include_core": sorted(CORE_FILES.keys()) + ["docs/guides/"],
        "include_config": sorted(CONFIG_FILES.keys()),
        "include_seed": [f"{d}/" for d in SEED_DIRS],
        "seed_stubs": {
            "noosphere_data/noosphere_config.json": json.dumps(
                {"tenant_slug": "<your-firm-slug>"}, indent=2
            ),
            "theseus-public/content/README.md": "# Empty content\n",
        },
        "tokens": {
            "THESEUS_ORG_NAME": {
                "description": "firm name",
                "source_value": "Theseus",
                "template_value": "<your firm name>",
            },
            "THESEUS_ORG_SLUG": {
                "description": "firm slug",
                "source_value": "theseus-local",
                "template_value": "<your-firm-slug>",
            },
            "THESEUS_FOUNDER_DISPLAY_NAME": {
                "description": "founder display",
                "source_value": "Michael Quintin",
                "template_value": "<founder name>",
            },
        },
        "forbidden_phrases": ["Michael Quintin", "Quintin Hypothesis"],
        "exclude_firm": sorted(FIRM_FILES.keys())
        + [
            "benchmarks/",
            "coding_prompts/",
            ".claude_code_runs/",
            "docs/research/",
        ],
        "exclude_globs": ["**/__pycache__/", "**/.DS_Store"],
        "payload": sorted(PAYLOAD_FILES.keys()),
        "output": {
            "default_dir": "../theseus-template-out",
            "initial_commit_message": "Initial commit (test extraction)",
            "initial_commit_author_name": "Test Builder",
            "initial_commit_author_email": "test@theseus.invalid",
        },
    }

    import yaml

    manifest_path = root / "scripts" / "template" / "manifest.yml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest_path


def _run_extraction(src: Path, dest: Path, manifest: Path) -> None:
    env = os.environ.copy()
    result = subprocess.run(
        [
            "bash",
            str(BUILD_SCRIPT),
            "--src",
            str(src),
            "--dest",
            str(dest),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"build_template.sh failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_extraction_full(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "out"
    manifest = _build_synthetic_source(src)

    _run_extraction(src, dest, manifest)

    # 1) Every CORE file is present.
    for rel in CORE_FILES:
        assert (dest / rel).is_file(), f"CORE file missing: {rel}"
    assert (dest / "docs/guides/01_Quick_Start.tex").is_file()

    # 2) No FIRM file is present.
    for rel in FIRM_FILES:
        assert not (dest / rel).exists(), f"FIRM file leaked: {rel}"
    assert not (dest / "benchmarks").exists()
    assert not (dest / "coding_prompts").exists()
    assert not (dest / ".claude_code_runs").exists()
    assert not (dest / "docs/research").exists()

    # 3) Every CONFIG token has been substituted.
    pyproject_text = (dest / "pyproject.toml").read_text()
    assert "THESEUS_ORG_NAME" not in pyproject_text, pyproject_text
    assert "Theseus" not in pyproject_text, pyproject_text
    assert "<your firm name>" in pyproject_text, pyproject_text

    env_text = (dest / ".env.live.template").read_text()
    assert "<your firm name>" in env_text
    assert "<your-firm-slug>" in env_text
    assert "<founder name>" in env_text
    assert "Michael Quintin" not in env_text
    assert "Theseus" not in env_text

    # 4) Payload files were written.
    assert (dest / "README.md").read_text().startswith("# Tenant readme")
    assert (dest / "scripts/bootstrap.sh").read_text().startswith("#!/usr/bin/env bash")

    # 5) SEED stubs are present.
    seed_stub = json.loads((dest / "noosphere_data/noosphere_config.json").read_text())
    assert seed_stub["tenant_slug"] == "<your-firm-slug>"
    assert (dest / "theseus-public/content/README.md").is_file()
    # SEED firm content was NOT copied through.
    assert not (dest / "noosphere_data/firm_filled_seed.md").exists()
    assert not (dest / "theseus-public/content/firm_filled_seed.md").exists()

    # 6) Output git log has exactly one commit.
    git_log = subprocess.run(
        ["git", "-C", str(dest), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = [line for line in git_log.stdout.splitlines() if line.strip()]
    assert len(commits) == 1, f"expected one commit, got {commits!r}"
    assert "Initial commit" in commits[0]

    # 7) No forbidden phrase survives anywhere in the output.
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        assert "Michael Quintin" not in text, f"founder name leaked into {path}"
        assert "Quintin Hypothesis" not in text, f"firm benchmark name leaked into {path}"


def test_extraction_idempotent(tmp_path: Path) -> None:
    """Same source → same output (byte-identical modulo timestamps and the .git dir)."""
    src = tmp_path / "src"
    src.mkdir()
    manifest = _build_synthetic_source(src)

    dest_a = tmp_path / "out_a"
    dest_b = tmp_path / "out_b"
    _run_extraction(src, dest_a, manifest)
    _run_extraction(src, dest_b, manifest)

    files_a = {
        str(p.relative_to(dest_a)): p.read_bytes()
        for p in dest_a.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    files_b = {
        str(p.relative_to(dest_b)): p.read_bytes()
        for p in dest_b.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert files_a.keys() == files_b.keys()
    for rel, content in files_a.items():
        assert content == files_b[rel], f"differs: {rel}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
