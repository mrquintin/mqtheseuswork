"""Tests for the GJP adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from noosphere.external_battery.adapters import CorpusAdapter, SnapshotMissingError
from noosphere.external_battery.adapters.gjp import GJPAdapter
from noosphere.models import OutcomeKind

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "adapters" / "gjp"


@pytest.fixture
def adapter():
    return GJPAdapter(snapshot_dir=FIXTURE_DIR)


@pytest.fixture
def bundle(adapter, tmp_path):
    return adapter.fetch(tmp_path)


class TestGJPAdapter:
    def test_implements_protocol(self, adapter):
        assert isinstance(adapter, CorpusAdapter)

    def test_fetch_deterministic(self, adapter, tmp_path):
        b1 = adapter.fetch(tmp_path)
        b2 = adapter.fetch(tmp_path)
        assert b1.content_hash == b2.content_hash

    def test_fetch_missing_snapshot_raises(self, tmp_path):
        adapter = GJPAdapter(snapshot_dir=tmp_path / "nonexistent")
        with pytest.raises(SnapshotMissingError):
            adapter.fetch(tmp_path)

    def test_iter_items_count(self, adapter, bundle):
        items = list(adapter.iter_items(bundle))
        assert len(items) == 5

    def test_iter_items_fields(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            assert item.question_text
            assert item.as_of is not None
            assert item.source == "gjp"
            assert item.outcome_type in (OutcomeKind.BINARY, OutcomeKind.INTERVAL)

    def test_iter_items_outcome_types(self, adapter, bundle):
        items = list(adapter.iter_items(bundle))
        binary = [i for i in items if i.outcome_type == OutcomeKind.BINARY]
        interval = [i for i in items if i.outcome_type == OutcomeKind.INTERVAL]
        assert len(binary) == 3
        assert len(interval) == 2

    def test_resolve_returns_outcome(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            assert outcome.resolution_source == "Good Judgment Project"

    def test_resolve_binary_values(self, adapter, bundle):
        items = list(adapter.iter_items(bundle))
        binary_items = [i for i in items if i.outcome_type == OutcomeKind.BINARY]
        for item in binary_items:
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            assert outcome.kind == OutcomeKind.BINARY
            assert isinstance(outcome.value, bool)

    def test_resolve_interval_values(self, adapter, bundle):
        items = list(adapter.iter_items(bundle))
        interval_items = [i for i in items if i.outcome_type == OutcomeKind.INTERVAL]
        for item in interval_items:
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            assert outcome.kind == OutcomeKind.INTERVAL
            assert isinstance(outcome.value, float)
