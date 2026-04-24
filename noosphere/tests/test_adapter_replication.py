"""Tests for the Replication adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from noosphere.external_battery.adapters import CorpusAdapter, SnapshotMissingError
from noosphere.external_battery.adapters.replication import ReplicationAdapter
from noosphere.models import OutcomeKind

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "adapters" / "replication"


@pytest.fixture
def adapter():
    return ReplicationAdapter(snapshot_dir=FIXTURE_DIR)


@pytest.fixture
def bundle(adapter, tmp_path):
    return adapter.fetch(tmp_path)


class TestReplicationAdapter:
    def test_implements_protocol(self, adapter):
        assert isinstance(adapter, CorpusAdapter)

    def test_fetch_deterministic(self, adapter, tmp_path):
        b1 = adapter.fetch(tmp_path)
        b2 = adapter.fetch(tmp_path)
        assert b1.content_hash == b2.content_hash

    def test_fetch_missing_snapshot_raises(self, tmp_path):
        adapter = ReplicationAdapter(snapshot_dir=tmp_path / "nonexistent")
        with pytest.raises(SnapshotMissingError):
            adapter.fetch(tmp_path)

    def test_iter_items_count(self, adapter, bundle):
        items = list(adapter.iter_items(bundle))
        assert len(items) == 5

    def test_iter_items_fields(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            assert item.question_text
            assert item.as_of is not None
            assert item.source == "replication"
            assert item.outcome_type == OutcomeKind.INTERVAL

    def test_iter_items_all_interval(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            assert item.outcome_type == OutcomeKind.INTERVAL

    def test_resolve_returns_outcome(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            assert outcome.resolution_source

    def test_resolve_sources_are_projects(self, adapter, bundle):
        sources = set()
        for item in adapter.iter_items(bundle):
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            sources.add(outcome.resolution_source)
        assert "Reproducibility Project: Psychology" in sources
        assert "ManyLabs 2" in sources

    def test_resolve_interval_values(self, adapter, bundle):
        for item in adapter.iter_items(bundle):
            outcome = adapter.resolve(item, bundle)
            assert outcome is not None
            assert outcome.kind == OutcomeKind.INTERVAL
            assert isinstance(outcome.value, float)
