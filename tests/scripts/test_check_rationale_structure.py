"""Tests for ``scripts/check_rationale_structure.py``.

Covers part F of the documentation-rot repair: exercise the structure check
and the cross-link audit against synthetic RATIONALEs so the gate's behaviour
is pinned without depending on the live repo tree.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_rationale_structure.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_rationale_structure", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


crs = _load_module()


# A structurally complete synthetic RATIONALE: all seven sections, in order,
# with one cross-linked citation.
_GOOD_RATIONALE = """\
# Synthetic Method — Rationale

## Purpose
Does a synthetic thing for the test suite.

## Inputs
- `x` (int) — a number.

## Outputs
- `y` (int) — a bigger number.

## Algorithm
Adds one to `x`.

## Domain
Synthetic only. No machine-checkable `DomainBound` is declared.

## Failure Modes
This method has no `FAILURES.yaml` catalog; limits are documented inline.

## References
- The synthetic backing paper — [@synthetic2026paper].
"""

# A well-formed bibliography: one entry with a real arXiv id.
_GOOD_BIB = """\
@inproceedings{synthetic2026paper,
  author = {Doe, Jane},
  title  = {A Synthetic Paper},
  year   = {2026},
  eprint = {2601.01234},
  archivePrefix = {arXiv},
  url    = {https://arxiv.org/abs/2601.01234}
}
"""

# Same entry, but the DOI is broken — not a `10.NNNN/...` form.
_BROKEN_DOI_BIB = """\
@article{synthetic2026paper,
  author = {Doe, Jane},
  title  = {A Synthetic Paper},
  year   = {2026},
  doi    = {not-a-real-doi},
  url    = {https://example.org/synthetic}
}
"""


# ── Structure check ─────────────────────────────────────────────────────────


def test_structure_check_passes_on_complete_rationale(tmp_path: Path):
    path = tmp_path / "synthetic_method.RATIONALE.md"
    path.write_text(_GOOD_RATIONALE, encoding="utf-8")
    assert crs.check_structure(path) == []


def test_structure_check_flags_missing_section(tmp_path: Path):
    # Drop the Failure Modes section.
    missing = _GOOD_RATIONALE.replace(
        "## Failure Modes\n"
        "This method has no `FAILURES.yaml` catalog; limits are documented inline.\n\n",
        "",
    )
    path = tmp_path / "synthetic_method.RATIONALE.md"
    path.write_text(missing, encoding="utf-8")
    violations = crs.check_structure(path)
    assert any("missing required section '## Failure Modes'" in v for v in violations)


def test_structure_check_flags_out_of_order_sections(tmp_path: Path):
    # All seven present, but Inputs and Outputs swapped.
    reordered = _GOOD_RATIONALE.replace(
        "## Inputs\n- `x` (int) — a number.\n\n## Outputs\n- `y` (int) — a bigger number.\n",
        "## Outputs\n- `y` (int) — a bigger number.\n\n## Inputs\n- `x` (int) — a number.\n",
    )
    path = tmp_path / "synthetic_method.RATIONALE.md"
    path.write_text(reordered, encoding="utf-8")
    violations = crs.check_structure(path)
    assert any("out of order" in v for v in violations)


# ── Cross-link audit ────────────────────────────────────────────────────────


def test_crosslink_audit_passes_when_citation_resolves(tmp_path: Path):
    bib = tmp_path / "References.bib"
    bib.write_text(_GOOD_BIB, encoding="utf-8")
    entries = crs.parse_bib(bib)
    assert "synthetic2026paper" in entries
    assert crs.audit_crosslinks(_GOOD_RATIONALE, entries) == []
    assert crs.audit_bib_entries(entries) == []


def test_crosslink_audit_flags_missing_bib_entry(tmp_path: Path):
    # Empty bibliography — the [@synthetic2026paper] citation cannot resolve.
    entries: dict = {}
    violations = crs.audit_crosslinks(_GOOD_RATIONALE, entries, label="synthetic")
    assert any("synthetic2026paper" in v and "no entry" in v for v in violations)


def test_crosslink_audit_catches_broken_doi(tmp_path: Path):
    bib = tmp_path / "References.bib"
    bib.write_text(_BROKEN_DOI_BIB, encoding="utf-8")
    entries = crs.parse_bib(bib)
    violations = crs.audit_bib_entries(entries)
    assert any(
        "synthetic2026paper" in v and "malformed DOI" in v for v in violations
    ), violations


def test_crosslink_audit_catches_entry_with_no_locator(tmp_path: Path):
    bib = tmp_path / "References.bib"
    bib.write_text(
        "@misc{nolocator2026,\n"
        "  author = {Doe, Jane},\n"
        "  title  = {No Locator},\n"
        "  year   = {2026}\n"
        "}\n",
        encoding="utf-8",
    )
    entries = crs.parse_bib(bib)
    violations = crs.audit_bib_entries(entries)
    assert any("no usable locator" in v for v in violations)


# ── End-to-end driver over a synthetic methods dir ──────────────────────────


def test_run_is_clean_on_synthetic_tree(tmp_path: Path):
    methods_dir = tmp_path / "methods"
    methods_dir.mkdir()
    (methods_dir / "synthetic_method.RATIONALE.md").write_text(
        _GOOD_RATIONALE, encoding="utf-8"
    )
    bib = tmp_path / "References.bib"
    bib.write_text(_GOOD_BIB, encoding="utf-8")
    assert crs.run(methods_dir, bib) == []


def test_run_reports_broken_doi_and_missing_section(tmp_path: Path):
    methods_dir = tmp_path / "methods"
    methods_dir.mkdir()
    # One RATIONALE missing References entirely.
    bad = _GOOD_RATIONALE.replace(
        "## References\n- The synthetic backing paper — [@synthetic2026paper].\n",
        "",
    )
    (methods_dir / "synthetic_method.RATIONALE.md").write_text(bad, encoding="utf-8")
    bib = tmp_path / "References.bib"
    bib.write_text(_BROKEN_DOI_BIB, encoding="utf-8")

    violations = crs.run(methods_dir, bib)
    assert any("missing required section '## References'" in v for v in violations)
    assert any("malformed DOI" in v for v in violations)


def test_repo_check_passes():
    """The live repo tree must satisfy the gate after the repair pass."""
    methods_dir = REPO_ROOT / "noosphere" / "noosphere" / "methods"
    bib = REPO_ROOT / "docs" / "methods" / "References.bib"
    assert crs.run(methods_dir, bib) == []
