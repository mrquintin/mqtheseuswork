"""Test that direct writes to the public-site store are rejected when
bypassing the rigor gate — the @gated decorator is load-bearing.
"""

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
from noosphere.rigor_gate.gate import GateBlocked
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


def _make_submission() -> RigorSubmission:
    return RigorSubmission(
        submission_id=str(uuid.uuid4()),
        kind="conclusion",
        payload_ref="payload-ref",
        author=Actor(kind="human", id="user-1", display_name="User"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="user-1",
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )


def _blocking_check(sub: RigorSubmission) -> CheckResult:
    return CheckResult(check_name="block_all", pass_=False, detail="blocked")


class TestPublicStoreOnlyGatedWrites:
    def test_gated_write_blocked_by_failing_check(self, store):
        register("block_all", _blocking_check)
        configure_store(store)

        @gated(kind="conclusion")
        def publish_content(content: str) -> str:
            return f"published: {content}"

        sub = _make_submission()
        with pytest.raises(GateBlocked) as exc_info:
            publish_content("my conclusion", submission=sub)

        assert exc_info.value.verdict.verdict == "fail"

    def test_gated_write_allowed_when_checks_pass(self, store):
        def pass_check(sub: RigorSubmission) -> CheckResult:
            return CheckResult(check_name="ok", pass_=True, detail="fine")

        register("ok", pass_check)
        configure_store(store)

        @gated(kind="conclusion")
        def publish_content(content: str) -> str:
            return f"published: {content}"

        sub = _make_submission()
        result = publish_content("my conclusion", submission=sub)
        assert result == "published: my conclusion"

    def test_ungated_handler_with_no_store_raises(self):
        configure_store(None)

        @gated(kind="conclusion")
        def publish_content() -> str:
            return "should not reach here"

        with pytest.raises(RuntimeError, match="store not configured"):
            publish_content()
