"""Test: insert a canary claim after the cut; assert it never appears during counterfactual."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from noosphere.models import (
    Artifact,
    Claim,
    CorpusSelector,
    MethodRef,
    Outcome,
    OutcomeKind,
    Speaker,
    TemporalCut,
)
from noosphere.evaluation.counterfactual import CounterfactualRunner
from noosphere.evaluation.slicer import CorpusSlicer, EmbargoViolation


CUT_DATE = datetime(2025, 6, 1, tzinfo=timezone.utc)
CANARY_DATE = date(2025, 9, 1)
CANARY_TEXT = "CANARY_SHOULD_NEVER_APPEAR"


class LeakTestStore:
    def __init__(self):
        self.artifacts = {
            "a-old": Artifact(
                id="a-old", title="Old",
                created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            "a-new": Artifact(
                id="a-new", title="Future",
                created_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
            ),
        }
        self.claims = {
            "c-old": Claim(
                id="c-old", text="Safe claim",
                speaker=Speaker(name="alice"),
                episode_id="ep1", episode_date=date(2025, 3, 1),
            ),
            "c-canary": Claim(
                id="c-canary", text=CANARY_TEXT,
                speaker=Speaker(name="bob"),
                episode_id="ep2", episode_date=CANARY_DATE,
            ),
        }

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def get_claim(self, claim_id: str):
        return self.claims.get(claim_id)

    def get_chunk(self, chunk_id: str):
        return None

    def get_conclusion(self, conclusion_id: str):
        return None

    def get_embedding_vector(self, embedding_id: str):
        return None

    def list_claim_ids(self):
        return list(self.claims.keys())

    def list_conclusions(self):
        return []

    def list_chunks_for_artifact(self, artifact_id: str):
        return []

    def list_drift_events(self, *, limit=500):
        return []

    def get_temporal_cut(self, cut_id: str):
        return None

    def list_outcomes_for_cut(self, cut_id: str):
        return []


def test_canary_claim_not_visible_through_slicer():
    """Direct slicer test: canary claim after cut must raise EmbargoViolation."""
    store = LeakTestStore()
    cut = TemporalCut(
        cut_id="leak-test",
        as_of=CUT_DATE,
        corpus_slice=CorpusSelector(as_of=CUT_DATE),
        embargoed=CorpusSelector(as_of=CUT_DATE),
        embedding_version_pin="default",
        outcomes=[],
    )
    slicer = CorpusSlicer(store, cut)

    safe = slicer.get_claim("c-old")
    assert safe is not None
    assert CANARY_TEXT not in safe.text

    with pytest.raises(EmbargoViolation):
        slicer.get_claim("c-canary")


def test_canary_not_in_list_claim_ids():
    store = LeakTestStore()
    cut = TemporalCut(
        cut_id="leak-test-2",
        as_of=CUT_DATE,
        corpus_slice=CorpusSelector(as_of=CUT_DATE),
        embargoed=CorpusSelector(as_of=CUT_DATE),
        embedding_version_pin="default",
        outcomes=[],
    )
    slicer = CorpusSlicer(store, cut)
    ids = slicer.list_claim_ids()
    assert "c-canary" not in ids
    assert "c-old" in ids


def test_canary_artifact_not_visible():
    store = LeakTestStore()
    cut = TemporalCut(
        cut_id="leak-test-3",
        as_of=CUT_DATE,
        corpus_slice=CorpusSelector(as_of=CUT_DATE),
        embargoed=CorpusSelector(as_of=CUT_DATE),
        embedding_version_pin="default",
        outcomes=[],
    )
    slicer = CorpusSlicer(store, cut)

    old = slicer.get_artifact("a-old")
    assert old is not None

    with pytest.raises(EmbargoViolation):
        slicer.get_artifact("a-new")


def test_counterfactual_method_never_sees_canary():
    """Full counterfactual run: method that tries to read canary gets blocked."""
    store = LeakTestStore()

    seen_texts: list[str] = []

    def _snooping_method(slicer: Any) -> dict:
        ids = slicer.list_claim_ids()
        for cid in ids:
            c = slicer.get_claim(cid)
            if c is not None:
                seen_texts.append(c.text)
        return {"prediction": 0.5}

    cut = TemporalCut(
        cut_id="cf-leak-test",
        as_of=CUT_DATE,
        corpus_slice=CorpusSelector(as_of=CUT_DATE),
        embargoed=CorpusSelector(as_of=CUT_DATE),
        embedding_version_pin="default",
        outcomes=[
            Outcome(
                outcome_id="o-leak",
                kind=OutcomeKind.BINARY,
                event_ref="evt",
                resolution_source="judge",
                resolved_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                value=True,
            ),
        ],
    )

    runner = CounterfactualRunner(
        store=store,
        method_fn=_snooping_method,
        method_ref=MethodRef(name="snooper", version="1.0"),
    )

    run = runner.run(
        window_start=CUT_DATE,
        window_end=CUT_DATE,
        cadence=timedelta(days=30),
        cuts=[cut],
    )

    assert CANARY_TEXT not in seen_texts
    for t in seen_texts:
        assert CANARY_TEXT not in t
