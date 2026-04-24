"""Tests for ExternalItem canonicalization round-trips across all OutcomeKind shapes."""

from datetime import datetime, timezone

from noosphere.models import ExternalItem, OutcomeKind
from noosphere.external_battery.canonical import (
    CanonicalKind,
    canonicalize,
    decanonicalize,
)


def _make_item(outcome_type: OutcomeKind, source_id: str = "t1") -> ExternalItem:
    return ExternalItem(
        source="test",
        source_id=source_id,
        question_text="Test question?",
        as_of=datetime(2025, 6, 1, tzinfo=timezone.utc),
        resolved_at=None,
        outcome_type=outcome_type,
        metadata={"tag": "unit_test"},
    )


class TestCanonicalizeBinary:
    def test_binary_becomes_prediction(self):
        item = _make_item(OutcomeKind.BINARY)
        cp = canonicalize(item)
        assert cp.kind == CanonicalKind.PREDICTION
        assert cp.outcome_type == OutcomeKind.BINARY
        assert cp.canonical_id == "test:t1"

    def test_binary_round_trip(self):
        item = _make_item(OutcomeKind.BINARY)
        cp = canonicalize(item)
        restored = decanonicalize(cp)
        assert restored.source == item.source
        assert restored.source_id == item.source_id
        assert restored.question_text == item.question_text
        assert restored.as_of == item.as_of
        assert restored.outcome_type == item.outcome_type
        assert restored.metadata == item.metadata


class TestCanonicalizeInterval:
    def test_interval_becomes_prediction(self):
        item = _make_item(OutcomeKind.INTERVAL, "t2")
        cp = canonicalize(item)
        assert cp.kind == CanonicalKind.PREDICTION
        assert cp.outcome_type == OutcomeKind.INTERVAL
        assert cp.canonical_id == "test:t2"

    def test_interval_round_trip(self):
        item = _make_item(OutcomeKind.INTERVAL, "t2")
        cp = canonicalize(item)
        restored = decanonicalize(cp)
        assert restored.source == item.source
        assert restored.source_id == item.source_id
        assert restored.outcome_type == item.outcome_type


class TestCanonicalizePreference:
    def test_preference_becomes_claim(self):
        item = _make_item(OutcomeKind.PREFERENCE, "t3")
        cp = canonicalize(item)
        assert cp.kind == CanonicalKind.CLAIM
        assert cp.outcome_type == OutcomeKind.PREFERENCE
        assert cp.canonical_id == "test:t3"

    def test_preference_round_trip(self):
        item = _make_item(OutcomeKind.PREFERENCE, "t3")
        cp = canonicalize(item)
        restored = decanonicalize(cp)
        assert restored.source == item.source
        assert restored.source_id == item.source_id
        assert restored.outcome_type == item.outcome_type


class TestCanonicalIdDeterminism:
    def test_same_item_same_id(self):
        item = _make_item(OutcomeKind.BINARY)
        assert canonicalize(item).canonical_id == canonicalize(item).canonical_id

    def test_different_items_different_ids(self):
        a = _make_item(OutcomeKind.BINARY, "a1")
        b = _make_item(OutcomeKind.BINARY, "b1")
        assert canonicalize(a).canonical_id != canonicalize(b).canonical_id


class TestMetadataPreservation:
    def test_metadata_survives_round_trip(self):
        item = ExternalItem(
            source="rich",
            source_id="m1",
            question_text="Complex item",
            as_of=datetime(2025, 3, 15, tzinfo=timezone.utc),
            resolved_at=None,
            outcome_type=OutcomeKind.BINARY,
            metadata={"nested": {"key": "value"}, "list": [1, 2, 3]},
        )
        cp = canonicalize(item)
        restored = decanonicalize(cp)
        assert restored.metadata == item.metadata
