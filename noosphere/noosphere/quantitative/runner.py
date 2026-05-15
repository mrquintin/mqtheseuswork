"""Run an APPROVED quantitative formalisation end-to-end.

Reads:
    The APPROVED ``QuantitativeFormalisation`` rows produced by prompt 57
    (``noosphere/noosphere/quantitative/formalisation.py``).

Writes:
    One ``QuantitativeTestResult`` row per pass + plot artifacts under
    ``benchmarks/quantitative/<formalisation_id>/<run_stamp>/``.

Cadence:
    The Forecasts scheduler ticks ``run`` on each formalisation's
    ``update_cadence`` (taken from the first metric's
    ``update_cadence`` field). Daily / weekly / monthly only —
    sub-daily is denied and lands in the ``error`` field with
    ``SUBDAILY_DENIED``; trading signals belong to prompt 61.

Idempotency:
    Persistence keys on ``(formalisation_id, run_stamp)``. The default
    ``run_stamp`` uses second-resolution UTC so two near-simultaneous
    runs collide cleanly rather than stacking duplicate rows.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from noosphere.models import (
    DataSourceSpec,
    FormalisationStatus,
    QuantitativeFormalisation,
    QuantitativeRunStatus,
    QuantitativeTestOutput,
    QuantitativeTestResult,
    StatisticalTestKind,
    StatisticalTestSpec,
)
from noosphere.observability import get_logger
from noosphere.quantitative import dispatchers, plots
from noosphere.quantitative.dispatchers import (
    ResolvedDataset,
    UnknownDataSourceError,
)


log = get_logger(__name__)

DEFAULT_ARTIFACTS_ROOT = Path("benchmarks/quantitative")

# Allowed cadences. Sub-daily would push the runner into trading-signal
# territory (prompt 61); the founder picked weekly as the default so
# the scheduler tick interval doesn't itself become a signal.
_ALLOWED_CADENCES: set[str] = {"daily", "weekly", "monthly", "ad-hoc"}
_SUBDAILY_CADENCES: set[str] = {
    "minutely",
    "hourly",
    "intraday",
    "tick",
    "second",
    "sub-daily",
    "subdaily",
    "realtime",
    "real-time",
}


def _utc_run_stamp() -> str:
    """Second-resolution UTC slug — collision-resistant for idempotency."""

    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (text or "").strip()) or "metric"


def _normalise_cadence(value: str) -> str:
    text = (value or "").strip().lower()
    return text


def _formalisation_cadence(formalisation: QuantitativeFormalisation) -> str:
    """Cadence the scheduler should tick this formalisation on.

    The first metric's ``update_cadence`` is the canonical source: it
    is the slowest moving piece of the spec (the data refresh rate). If
    no metric is present the default is weekly.
    """

    if not formalisation.metrics:
        return "weekly"
    return _normalise_cadence(formalisation.metrics[0].update_cadence) or "weekly"


def _is_subdaily(cadence: str) -> bool:
    return _normalise_cadence(cadence) in _SUBDAILY_CADENCES


def _is_approved(formalisation: QuantitativeFormalisation) -> bool:
    status = formalisation.status
    if hasattr(status, "value"):
        status = status.value
    return status == FormalisationStatus.APPROVED.value


def _principle_id(formalisation: QuantitativeFormalisation) -> str:
    return getattr(formalisation, "principle_id", "") or ""


@dataclass
class _MetricSnapshot:
    name: str
    value: float | int | None
    as_of: str


def _compute_metric(
    spec: Any, datasets: dict[str, "ResolvedDataset"]
) -> _MetricSnapshot:
    """Compute one metric.

    The metric's ``source_dataset`` keys into the resolved datasets
    dict by name. The mean of any numeric column whose header matches
    ``spec.name`` (case-insensitive) is the v1 contract — formalisations
    that need a non-mean reduction must lift the metric to a derived
    column in the upstream source.
    """

    ds = datasets.get(spec.source_dataset)
    if ds is None or ds.row_count == 0:
        return _MetricSnapshot(name=spec.name, value=None, as_of=_utc_run_stamp())

    frame = ds.dataframe
    # Match by exact name first, then case-insensitive.
    column = None
    if spec.name in frame.columns:
        column = spec.name
    else:
        lower = {c.lower(): c for c in frame.columns}
        column = lower.get(spec.name.lower())
    if column is None:
        return _MetricSnapshot(name=spec.name, value=None, as_of=_utc_run_stamp())
    try:
        value = float(frame[column].dropna().astype(float).mean())
    except Exception:
        return _MetricSnapshot(name=spec.name, value=None, as_of=_utc_run_stamp())
    if value != value:  # NaN guard.
        return _MetricSnapshot(name=spec.name, value=None, as_of=_utc_run_stamp())
    return _MetricSnapshot(name=spec.name, value=value, as_of=_utc_run_stamp())


def _check_thresholds(
    formalisation: QuantitativeFormalisation,
    outputs: list[QuantitativeTestOutput],
) -> list[str]:
    """Return the human-readable thresholds whose condition is satisfied.

    The drafter writes thresholds as free-text strings ("p < 0.01 →
    promote", "p > 0.20 → retire"); without parsing the prose we
    conservatively flag any threshold whose first numeric p-value
    bound is crossed by any test's observed p-value. The founder still
    confirms the implied update — the runner only recommends.
    """

    crossings: list[str] = []
    pattern = re.compile(r"p\s*([<>])\s*(0?\.\d+)")
    for threshold in formalisation.decision_thresholds:
        match = pattern.search(threshold)
        if not match:
            continue
        op, bound_s = match.group(1), match.group(2)
        try:
            bound = float(bound_s)
        except ValueError:
            continue
        for out in outputs:
            if out.p_value is None:
                continue
            crossed = (op == "<" and out.p_value < bound) or (
                op == ">" and out.p_value > bound
            )
            if crossed:
                crossings.append(threshold)
                break
    return crossings


def _summarise(
    formalisation: QuantitativeFormalisation,
    metrics: list[_MetricSnapshot],
    outputs: list[QuantitativeTestOutput],
    crossings: list[str],
) -> str:
    """Build a one-paragraph natural-language summary.

    Deliberately deterministic — no LLM call so the runner can ship
    without an API key. The shape mirrors how a research note would
    open: principle id, sample size, headline p-value, then any
    threshold crossing.
    """

    if not outputs:
        return "Runner produced no test outputs."
    headline = outputs[0]
    metric_summary = ", ".join(
        f"{m.name}={m.value:.4f}" if isinstance(m.value, float) else f"{m.name}=n/a"
        for m in metrics
    ) or "no metrics computed"
    parts = [
        f"Principle {_principle_id(formalisation) or formalisation.id}:",
        f"{headline.test_kind} produced statistic={headline.statistic}",
    ]
    if headline.p_value is not None:
        parts.append(f"at p={headline.p_value:.4f}")
    if headline.sample_size is not None:
        parts.append(f"on n={headline.sample_size}")
    parts.append(f"({metric_summary}).")
    if crossings:
        parts.append(
            "Decision thresholds crossed — queueing for founder review: "
            + "; ".join(crossings)
        )
    else:
        parts.append("No decision thresholds crossed.")
    return " ".join(parts)


class QuantitativeRunner:
    """Run an APPROVED formalisation and persist a ``QuantitativeTestResult``.

    The runner is sync at the dataset / fit level (SciPy and pandas are
    blocking) but exposes an async ``run`` so the Forecasts scheduler
    can compose it the same way it composes other sub-loops; a thread
    executor isolates the heavy work.
    """

    def __init__(
        self,
        store: Any,
        *,
        artifacts_root: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.store = store
        self.artifacts_root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
        self.data_dir = data_dir

    async def run(
        self,
        formalisation_id: str,
        *,
        run_stamp: str | None = None,
    ) -> QuantitativeTestResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_sync(formalisation_id, run_stamp=run_stamp),
        )

    def run_sync(
        self,
        formalisation_id: str,
        *,
        run_stamp: str | None = None,
    ) -> QuantitativeTestResult:
        stamp = run_stamp or _utc_run_stamp()
        formalisation = self.store.get_quantitative_formalisation(formalisation_id)
        if formalisation is None:
            result = QuantitativeTestResult(
                formalisation_id=formalisation_id,
                run_stamp=stamp,
                status=QuantitativeRunStatus.FAILED,
                error="UNKNOWN_FORMALISATION",
                decision_summary="No formalisation row found for id.",
            )
            self.store.upsert_quantitative_test_result(result)
            return result

        if not _is_approved(formalisation):
            result = QuantitativeTestResult(
                formalisation_id=formalisation_id,
                principle_id=_principle_id(formalisation),
                run_stamp=stamp,
                status=QuantitativeRunStatus.FAILED,
                error="NOT_APPROVED",
                decision_summary="Formalisation is not APPROVED; runner declined.",
            )
            self.store.upsert_quantitative_test_result(result)
            return result

        cadence = _formalisation_cadence(formalisation)
        if _is_subdaily(cadence):
            result = QuantitativeTestResult(
                formalisation_id=formalisation_id,
                principle_id=_principle_id(formalisation),
                run_stamp=stamp,
                status=QuantitativeRunStatus.FAILED,
                error="SUBDAILY_DENIED",
                decision_summary=(
                    f"Cadence '{cadence}' is sub-daily; quantitative runner "
                    "does not run sub-daily tests (trading signals belong to "
                    "prompt 61)."
                ),
            )
            self.store.upsert_quantitative_test_result(result)
            return result

        artifacts_dir = self.artifacts_root / formalisation_id / stamp
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Resolve data sources up-front; record per-source failures.
        datasets: dict[str, ResolvedDataset] = {}
        source_errors: list[str] = []
        for source in formalisation.data_sources:
            try:
                resolved = dispatchers.resolve_data_source(
                    source, data_dir=self.data_dir, store=self.store
                )
            except UnknownDataSourceError as exc:
                source_errors.append(
                    f"{source.name}:UNKNOWN_DATA_SOURCE:{exc}"
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive.
                source_errors.append(
                    f"{source.name}:{type(exc).__name__}:{exc}"
                )
                continue
            datasets[source.name] = resolved

        # If every source failed, fail loudly so the operator sees it.
        if formalisation.data_sources and not datasets:
            result = QuantitativeTestResult(
                formalisation_id=formalisation_id,
                principle_id=_principle_id(formalisation),
                run_stamp=stamp,
                status=QuantitativeRunStatus.FAILED,
                error="; ".join(source_errors) or "UNKNOWN_DATA_SOURCE",
                decision_summary="No data sources resolved; runner aborted.",
                artifacts_path=str(artifacts_dir),
            )
            self._dump_artifacts(artifacts_dir, datasets, [], [], result)
            self.store.upsert_quantitative_test_result(result)
            self._log_summary(result)
            return result

        # Compute metrics.
        metrics: list[_MetricSnapshot] = [
            _compute_metric(spec, datasets) for spec in formalisation.metrics
        ]
        metric_values: dict[str, Any] = {
            m.name: {"value": m.value, "as_of": m.as_of} for m in metrics
        }

        # Run tests. Each test picks its primary dataset by
        # (dependent column ∈ frame.columns). If no resolved dataset
        # carries the dependent column we mark that test FAILED but
        # continue with the others.
        outputs: list[QuantitativeTestOutput] = []
        for spec in formalisation.tests:
            frame = self._frame_for_test(spec, datasets)
            if frame is None:
                outputs.append(
                    QuantitativeTestOutput(
                        test_kind=spec.kind.value
                        if hasattr(spec.kind, "value")
                        else str(spec.kind),
                        notes=(
                            f"no resolved dataset contains dependent "
                            f"column '{spec.dependent}'"
                        ),
                        passed_threshold=False,
                    )
                )
                continue
            try:
                output, sidecar = dispatchers.run_test(frame, spec)
            except Exception as exc:
                outputs.append(
                    QuantitativeTestOutput(
                        test_kind=spec.kind.value
                        if hasattr(spec.kind, "value")
                        else str(spec.kind),
                        notes=f"test crashed: {type(exc).__name__}: {exc}",
                        passed_threshold=False,
                    )
                )
                continue
            outputs.append(output)
            self._draw_plot(artifacts_dir, spec, output, sidecar)

        crossings = _check_thresholds(formalisation, outputs)
        summary = _summarise(formalisation, metrics, outputs, crossings)
        status = self._roll_up_status(outputs, source_errors)
        result = QuantitativeTestResult(
            formalisation_id=formalisation_id,
            principle_id=_principle_id(formalisation),
            run_stamp=stamp,
            metric_values=metric_values,
            test_outputs=outputs,
            decision_summary=summary,
            artifacts_path=str(artifacts_dir),
            status=status,
            error=("; ".join(source_errors) or None) if source_errors else None,
            threshold_crossings=crossings,
        )
        self._dump_artifacts(artifacts_dir, datasets, metrics, outputs, result)
        self.store.upsert_quantitative_test_result(result)
        if crossings:
            try:
                self._queue_for_founder(result, crossings)
            except Exception as exc:  # pragma: no cover - best-effort.
                log.warning(
                    "quantitative_threshold_queue_failed",
                    formalisation_id=formalisation_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
        self._log_summary(result)
        return result

    def _frame_for_test(
        self,
        spec: StatisticalTestSpec,
        datasets: dict[str, ResolvedDataset],
    ) -> Any | None:
        for ds in datasets.values():
            if spec.dependent in ds.dataframe.columns:
                return ds.dataframe
        return None

    def _draw_plot(
        self,
        artifacts_dir: Path,
        spec: StatisticalTestSpec,
        output: QuantitativeTestOutput,
        sidecar: dict[str, Any],
    ) -> None:
        if not sidecar:
            return
        kind = (
            spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind)
        )
        stem = artifacts_dir / f"{_slug(spec.dependent)}_{kind}"
        if kind == StatisticalTestKind.REGRESSION.value and "fitted" in sidecar:
            plots.residual_plot(
                sidecar["fitted"],
                sidecar["resid"],
                out_path=stem.with_suffix(".png"),
                title=f"Residuals · {spec.dependent}",
            )
        elif kind == StatisticalTestKind.KS_TEST.value and "a" in sidecar:
            plots.distribution_overlay(
                sidecar["a"],
                sidecar["b"],
                out_path=stem.with_suffix(".png"),
                title=f"KS overlay · {spec.dependent}",
            )
        elif (
            kind == StatisticalTestKind.CLASSIFICATION.value
            and "predicted" in sidecar
        ):
            plots.calibration_plot(
                sidecar["predicted"],
                sidecar["actual"],
                out_path=stem.with_suffix(".png"),
                title=f"Calibration · {spec.dependent}",
            )

    def _dump_artifacts(
        self,
        artifacts_dir: Path,
        datasets: dict[str, ResolvedDataset],
        metrics: list[_MetricSnapshot],
        outputs: list[QuantitativeTestOutput],
        result: QuantitativeTestResult,
    ) -> None:
        try:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "result.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            (artifacts_dir / "sources.json").write_text(
                json.dumps(
                    {name: ds.row_count for name, ds in datasets.items()},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - best-effort.
            log.warning(
                "quantitative_artifacts_dump_failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _roll_up_status(
        self,
        outputs: list[QuantitativeTestOutput],
        source_errors: list[str],
    ) -> QuantitativeRunStatus:
        if not outputs and source_errors:
            return QuantitativeRunStatus.FAILED
        any_pass = any(o.passed_threshold for o in outputs if o.passed_threshold is not None)
        any_bad = any(
            (o.statistic is None and o.p_value is None and "missing" in (o.notes or ""))
            for o in outputs
        )
        if source_errors or any_bad:
            return QuantitativeRunStatus.PARTIAL
        if any_pass or outputs:
            return QuantitativeRunStatus.RAN
        return QuantitativeRunStatus.FAILED

    def _queue_for_founder(
        self,
        result: QuantitativeTestResult,
        crossings: list[str],
    ) -> None:
        """Best-effort triage-queue write.

        The same founder-confirmable queue pattern as elsewhere — the
        runner recommends and the founder accepts. The queue table is
        operator-side; in noosphere-only sqlite deployments the
        underlying table may not exist, in which case the structured
        log line is the durable record.
        """

        from sqlalchemy import text as sa_text

        payload = {
            "formalisation_id": result.formalisation_id,
            "principle_id": result.principle_id,
            "run_stamp": result.run_stamp,
            "crossings": crossings,
            "decision_summary": result.decision_summary,
        }
        log.info(
            "quantitative_threshold_crossed",
            **payload,
        )
        try:
            insp_tables = self.store.engine.dialect.get_table_names(
                self.store.engine.connect()
            )
        except Exception:
            insp_tables = []
        if "PrincipleConvictionUpdateQueue" not in insp_tables:
            return
        with self.store.engine.begin() as conn:
            conn.execute(
                sa_text(
                    'INSERT INTO "PrincipleConvictionUpdateQueue" '
                    '("principleId", "formalisationId", "runStamp", '
                    '"crossingsJson", "summary", "createdAt") '
                    "VALUES (:p, :f, :r, :c, :s, CURRENT_TIMESTAMP)"
                ),
                {
                    "p": result.principle_id,
                    "f": result.formalisation_id,
                    "r": result.run_stamp,
                    "c": json.dumps(crossings),
                    "s": result.decision_summary,
                },
            )

    def _log_summary(self, result: QuantitativeTestResult) -> None:
        log.info(
            "quantitative_run_completed",
            formalisation_id=result.formalisation_id,
            principle_id=result.principle_id,
            run_stamp=result.run_stamp,
            status=(
                result.status.value
                if hasattr(result.status, "value")
                else result.status
            ),
            test_count=len(result.test_outputs),
            crossings=result.threshold_crossings,
            headline_p=(
                result.test_outputs[0].p_value if result.test_outputs else None
            ),
        )


def cadence_to_seconds(cadence: str) -> int:
    """Translate a cadence string to a scheduler tick interval.

    Returns ``0`` for unknown / sub-daily cadences so the scheduler
    treats the formalisation as paused rather than spinning.
    """

    text = _normalise_cadence(cadence)
    if text in _SUBDAILY_CADENCES or text not in _ALLOWED_CADENCES:
        return 0
    if text == "daily":
        return 24 * 60 * 60
    if text == "weekly":
        return 7 * 24 * 60 * 60
    if text == "monthly":
        return 30 * 24 * 60 * 60
    # ad-hoc: never auto-tick.
    return 0
