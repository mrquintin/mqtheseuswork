"""Counterfactual replay engine: synthetic ledger + two methods of
known relative performance. The engine must reproduce the ranking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from noosphere.evaluation.counterfactual_replay import (
    CounterfactualReplayEngine,
    MethodIncompatibleError,
    ResolvedRow,
    would_have_been_better_matrix,
)
from noosphere.methods._registry import MethodRegistry
from noosphere.models import (
    Claim,
    Conclusion,
    Method,
    MethodImplRef,
    MethodType,
    Speaker,
)


# ── synthetic ledger ────────────────────────────────────────────────


class FakeStore:
    """Just enough store surface for the replay engine."""

    def __init__(self) -> None:
        self.claims: dict[str, Claim] = {}
        self.conclusions: dict[str, Conclusion] = {}

    def add_claim(self, c: Claim) -> None:
        self.claims[c.id] = c

    def add_conclusion(self, c: Conclusion) -> None:
        self.conclusions[c.id] = c

    # store surface ------------------------------------------------------

    def list_claim_ids(self):
        return list(self.claims.keys())

    def get_claim(self, cid: str):
        return self.claims.get(cid)

    def get_artifact(self, aid: str):
        return None

    def list_conclusions(self):
        return list(self.conclusions.values())

    def get_conclusion(self, cid: str):
        return self.conclusions.get(cid)

    def session(self):  # pragma: no cover — not used in this test path
        raise RuntimeError("FakeStore has no SQL session")


# ── synthetic methods of known relative performance ────────────────


def _make_spec(name: str) -> Method:
    return Method(
        method_id=f"sha-{name}",
        name=name,
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={},
        output_schema={},
        description=f"synthetic {name}",
        rationale="test fixture",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module=__name__, fn_name=name, git_sha="test", image_digest=None
        ),
        owner="test",
        status="active",
        nondeterministic=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _good_method(input_data: dict) -> dict:
    """Returns a confidence aligned with the planted truth label."""
    return {"confidence": 0.9 if input_data["truth"] else 0.1}


def _bad_method(input_data: dict) -> dict:
    """Returns flat 0.5 — uninformed predictions."""
    return {"confidence": 0.5}


def _adapter(conclusion: Conclusion, snap, store) -> dict:
    if not conclusion.evidence_chain_claim_ids:
        raise MethodIncompatibleError("conclusion has no evidence")
    # Truth label is encoded into the conclusion's text by the test fixture.
    return {
        "conclusion_id": conclusion.id,
        "n_claims": len(snap.visible_claim_ids),
        "truth": "TRUE" in conclusion.text,
    }


# ── fixtures ────────────────────────────────────────────────────────


def _build_ledger() -> tuple[FakeStore, list[ResolvedRow]]:
    store = FakeStore()
    speaker = Speaker(name="test")

    rows: list[ResolvedRow] = []
    truth_labels = [True, True, False, True, False, False, True, False]
    for i, truth in enumerate(truth_labels):
        claim = Claim(
            id=f"cl-{i}",
            text=f"evidence for item {i}",
            speaker=speaker,
            episode_id=f"ep-{i}",
            episode_date=datetime(2026, 1, 10).date(),
        )
        store.add_claim(claim)
        conclusion = Conclusion(
            id=f"conc-{i}",
            text=f"forecast {i} TRUE" if truth else f"forecast {i} FALSE",
            evidence_chain_claim_ids=[claim.id],
            confidence=0.5,
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        store.add_conclusion(conclusion)
        rows.append(
            ResolvedRow(
                conclusion=conclusion,
                actual_method="bad_method",
                actual_confidence_yes=0.5,
                outcome=truth,
            )
        )
    return store, rows


def _engine(store: FakeStore) -> CounterfactualReplayEngine:
    reg = MethodRegistry()
    reg.register(_make_spec("good_method"), _good_method)
    reg.register(_make_spec("bad_method"), _bad_method)
    engine = CounterfactualReplayEngine(store, registry=reg)
    engine.register_adapter("good_method", _adapter)
    engine.register_adapter("bad_method", _adapter)
    return engine


# ── tests ───────────────────────────────────────────────────────────


def test_snapshot_id_is_deterministic_and_bounded_by_as_of():
    store, _ = _build_ledger()
    engine = _engine(store)
    conclusion = store.get_conclusion("conc-0")

    snap_a = engine.snapshot_for(conclusion)
    snap_b = engine.snapshot_for(conclusion)
    assert snap_a.snapshot_id == snap_b.snapshot_id
    assert snap_a.as_of == conclusion.created_at
    assert all(cid in snap_a.visible_claim_ids for cid in store.claims)


def test_replay_returns_alternative_confidence_and_caches():
    store, _ = _build_ledger()
    engine = _engine(store)
    conclusion = store.get_conclusion("conc-0")  # truth=True

    first = engine.replay(conclusion, "good_method")
    assert first.alternative_confidence == pytest.approx(0.9)
    assert first.cached is False
    assert "snapshot=" in first.reasoning_trace

    second = engine.replay(conclusion, "good_method")
    assert second.cached is True
    assert second.alternative_confidence == pytest.approx(0.9)


def test_replay_errors_loud_on_incompatible_method():
    """A registered method without an adapter must error loud."""
    store, _ = _build_ledger()
    reg = MethodRegistry()
    reg.register(_make_spec("good_method"), _good_method)
    reg.register(_make_spec("orphan_method"), _good_method)
    engine = CounterfactualReplayEngine(store, registry=reg)
    engine.register_adapter("good_method", _adapter)
    # orphan_method is registered but has no adapter — replay must refuse.
    conclusion = store.get_conclusion("conc-0")

    with pytest.raises(MethodIncompatibleError):
        engine.replay(conclusion, "orphan_method")


def test_replay_errors_when_evidence_is_missing():
    store, _ = _build_ledger()
    engine = _engine(store)
    bare = Conclusion(
        id="bare",
        text="no evidence TRUE",
        evidence_chain_claim_ids=[],
        confidence=0.5,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    store.add_conclusion(bare)
    with pytest.raises(MethodIncompatibleError):
        engine.replay(bare, "good_method")


def test_would_have_been_better_matrix_recovers_known_ranking():
    """The good method has a planted alignment with truth and should
    aggregate to a substantially lower Brier than the bad method
    against the same outcomes."""
    store, rows = _build_ledger()
    engine = _engine(store)

    cells = would_have_been_better_matrix(
        engine, rows, ["good_method", "bad_method"]
    )

    by_alt = {c.alternative_method: c for c in cells if c.actual_method == "bad_method"}
    assert "good_method" in by_alt
    good = by_alt["good_method"]
    assert good.n == len(rows)
    # Good method's planted alignment dominates the flat 0.5 baseline.
    assert good.mean_brier_alternative < good.mean_brier_actual
    # Signed delta < 0 means alt would have been better than actual on average.
    assert good.mean_brier_delta < 0
    assert good.alt_better_count == len(rows)


def test_snapshot_excludes_claims_after_as_of():
    """Claims authored *after* the conclusion's created_at must not be
    visible in the replay snapshot — that is the anachronism guard."""
    store, _ = _build_ledger()
    speaker = Speaker(name="future")
    future_claim = Claim(
        id="cl-future",
        text="from the future",
        speaker=speaker,
        episode_id="ep-future",
        episode_date=datetime(2027, 1, 1).date(),
    )
    store.add_claim(future_claim)

    engine = _engine(store)
    conclusion = store.get_conclusion("conc-0")
    snap = engine.snapshot_for(conclusion)
    assert "cl-future" not in snap.visible_claim_ids
