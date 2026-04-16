"""End-to-end test: synthetic corpus + one method → valid CounterfactualEvalRun."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from noosphere.models import (
    Artifact,
    CalibrationMetrics,
    CorpusSelector,
    MethodRef,
    Outcome,
    OutcomeKind,
    TemporalCut,
)
from noosphere.evaluation.counterfactual import CounterfactualRunner
from noosphere.evaluation.slicer import CorpusSlicer


class SyntheticStore:
    """Minimal store with a few artifacts and outcomes for testing."""

    def __init__(self):
        self.artifacts = {
            "a1": Artifact(id="a1", title="Early paper",
                           created_at=datetime(2025, 1, 15, tzinfo=timezone.utc)),
            "a2": Artifact(id="a2", title="Mid paper",
                           created_at=datetime(2025, 3, 15, tzinfo=timezone.utc)),
            "a3": Artifact(id="a3", title="Late paper",
                           created_at=datetime(2025, 7, 15, tzinfo=timezone.utc)),
        }
        self._outcomes: dict[str, list[Outcome]] = {}

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def get_chunk(self, chunk_id: str):
        return None

    def get_claim(self, claim_id: str):
        return None

    def get_conclusion(self, conclusion_id: str):
        return None

    def get_embedding_vector(self, embedding_id: str):
        return None

    def list_claim_ids(self):
        return []

    def list_conclusions(self):
        return []

    def list_chunks_for_artifact(self, artifact_id: str):
        return []

    def list_drift_events(self, *, limit=500):
        return []

    def get_temporal_cut(self, cut_id: str):
        return None

    def list_outcomes_for_cut(self, cut_id: str):
        return self._outcomes.get(cut_id, [])


def _dummy_method(slicer: Any) -> dict:
    """A simple method that always predicts 0.7 probability."""
    return {"prediction": 0.7}


def test_counterfactual_end_to_end():
    store = SyntheticStore()

    cut_date = datetime(2025, 5, 1, tzinfo=timezone.utc)
    outcomes = [
        Outcome(
            outcome_id="o1",
            kind=OutcomeKind.BINARY,
            event_ref="evt-1",
            resolution_source="external_judge",
            resolved_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            value=True,
        ),
        Outcome(
            outcome_id="o2",
            kind=OutcomeKind.BINARY,
            event_ref="evt-2",
            resolution_source="external_judge",
            resolved_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            value=False,
        ),
    ]

    cut = TemporalCut(
        cut_id="test-cut-1",
        as_of=cut_date,
        corpus_slice=CorpusSelector(as_of=cut_date),
        embargoed=CorpusSelector(as_of=cut_date),
        embedding_version_pin="default",
        outcomes=outcomes,
    )

    runner = CounterfactualRunner(
        store=store,
        method_fn=_dummy_method,
        method_ref=MethodRef(name="dummy_predictor", version="1.0"),
    )

    run = runner.run(
        window_start=cut_date,
        window_end=cut_date,
        cadence=timedelta(days=30),
        cuts=[cut],
    )

    assert run.run_id.startswith("cf-")
    assert run.method_ref.name == "dummy_predictor"
    assert len(run.prediction_refs) == 2

    m = run.metrics
    assert isinstance(m, CalibrationMetrics)
    assert 0 <= m.brier <= 1
    assert m.coverage > 0


def test_counterfactual_with_failing_method():
    store = SyntheticStore()
    cut_date = datetime(2025, 5, 1, tzinfo=timezone.utc)

    cut = TemporalCut(
        cut_id="fail-cut",
        as_of=cut_date,
        corpus_slice=CorpusSelector(as_of=cut_date),
        embargoed=CorpusSelector(as_of=cut_date),
        embedding_version_pin="default",
        outcomes=[
            Outcome(
                outcome_id="o-fail",
                kind=OutcomeKind.BINARY,
                event_ref="evt",
                resolution_source="judge",
                resolved_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                value=True,
            ),
        ],
    )

    def _broken_method(slicer):
        raise ValueError("method crashed")

    runner = CounterfactualRunner(
        store=store,
        method_fn=_broken_method,
        method_ref=MethodRef(name="broken", version="1.0"),
    )

    run = runner.run(
        window_start=cut_date,
        window_end=cut_date,
        cadence=timedelta(days=30),
        cuts=[cut],
    )

    assert len(run.prediction_refs) == 0
    assert run.metrics.coverage == 0.0
