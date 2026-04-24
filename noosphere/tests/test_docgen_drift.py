"""Test doc drift detection: manual edits to generated files are rejected."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_doc_drift import check_drift, check_precommit_hook


def test_precommit_rejects_manual_edit_to_spec():
    docs_dir = Path("docs/methods")
    staged = [
        "docs/methods/nli_scorer/1.0.0/spec.md",
        "docs/methods/nli_scorer/1.0.0/rationale.md",
    ]
    violations = check_precommit_hook(staged, docs_dir)
    assert len(violations) == 1
    assert "spec.md" in violations[0]


def test_precommit_allows_rationale_edits():
    docs_dir = Path("docs/methods")
    staged = ["docs/methods/nli_scorer/1.0.0/rationale.md"]
    violations = check_precommit_hook(staged, docs_dir)
    assert len(violations) == 0


def test_precommit_rejects_all_generated_files():
    docs_dir = Path("docs/methods")
    generated = ["spec.md", "examples.md", "calibration.md", "transfer.md", "operations.md", "index.md"]
    staged = [f"docs/methods/test/1.0.0/{f}" for f in generated]
    violations = check_precommit_hook(staged, docs_dir)
    assert len(violations) == len(generated)


def test_drift_detects_changed_content(tmp_path):
    committed = tmp_path / "committed" / "method" / "1.0.0"
    committed.mkdir(parents=True)
    (committed / "spec.md").write_text("# Original content\n")

    recompiled = tmp_path / "recompiled" / "method" / "1.0.0"
    recompiled.mkdir(parents=True)
    (recompiled / "spec.md").write_text("# Modified content\n")

    diffs = check_drift(
        tmp_path / "committed" / "method" / "1.0.0",
        tmp_path / "recompiled" / "method" / "1.0.0",
    )
    assert len(diffs) == 1
    assert "spec.md" in diffs[0]


def test_drift_ignores_rationale(tmp_path):
    committed = tmp_path / "committed"
    committed.mkdir(parents=True)
    (committed / "rationale.md").write_text("# Hand authored\n")

    recompiled = tmp_path / "recompiled"
    recompiled.mkdir(parents=True)
    (recompiled / "rationale.md").write_text("# Different\n")

    diffs = check_drift(committed, recompiled)
    assert len(diffs) == 0


def test_no_drift_when_identical(tmp_path):
    committed = tmp_path / "committed"
    committed.mkdir(parents=True)
    (committed / "spec.md").write_text("# Same\n")

    recompiled = tmp_path / "recompiled"
    recompiled.mkdir(parents=True)
    (recompiled / "spec.md").write_text("# Same\n")

    diffs = check_drift(committed, recompiled)
    assert len(diffs) == 0
