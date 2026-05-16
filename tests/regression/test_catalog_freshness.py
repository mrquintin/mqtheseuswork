"""Freshness check for ``docs/security/BUG_CATALOG.md``.

The catalog is LIVING: every Bxx entry in the markdown MUST correspond
to a ``test_b<NN>_*`` function in :mod:`tests.regression.test_bug_replay`,
and every test function MUST have a catalog entry. Adding a new bug
without updating both sides is the failure this test exists to catch.

Set the env var ``THESEUS_REGRESSION_PLANT_ORPHAN`` to ``catalog`` or
``test`` to plant a fake orphan and confirm this test fails (used by
operators when they want to verify the gate is alive).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tests.regression.conftest import repo_root


CATALOG = repo_root() / "docs" / "security" / "BUG_CATALOG.md"
TEST_FILE = repo_root() / "tests" / "regression" / "test_bug_replay.py"

# A catalog entry looks like:  ## B07 — AES password mismatch …
# We accept any heading level so the catalog can be reorganised.
_CATALOG_BXX = re.compile(r"^#{1,6}\s*(B\d{2})\b", re.MULTILINE)

# A test function looks like:  def test_b07_unattended_password_file(...):
_TEST_BXX = re.compile(r"^\s*def\s+test_(b\d{2})_[a-zA-Z0-9_]+\s*\(", re.MULTILINE)


def _catalog_entries() -> set[str]:
    assert CATALOG.exists(), f"missing catalog: {CATALOG}"
    return {m.group(1) for m in _CATALOG_BXX.finditer(CATALOG.read_text())}


def _test_entries() -> set[str]:
    assert TEST_FILE.exists(), f"missing test file: {TEST_FILE}"
    return {m.group(1).upper() for m in _TEST_BXX.finditer(TEST_FILE.read_text())}


def test_catalog_and_tests_are_in_sync() -> None:
    """Every Bxx in the catalog has a test, and vice versa."""
    catalog = _catalog_entries()
    tests = _test_entries()

    # Operator-triggered planted-orphan mode for verifying the gate.
    plant = os.environ.get("THESEUS_REGRESSION_PLANT_ORPHAN", "").strip().lower()
    if plant == "catalog":
        catalog = catalog | {"B99"}  # entry in catalog with no test
    elif plant == "test":
        tests = tests | {"B99"}  # test with no catalog entry

    missing_tests = sorted(catalog - tests)
    missing_catalog = sorted(tests - catalog)

    detail: list[str] = []
    if missing_tests:
        detail.append(
            "Catalog entries without a regression test "
            f"(add to {TEST_FILE.relative_to(repo_root())}):\n  - "
            + "\n  - ".join(missing_tests)
        )
    if missing_catalog:
        detail.append(
            "Tests without a catalog entry "
            f"(add to {CATALOG.relative_to(repo_root())}):\n  - "
            + "\n  - ".join(missing_catalog)
        )
    assert not detail, "\n\n".join(detail)


def test_catalog_has_how_to_add_section() -> None:
    """Every operator who adds a new bug must follow the same recipe.
    The catalog has a 'How to add a new entry' footer; if it is removed,
    new contributors will diverge from the convention.
    """
    body = CATALOG.read_text()
    assert "How to add a new entry" in body, (
        "BUG_CATALOG.md lost its 'How to add a new entry' footer. New "
        "contributors will diverge from the format — restore it."
    )


@pytest.mark.parametrize("plant", ["catalog", "test"])
def test_planted_orphan_would_fail(plant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Self-test: plant a fake orphan and confirm the freshness check
    surfaces it. Without this, a future refactor could silently delete the
    cross-check.
    """
    monkeypatch.setenv("THESEUS_REGRESSION_PLANT_ORPHAN", plant)
    with pytest.raises(AssertionError) as exc:
        test_catalog_and_tests_are_in_sync()
    assert "B99" in str(exc.value), (
        f"Planted orphan was not surfaced under plant={plant!r}. "
        f"AssertionError text: {exc.value}"
    )
