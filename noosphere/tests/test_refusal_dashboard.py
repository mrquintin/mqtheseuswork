"""Tests for the refusal dashboard data accessors."""

from __future__ import annotations

import uuid

import pytest

from noosphere.models import (
    Actor,
    AuthorAttestation,
    CheckResult,
    FounderOverride,
    RigorSubmission,
    RigorVerdict,
)
from noosphere.rigor_gate.refusal_dashboard import (
    DashboardData,
    monthly_stats,
    overrides_for_display,
)
from noosphere.store import Store


@pytest.fixture()
def store():
    return Store.from_database_url("sqlite:///:memory:")


def _make_verdict(
    verdict_str: str = "pass",
    checks: list[CheckResult] | None = None,
    conditions: list[str] | None = None,
) -> RigorVerdict:
    return RigorVerdict(
        verdict=verdict_str,
        checks_run=checks or [],
        conditions=conditions or [],
        reviewed_by=[Actor(kind="human", id="r1", display_name="Reviewer")],
        ledger_entry_id=f"rigor-{uuid.uuid4()}",
    )


def _make_submission(submission_id: str | None = None) -> RigorSubmission:
    return RigorSubmission(
        submission_id=submission_id or str(uuid.uuid4()),
        kind="conclusion",
        payload_ref="ref",
        author=Actor(kind="human", id="a1", display_name="Author"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="a1", conflict_disclosures=[], acknowledgments=[]
        ),
    )


class TestMonthlyStats:
    def test_empty_store(self, store):
        data = monthly_stats(store, "2026-04")
        assert isinstance(data, DashboardData)
        assert data.total == 0
        assert data.passed == 0
        assert data.failed == 0
        assert data.pass_with_conditions == 0
        assert data.top_failure_categories == {}

    def test_counts_match_store(self, store):
        store.insert_rigor_verdict(_make_verdict("pass"))
        store.insert_rigor_verdict(_make_verdict("pass"))
        store.insert_rigor_verdict(
            _make_verdict(
                "fail",
                checks=[
                    CheckResult(check_name="chk_a", pass_=False, detail="bad"),
                ],
            )
        )
        store.insert_rigor_verdict(
            _make_verdict("pass_with_conditions", conditions=["review needed"])
        )

        data = monthly_stats(store, "2026-04")
        assert data.total == 4
        assert data.passed == 2
        assert data.failed == 1
        assert data.pass_with_conditions == 1

    def test_failure_categories(self, store):
        store.insert_rigor_verdict(
            _make_verdict(
                "fail",
                checks=[
                    CheckResult(check_name="coherence", pass_=False, detail="low"),
                    CheckResult(check_name="citation", pass_=False, detail="missing"),
                ],
            )
        )
        store.insert_rigor_verdict(
            _make_verdict(
                "fail",
                checks=[
                    CheckResult(check_name="coherence", pass_=False, detail="low"),
                ],
            )
        )
        data = monthly_stats(store, "2026-04")
        assert data.top_failure_categories["coherence"] == 2
        assert data.top_failure_categories["citation"] == 1


class TestOverridesForDisplay:
    def test_empty(self, store):
        assert overrides_for_display(store) == []

    def test_returns_stored_overrides(self, store):
        ov = FounderOverride(
            override_id="ov-1",
            submission_id="sub-1",
            founder_id="founder-x",
            overridden_checks=["c1"],
            justification="urgent",
            ledger_entry_id="entry-1",
        )
        store.insert_founder_override(ov)
        result = overrides_for_display(store)
        assert len(result) == 1
        assert result[0].override_id == "ov-1"
        assert result[0].founder_id == "founder-x"

    def test_multiple_overrides(self, store):
        for i in range(3):
            store.insert_founder_override(
                FounderOverride(
                    override_id=f"ov-{i}",
                    submission_id=f"sub-{i}",
                    founder_id="founder-y",
                    overridden_checks=["c"],
                    justification=f"reason {i}",
                    ledger_entry_id=f"entry-{i}",
                )
            )
        result = overrides_for_display(store)
        assert len(result) == 3
