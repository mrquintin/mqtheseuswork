"""Tests for the rigor-gate check registry."""

from __future__ import annotations

import pytest

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import _CHECKS, all_checks, register


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure a clean registry for every test."""
    saved = dict(_CHECKS)
    _CHECKS.clear()
    yield
    _CHECKS.clear()
    _CHECKS.update(saved)


def _dummy_check(submission: RigorSubmission) -> CheckResult:
    return CheckResult(check_name="dummy", pass_=True, detail="ok")


def _other_check(submission: RigorSubmission) -> CheckResult:
    return CheckResult(check_name="other", pass_=True, detail="also ok")


class TestCheckRegistry:
    def test_starts_empty(self):
        assert all_checks() == {}

    def test_register_makes_check_available(self):
        register("dummy", _dummy_check)
        checks = all_checks()
        assert "dummy" in checks
        assert checks["dummy"] is _dummy_check

    def test_multiple_registrations(self):
        register("dummy", _dummy_check)
        register("other", _other_check)
        checks = all_checks()
        assert len(checks) == 2
        assert "dummy" in checks
        assert "other" in checks

    def test_duplicate_name_replaces(self):
        register("dummy", _dummy_check)
        register("dummy", _other_check)
        checks = all_checks()
        assert len(checks) == 1
        assert checks["dummy"] is _other_check

    def test_all_checks_returns_copy(self):
        register("dummy", _dummy_check)
        checks = all_checks()
        checks["injected"] = _other_check
        assert "injected" not in all_checks()
