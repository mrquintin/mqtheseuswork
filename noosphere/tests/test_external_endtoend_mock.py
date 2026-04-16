"""End-to-end test: MockAdapter through BatteryRunner with a toy method."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from noosphere.models import (
    CorpusBundle,
    ExternalItem,
    LicenseTag,
    MethodRef,
    Outcome,
    OutcomeKind,
)
from noosphere.external_battery.canonical import ClaimOrPrediction
from noosphere.external_battery.run import BatteryRunner
from mock_adapter import MockAdapter


def _toy_method(canonical: ClaimOrPrediction):
    """Toy method that returns a plausible prediction for any item."""
    if canonical.outcome_type == OutcomeKind.BINARY:
        return {"prediction": 0.75}
    if canonical.outcome_type == OutcomeKind.INTERVAL:
        return {"prediction": {"point": 22.0, "lower": 20.0, "upper": 25.0}}
    if canonical.outcome_type == OutcomeKind.PREFERENCE:
        return {"prediction": "team_a"}
    return None


class TestEndToEndMock:
    def test_battery_produces_valid_result(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            cache_dir=tmp_path / "cache",
        )

        assert len(results) == 1
        result = results[0]

        assert result.corpus_name == "mock"
        assert result.method_ref == method_ref
        assert result.run_id.startswith("bat-")
        assert len(result.per_item_results) == 3

    def test_metrics_are_populated(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            cache_dir=tmp_path / "cache",
        )
        result = results[0]

        assert result.metrics.brier >= 0.0
        assert result.metrics.coverage >= 0.0

    def test_report_files_created(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        report_root = tmp_path / "reports"
        runner = BatteryRunner(report_root=report_root)

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            cache_dir=tmp_path / "cache",
        )
        result = results[0]

        md_files = list(report_root.rglob("*.md"))
        json_files = list(report_root.rglob("*.json"))

        assert len(md_files) >= 1, "Expected at least one markdown report"
        assert len(json_files) >= 1, "Expected at least one JSON report"

        md_content = md_files[0].read_text()
        assert "# External Battery: mock" in md_content
        assert "Brier" in md_content
        assert "Log Loss" in md_content

        json_content = json.loads(json_files[0].read_text())
        assert json_content["run_id"] == result.run_id
        assert json_content["corpus_name"] == "mock"

    def test_per_item_has_correlation_ids(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            cache_dir=tmp_path / "cache",
        )
        result = results[0]

        for item_result in result.per_item_results:
            assert item_result["correlation_id"].startswith("cf-ext-mock-")
            assert "cut_id" in item_result

    def test_failure_classification_present(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            cache_dir=tmp_path / "cache",
        )
        result = results[0]

        for item_result in result.per_item_results:
            assert "failure_kind" in item_result

    def test_sample_size_limits_items(self, tmp_path: Path):
        adapter = MockAdapter()
        method_ref = MethodRef(name="toy_method", version="0.1.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, method_ref)],
            sample_size=1,
            cache_dir=tmp_path / "cache",
        )
        result = results[0]
        assert len(result.per_item_results) == 1

    def test_multiple_methods(self, tmp_path: Path):
        adapter = MockAdapter()
        ref_a = MethodRef(name="method_a", version="0.1.0")
        ref_b = MethodRef(name="method_b", version="0.2.0")
        runner = BatteryRunner(report_root=tmp_path / "reports")

        results = runner.run(
            adapter,
            methods=[(_toy_method, ref_a), (_toy_method, ref_b)],
            cache_dir=tmp_path / "cache",
        )

        assert len(results) == 2
        assert results[0].method_ref == ref_a
        assert results[1].method_ref == ref_b


class TestMockAdapterProtocol:
    def test_mock_satisfies_protocol(self):
        from noosphere.external_battery.adapters import CorpusAdapter
        adapter = MockAdapter()
        assert isinstance(adapter, CorpusAdapter)
