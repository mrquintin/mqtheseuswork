"""Counterfactual runner: grades each method's predictive accuracy on held-out temporal slices."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from unittest.mock import patch
from uuid import uuid4

from noosphere.models import (
    CalibrationMetrics,
    CounterfactualEvalRun,
    MethodRef,
    Outcome,
    OutcomeKind,
    TemporalCut,
)
from noosphere.evaluation.outcomes import ResolutionResult, resolve
from noosphere.evaluation.metrics import compute_metrics_for_kind
from noosphere.evaluation.slicer import CorpusSlicer

logger = logging.getLogger(__name__)


class CounterfactualRunner:
    """Run methods against held-out temporal slices and grade predictions."""

    def __init__(
        self,
        store: Any,
        method_fn: Callable,
        method_ref: MethodRef,
        *,
        prediction_extractor: Optional[Callable] = None,
    ) -> None:
        self._store = store
        self._method_fn = method_fn
        self._method_ref = method_ref
        self._prediction_extractor = prediction_extractor or _default_extractor

    def run(
        self,
        window_start: datetime,
        window_end: datetime,
        cadence: timedelta,
        *,
        cuts: Optional[list[TemporalCut]] = None,
    ) -> CounterfactualEvalRun:
        run_id = f"cf-{uuid4().hex[:16]}"

        if cuts is None:
            cuts = self._generate_cuts(window_start, window_end, cadence)

        all_results: list[ResolutionResult] = []
        prediction_refs: list[str] = []
        total_by_kind: dict[OutcomeKind, int] = {}

        for cut in cuts:
            slicer = CorpusSlicer(self._store, cut)
            for outcome in cut.outcomes:
                total_by_kind[outcome.kind] = total_by_kind.get(outcome.kind, 0) + 1
                try:
                    with _block_network():
                        prediction = self._method_fn(slicer)
                except Exception:
                    logger.warning(
                        "Method %s failed on cut %s", self._method_ref.name, cut.cut_id,
                        exc_info=True,
                    )
                    continue

                extracted = self._prediction_extractor(prediction, outcome)
                if extracted is None:
                    continue

                try:
                    result = resolve(outcome, extracted)
                    all_results.append(result)
                    prediction_refs.append(
                        f"{cut.cut_id}:{outcome.outcome_id}"
                    )
                except Exception:
                    logger.warning(
                        "Resolution failed for outcome %s", outcome.outcome_id,
                        exc_info=True,
                    )

        metrics = self._aggregate_metrics(all_results, total_by_kind)

        return CounterfactualEvalRun(
            run_id=run_id,
            method_ref=self._method_ref,
            cut_id=cuts[0].cut_id if cuts else "",
            metrics=metrics,
            prediction_refs=prediction_refs,
            created_at=datetime.now(timezone.utc),
        )

    def _generate_cuts(
        self,
        window_start: datetime,
        window_end: datetime,
        cadence: timedelta,
    ) -> list[TemporalCut]:
        from noosphere.models import CorpusSelector

        cuts: list[TemporalCut] = []
        t = window_start
        while t <= window_end:
            outcomes = self._store.list_outcomes_for_cut(f"auto-{t.isoformat()}")
            cut = TemporalCut(
                cut_id=f"auto-{t.isoformat()}",
                as_of=t,
                corpus_slice=CorpusSelector(as_of=t),
                embargoed=CorpusSelector(as_of=t),
                embedding_version_pin="default",
                outcomes=outcomes if outcomes else [],
            )
            cuts.append(cut)
            t += cadence
        return cuts

    def _aggregate_metrics(
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
        if len(present_kinds) == 1:
            kind = next(iter(present_kinds))
            return compute_metrics_for_kind(
                results, kind, total_by_kind.get(kind, len(results))
            )
        first_kind = next(iter(sorted(present_kinds, key=lambda k: k.value)))
        return compute_metrics_for_kind(
            results, first_kind, total_by_kind.get(first_kind, len(results))
        )


def _default_extractor(prediction: Any, outcome: Outcome) -> Any:
    if isinstance(prediction, dict):
        return prediction.get("prediction", prediction.get("value", prediction))
    return prediction


class _block_network:
    """Context manager that patches socket to prevent network access."""

    def __enter__(self):
        import socket
        self._orig_connect = socket.socket.connect

        def _blocked(*args, **kwargs):
            raise RuntimeError("Network access blocked during counterfactual run")

        self._patch = patch.object(socket.socket, "connect", _blocked)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
