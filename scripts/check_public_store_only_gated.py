#!/usr/bin/env python3
"""Integration test: direct write to the public-site store must be rejected
when it bypasses the rigor gate.

The decorator + Gate form the only sanctioned write path. This script verifies
that calling a publication handler without the gate raises GateBlocked.
"""

from __future__ import annotations

import sys
import uuid

from noosphere.models import Actor, AuthorAttestation, CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register
from noosphere.rigor_gate.decorator import configure_store, gated
from noosphere.rigor_gate.gate import GateBlocked
from noosphere.store import Store


def _make_submission() -> RigorSubmission:
    return RigorSubmission(
        submission_id=str(uuid.uuid4()),
        kind="conclusion",
        payload_ref="test-payload",
        author=Actor(kind="human", id="test-user", display_name="Test"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="test-user",
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )


def _blocker_check(submission: RigorSubmission) -> CheckResult:
    return CheckResult(
        check_name="always_block",
        pass_=False,
        detail="Integration test blocker",
    )


def main() -> int:
    store = Store.from_database_url("sqlite:///:memory:")
    configure_store(store)

    register("always_block", _blocker_check)

    @gated(kind="conclusion")
    def publish_to_public_site(content: str) -> str:
        return f"published: {content}"

    sub = _make_submission()
    try:
        publish_to_public_site("test", submission=sub)
        print("FAIL: write was not blocked — gate bypass detected")
        return 1
    except GateBlocked:
        print("OK: direct write correctly blocked by the rigor gate")
        return 0
    finally:
        from noosphere.rigor_gate.checks import _CHECKS
        _CHECKS.pop("always_block", None)


if __name__ == "__main__":
    sys.exit(main())
