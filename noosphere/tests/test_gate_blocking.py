"""Tests for gate blocking and the @gated decorator."""

from __future__ import annotations

import uuid

import pytest

from noosphere.models import (
    Actor,
    AuthorAttestation,
    CheckResult,
    RigorSubmission,
)
from noosphere.rigor_gate.checks import _CHECKS, register
from noosphere.rigor_gate.decorator import configure_store, gated
from noosphere.rigor_gate.gate import Gate, GateBlocked
from noosphere.store import Store


@pytest.fixture()
def store():
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(_CHECKS)
    _CHECKS.clear()
    yield
    _CHECKS.clear()
    _CHECKS.update(saved)


def _make_submission(**overrides) -> RigorSubmission:
    defaults = dict(
        submission_id=str(uuid.uuid4()),
        kind="conclusion",
        payload_ref="ref-1",
        author=Actor(kind="human", id="u1", display_name="User 1"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="u1",
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )
    defaults.update(overrides)
    return RigorSubmission(**defaults)


def _blocker(sub: RigorSubmission) -> CheckResult:
    return CheckResult(check_name="blocker", pass_=False, detail="blocked")


def _passer(sub: RigorSubmission) -> CheckResult:
    return CheckResult(check_name="passer", pass_=True, detail="ok")


def _condition_check(sub: RigorSubmission) -> CheckResult:
    return CheckResult(
        check_name="cond", pass_=True, detail="CONDITION: needs review"
    )


class TestGateBlocking:
    def test_no_checks_pass(self, store):
        gate = Gate(store)
        sub = _make_submission()
        verdict = gate.submit(sub)
        assert verdict.verdict == "pass"
        assert verdict.conditions == []

    def test_all_pass(self, store):
        register("passer", _passer)
        gate = Gate(store)
        verdict = gate.submit(_make_submission())
        assert verdict.verdict == "pass"

    def test_blocker_causes_fail(self, store):
        register("blocker", _blocker)
        gate = Gate(store)
        verdict = gate.submit(_make_submission())
        assert verdict.verdict == "fail"

    def test_condition_check(self, store):
        register("cond", _condition_check)
        gate = Gate(store)
        verdict = gate.submit(_make_submission())
        assert verdict.verdict == "pass_with_conditions"
        assert "needs review" in verdict.conditions

    def test_blocker_overrides_condition(self, store):
        register("blocker", _blocker)
        register("cond", _condition_check)
        gate = Gate(store)
        verdict = gate.submit(_make_submission())
        assert verdict.verdict == "fail"

    def test_verdict_stored(self, store):
        gate = Gate(store)
        sub = _make_submission()
        verdict = gate.submit(sub)
        assert verdict.ledger_entry_id.startswith("rigor-")


class TestGatedDecorator:
    def test_decorator_raises_on_fail(self, store):
        register("blocker", _blocker)
        configure_store(store)

        @gated(kind="conclusion")
        def handler(content: str) -> str:
            return content

        sub = _make_submission()
        with pytest.raises(GateBlocked) as exc_info:
            handler("test", submission=sub)
        assert exc_info.value.verdict.verdict == "fail"

    def test_decorator_passes_through(self, store):
        register("passer", _passer)
        configure_store(store)

        @gated(kind="conclusion")
        def handler(content: str) -> str:
            return content

        sub = _make_submission()
        result = handler("hello", submission=sub)
        assert result == "hello"

    def test_decorator_no_store_raises_runtime_error(self):
        configure_store(None)

        @gated(kind="conclusion")
        def handler() -> str:
            return "x"

        with pytest.raises(RuntimeError, match="store not configured"):
            handler()
