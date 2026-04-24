"""Tests for founder override creation and ledger recording."""

from __future__ import annotations

import pytest

from noosphere.models import FounderOverride
from noosphere.rigor_gate.override import create_override
from noosphere.store import Store


@pytest.fixture()
def store():
    return Store.from_database_url("sqlite:///:memory:")


class TestCreateOverride:
    def test_returns_founder_override(self, store):
        ov = create_override(
            store,
            submission_id="sub-1",
            founder_id="founder-alice",
            overridden_checks=["check_a", "check_b"],
            justification="Urgent publication needed",
        )
        assert isinstance(ov, FounderOverride)

    def test_has_all_required_fields(self, store):
        ov = create_override(
            store,
            submission_id="sub-2",
            founder_id="founder-bob",
            overridden_checks=["check_x"],
            justification="Reviewed manually",
        )
        assert ov.submission_id == "sub-2"
        assert ov.founder_id == "founder-bob"
        assert ov.overridden_checks == ["check_x"]
        assert ov.justification == "Reviewed manually"
        assert ov.override_id  # non-empty UUID
        assert ov.ledger_entry_id.startswith("override-")

    def test_ledger_entry_id_format_without_ledger(self, store):
        ov = create_override(
            store,
            submission_id="sub-3",
            founder_id="founder-carol",
            overridden_checks=["c1"],
            justification="Testing",
        )
        assert ov.ledger_entry_id.startswith("override-")
        assert ov.override_id in ov.ledger_entry_id

    def test_override_persisted_in_store(self, store):
        ov = create_override(
            store,
            submission_id="sub-4",
            founder_id="founder-dave",
            overridden_checks=["c2"],
            justification="Persisted",
        )
        from sqlmodel import select
        from noosphere.store import StoredFounderOverride

        with store.session() as s:
            row = s.get(StoredFounderOverride, ov.override_id)
        assert row is not None
        restored = FounderOverride.model_validate_json(row.payload_json)
        assert restored.submission_id == "sub-4"
        assert restored.founder_id == "founder-dave"

    def test_multiple_overrides_distinct_ids(self, store):
        ov1 = create_override(
            store,
            submission_id="sub-5",
            founder_id="f1",
            overridden_checks=["c"],
            justification="j1",
        )
        ov2 = create_override(
            store,
            submission_id="sub-5",
            founder_id="f1",
            overridden_checks=["c"],
            justification="j2",
        )
        assert ov1.override_id != ov2.override_id
        assert ov1.ledger_entry_id != ov2.ledger_entry_id
