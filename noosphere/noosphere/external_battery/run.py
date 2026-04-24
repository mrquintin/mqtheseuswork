"""BatteryRunner: orchestrate external-corpus benchmarking for registered methods."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from noosphere.models import (
    BatteryRunResult,
    CalibrationMetrics,
    CorpusBundle,
    CorpusSelector,
    ExternalItem,
    MethodRef,
    MethodType,
    Outcome,
    OutcomeKind,
    ReviewItem,
    TemporalCut,
)
from noosphere.evaluation.metrics import compute_metrics_for_kind
from noosphere.evaluation.outcomes import ResolutionResult, resolve
from noosphere.external_battery.canonical import canonicalize
from noosphere.external_battery.failures import (
    FailureKind,
    classify_failure,
    failure_histogram,
)
from noosphere.external_battery.adapters import CorpusAdapter
from noosphere.methods._decorator import CORRELATION_ID, register_method

logger = logging.getLogger(__name__)

_BRIER_REGRESSION_THRESHOLD = 0.05
_DEFAULT_REPORT_ROOT = Path("docs/eval/external")


class _BatteryInput:
    pass


class _BatteryOutput:
    pass


@register_method(
    name="external_battery_run",
    version="0.1.0",
    method_type=MethodType.CALIBRATION,
    input_schema={},
    output_schema={},
    description="Run external-corpus battery benchmarks against registered methods.",
    rationale="External corpora provide ground-truth calibration data independent of internal ingestion.",
    owner="eval-team",
    nondeterministic=True,
)
def _battery_run_entrypoint(input_data: Any) -> Any:
    """Thin entrypoint so the method registry sees external_battery_run.

    Real orchestration goes through BatteryRunner.run() which calls this
    method's underlying logic.
    """
    return input_data


class BatteryRunner:
    """Orchestrate external-corpus benchmarking."""

    def __init__(
        self,
        *,
        store: Any = None,
        report_root: Path = _DEFAULT_REPORT_ROOT,
    ) -> None:
        self._store = store
        self._report_root = report_root

    def run(
        self,
        adapter: CorpusAdapter,
        methods: list[tuple[Callable, MethodRef]],
        sample_size: Optional[int] = None,
        *,
        cache_dir: Optional[Path] = None,
    ) -> list[BatteryRunResult]:
        """Run the battery for each method against the adapter's corpus.

        Returns one BatteryRunResult per method.
        """
        effective_cache = cache_dir or Path.home() / ".cache" / "noosphere" / "corpora"
        effective_cache.mkdir(parents=True, exist_ok=True)

        bundle = adapter.fetch(effective_cache)

        if self._store is not None:
            try:
                self._store.insert_corpus_bundle(bundle)
            except Exception:
                logger.debug("Bundle already stored or store unavailable", exc_info=True)

        items = list(adapter.iter_items(bundle))
        if sample_size is not None and sample_size < len(items):
            items = items[:sample_size]

        results: list[BatteryRunResult] = []
        for method_fn, method_ref in methods:
            result = self._run_single(adapter, bundle, items, method_fn, method_ref)
            results.append(result)

            self._write_report(adapter.name, result)
            self._check_regression(adapter.name, result)

        return results

    def _run_single(
        self,
        adapter: CorpusAdapter,
        bundle: CorpusBundle,
        items: list[ExternalItem],
        method_fn: Callable,
        method_ref: MethodRef,
    ) -> BatteryRunResult:
        run_id = f"bat-{uuid4().hex[:16]}"
        per_item: list[dict[str, Any]] = []
        resolution_results: list[ResolutionResult] = []
        failure_kinds: list[Optional[FailureKind]] = []
        total_by_kind: dict[OutcomeKind, int] = {}

        for item in items:
            total_by_kind[item.outcome_type] = total_by_kind.get(item.outcome_type, 0) + 1
            correlation_id = f"cf-ext-{adapter.name}-{run_id}-{item.source_id}"

            cut = TemporalCut(
                cut_id=f"ext-{adapter.name}-{item.source_id}",
                as_of=item.as_of,
                corpus_slice=CorpusSelector(as_of=item.as_of),
                embargoed=CorpusSelector(as_of=item.as_of),
                embedding_version_pin="default",
                outcomes=[],
            )

            canonical = canonicalize(item)

            token = CORRELATION_ID.set(correlation_id)
            try:
                method_output = method_fn(canonical)
            except Exception:
                logger.warning(
                    "Method %s failed on item %s:%s",
                    method_ref.name, item.source, item.source_id,
                    exc_info=True,
                )
                method_output = None
            finally:
                CORRELATION_ID.reset(token)

            resolution = adapter.resolve(item, bundle)
            fk = classify_failure(item, method_output, resolution)
            failure_kinds.append(fk)

            item_record: dict[str, Any] = {
                "source_id": item.source_id,
                "correlation_id": correlation_id,
                "cut_id": cut.cut_id,
                "method_output": _safe_serialize(method_output),
                "resolution": resolution.model_dump(mode="json") if resolution else None,
                "failure_kind": fk.value if fk else None,
            }

            if resolution is not None and method_output is not None:
                prediction = _extract_prediction(method_output)
                if prediction is not None:
                    try:
                        rr = resolve(resolution, prediction)
                        resolution_results.append(rr)
                        item_record["score"] = rr.score
                    except Exception:
                        logger.debug(
                            "Could not resolve item %s", item.source_id, exc_info=True
                        )

            per_item.append(item_record)

        metrics = self._aggregate(resolution_results, total_by_kind)
        failures = failure_histogram(failure_kinds)

        result = BatteryRunResult(
            run_id=run_id,
            corpus_name=adapter.name,
            method_ref=method_ref,
            per_item_results=per_item,
            metrics=metrics,
            failures=failures,
        )

        if self._store is not None:
            try:
                self._store.insert_battery_run(result)
            except Exception:
                logger.debug("Could not persist battery run", exc_info=True)

        return result

    def _aggregate(
        self,
        results: list[ResolutionResult],
        total_by_kind: dict[OutcomeKind, int],
    ) -> CalibrationMetrics:
        if not results:
            return CalibrationMetrics(
                brier=0.0, log_loss=0.0, ece=0.0,
                reliability_bins=[], resolution=0.0, coverage=0.0,
            )
        present_kinds = {r.kind for r in results}
        first_kind = min(present_kinds, key=lambda k: k.value)
        return compute_metrics_for_kind(
            results, first_kind, total_by_kind.get(first_kind, len(results))
        )

    def _write_report(self, corpus_name: str, result: BatteryRunResult) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_dir = self._report_root / corpus_name / date_str
        report_dir.mkdir(parents=True, exist_ok=True)

        md_path = report_dir / f"{result.run_id}.md"
        md_path.write_text(_render_markdown(result), encoding="utf-8")

        json_path = report_dir / f"{result.run_id}.json"
        json_path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return md_path

    def _check_regression(self, corpus_name: str, result: BatteryRunResult) -> None:
        if self._store is None:
            return
        try:
            prior = self._store.get_latest_battery_run(corpus_name, result.method_ref)
        except (AttributeError, Exception):
            return
        if prior is None:
            return

        delta = result.metrics.brier - prior.metrics.brier
        if delta > _BRIER_REGRESSION_THRESHOLD:
            ticket = ReviewItem(
                reason=(
                    f"Brier regression on {corpus_name}: "
                    f"{prior.metrics.brier:.4f} -> {result.metrics.brier:.4f} "
                    f"(delta={delta:.4f}, threshold={_BRIER_REGRESSION_THRESHOLD})"
                ),
                status="open",
            )
            try:
                self._store.put_review_item(ticket)
            except Exception:
                logger.warning("Could not file red-flag ticket", exc_info=True)


def _extract_prediction(method_output: Any) -> Any:
    if isinstance(method_output, dict):
        return method_output.get("prediction", method_output.get("value", method_output))
    return method_output


def _safe_serialize(obj: Any) -> Any:
    if obj is None:
        return None
    try:
        json.dumps(obj, default=str)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _render_markdown(result: BatteryRunResult) -> str:
    m = result.metrics
    lines = [
        f"# External Battery: {result.corpus_name}",
        "",
        f"**Run ID:** {result.run_id}",
        f"**Method:** {result.method_ref.name} v{result.method_ref.version}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Brier | {m.brier:.6f} |",
        f"| Log Loss | {m.log_loss:.6f} |",
        f"| ECE | {m.ece:.6f} |",
        f"| Resolution | {m.resolution:.6f} |",
        f"| Coverage | {m.coverage:.6f} |",
        "",
        f"## Items ({len(result.per_item_results)} total)",
        "",
    ]

    if result.failures:
        lines.append("## Failure Breakdown")
        lines.append("")
        lines.append("| Failure Kind | Count |")
        lines.append("|-------------|-------|")
        for kind, count in sorted(result.failures.items()):
            lines.append(f"| {kind} | {count} |")
        lines.append("")

    for item in result.per_item_results[:20]:
        fk = item.get("failure_kind", "ok")
        lines.append(f"- `{item['source_id']}` — {fk}")
    if len(result.per_item_results) > 20:
        lines.append(f"- ... and {len(result.per_item_results) - 20} more")
    lines.append("")
    return "\n".join(lines)
