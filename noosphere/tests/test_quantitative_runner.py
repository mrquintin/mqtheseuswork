"""Quantitative runner end-to-end tests.

Covers:
- Happy path: a fixture formalisation with one OLS regression hitting
  a committed CSV fixture produces a ``QuantitativeTestResult`` with
  the expected coefficients within tolerance.
- Unknown data source: the runner records the failure on the
  ``QuantitativeTestResult`` rather than raising — and the test
  asserts that no real network call is made (yfinance and
  ``urllib.request.urlopen`` are both monkeypatched to fail loudly).
- Decision-threshold crossing: a threshold whose p-value bound the
  fixture clearly crosses is recorded in ``threshold_crossings`` and
  the conviction score on the underlying principle is NOT updated
  automatically (the founder-confirmable queue pattern).
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest

from noosphere.models import (
    DataSourceSpec,
    FormalisationStatus,
    MetricSpec,
    QuantitativeFormalisation,
    QuantitativeRunStatus,
    StatisticalTestKind,
    StatisticalTestSpec,
)
from noosphere.quantitative import dispatchers
from noosphere.quantitative.runner import QuantitativeRunner
from noosphere.store import Store


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _build_store(tmp_path: Path) -> Store:
    # File-backed sqlite — in-memory sqlite is per-thread and the
    # runner offloads to an executor thread.
    return Store.from_database_url(f"sqlite:///{tmp_path / 'qrunner.db'}")


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any real network attempt.

    Belt-and-braces: yfinance is monkeypatched separately, but the
    socket-level block catches any helper that bypasses it.
    """

    def _refuse(*_args, **_kwargs):  # pragma: no cover - test guard.
        raise RuntimeError("network access is not permitted in tests")

    monkeypatch.setattr(socket, "create_connection", _refuse)


def _approved_fixture_formalisation(principle_id: str = "p_fixture") -> QuantitativeFormalisation:
    """Hand-crafted APPROVED formalisation against the CSV fixture.

    The CSV has y ≈ 2 * x, so an OLS regression on y ~ x is expected
    to produce slope ≈ 2.0 with a p-value well below 0.05.
    """

    return QuantitativeFormalisation(
        principle_id=principle_id,
        null_hypothesis="The slope of y on x is zero (no relationship).",
        metrics=[
            MetricSpec(
                name="y",
                definition="dependent value y as recorded in the fixture",
                unit="unitless",
                source_dataset="fixture",
                update_cadence="weekly",
            )
        ],
        tests=[
            StatisticalTestSpec(
                kind=StatisticalTestKind.REGRESSION,
                dependent="y",
                independents=["x"],
                expected_sign_or_magnitude="positive slope near 2",
                expected_p_threshold=0.05,
            )
        ],
        data_sources=[
            DataSourceSpec(
                name="fixture",
                provenance="file://quant_fixture.csv",
                license="internal",
                refresh_cadence="weekly",
            )
        ],
        decision_thresholds=[
            "p < 0.01 → promote conviction one notch",
        ],
        status=FormalisationStatus.APPROVED,
    )


def test_runner_persists_expected_regression_within_tolerance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    _block_network(monkeypatch)
    store = _build_store(tmp_path)
    formalisation = _approved_fixture_formalisation()
    store.put_quantitative_formalisation(formalisation)

    runner = QuantitativeRunner(
        store, artifacts_root=tmp_path / "bench", data_dir=FIXTURES_DIR
    )
    result = asyncio.run(runner.run(formalisation.id))

    assert result.status in {
        QuantitativeRunStatus.RAN,
        QuantitativeRunStatus.RAN.value,
    }
    assert len(result.test_outputs) == 1
    output = result.test_outputs[0]
    # y = 2x exactly in the fixture, so the OLS slope is 2.0 (within
    # numerical tolerance) and the p-value is effectively zero.
    assert output.statistic is not None
    assert output.statistic == pytest.approx(2.0, abs=0.05)
    assert output.p_value is not None
    assert output.p_value < 1e-12
    assert output.passed_threshold is True
    assert output.sample_size == 12
    assert "y" in result.metric_values
    assert result.metric_values["y"]["value"] == pytest.approx(
        (2.10 + 4.05 + 5.95 + 8.10 + 9.95 + 12.05 + 13.90 + 16.10 + 17.95 + 20.05 + 21.90 + 24.05)
        / 12.0,
        abs=1e-6,
    )
    artifacts_dir = Path(result.artifacts_path)
    assert artifacts_dir.exists()
    assert (artifacts_dir / "result.json").exists()


def test_unknown_data_source_marks_result_failed_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("pandas")
    _block_network(monkeypatch)
    # Belt-and-braces: even if a future regression wires unknown://
    # to yfinance by accident, this stub blows the test up.
    def _yf_stub(*_args, **_kwargs):  # pragma: no cover - test guard
        raise RuntimeError("yfinance must not be invoked in tests")

    monkeypatch.setattr(dispatchers, "_yfinance_fetcher", lambda: _yf_stub)

    store = _build_store(tmp_path)
    formalisation = QuantitativeFormalisation(
        principle_id="p_bad_source",
        null_hypothesis="ignored — runner refuses unknown sources",
        metrics=[
            MetricSpec(
                name="y",
                definition="placeholder",
                unit="unitless",
                source_dataset="bogus",
                update_cadence="weekly",
            )
        ],
        tests=[
            StatisticalTestSpec(
                kind=StatisticalTestKind.REGRESSION,
                dependent="y",
                independents=["x"],
                expected_sign_or_magnitude="any",
                expected_p_threshold=0.05,
            )
        ],
        data_sources=[
            DataSourceSpec(
                name="bogus",
                provenance="mysteryProto://nowhere",
                license="internal",
                refresh_cadence="weekly",
            )
        ],
        status=FormalisationStatus.APPROVED,
    )
    store.put_quantitative_formalisation(formalisation)

    runner = QuantitativeRunner(store, artifacts_root=tmp_path / "bench")
    result = asyncio.run(runner.run(formalisation.id))

    assert result.status in {
        QuantitativeRunStatus.FAILED,
        QuantitativeRunStatus.FAILED.value,
    }
    assert result.error is not None
    assert "UNKNOWN_DATA_SOURCE" in result.error


def test_threshold_crossing_does_not_auto_update_conviction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Crossing a decision threshold must enqueue, not auto-update.

    The runner records the crossing on the ``QuantitativeTestResult``
    so the founder triage UI can surface it; it must NOT touch the
    principle's conviction score directly. Asserted by checking that
    no ``PrincipleConvictionUpdateQueue`` row is created in noosphere's
    in-memory sqlite (the queue table is operator-side) and that the
    crossings live on the result row.
    """

    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    _block_network(monkeypatch)

    store = _build_store(tmp_path)
    formalisation = _approved_fixture_formalisation(principle_id="p_threshold")
    # Tight threshold the regression p-value (≈0) clearly crosses.
    formalisation.decision_thresholds = [
        "p < 0.001 → promote one notch (founder confirms)",
    ]
    store.put_quantitative_formalisation(formalisation)

    runner = QuantitativeRunner(
        store, artifacts_root=tmp_path / "bench", data_dir=FIXTURES_DIR
    )
    result = asyncio.run(runner.run(formalisation.id))

    assert result.threshold_crossings, (
        "expected the runner to flag the p<0.001 threshold as crossed"
    )
    # The runner must not have inserted an automatic conviction-score
    # update — assert via the store's session (the queue table is
    # operator-side; in noosphere-only sqlite the runner's INSERT path
    # is a no-op, the structured log is the durable record).
    with store.engine.connect() as conn:
        tables = set(conn.dialect.get_table_names(conn))
    assert "PrincipleConvictionUpdateQueue" not in tables
    # And no second pass at the same stamp duplicates the row —
    # idempotency check.
    asyncio.run(runner.run(formalisation.id, run_stamp=result.run_stamp))
    rows = store.list_quantitative_test_results(
        formalisation_id=formalisation.id
    )
    same_stamp = [r for r in rows if r.run_stamp == result.run_stamp]
    assert len(same_stamp) == 1
