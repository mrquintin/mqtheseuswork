"""P10 — idempotency holds end-to-end.

* Algorithm runtime: identical input observation → one invocation.
* Synthesizer / memo builder: re-persisting a memo with the same id →
  one row.
* Portfolio dispatch: re-persisting a dispatch with the same id →
  one row.
* Contradiction engine: same pair + same method version + same time
  window → one stored result (idempotency proxied via the engine's
  canonical input hashing, which is the same primitive the runtime
  uses for replay detection).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from noosphere.algorithms.runtime import (
    AlgorithmRuntime,
    canonical_input_hash,
)
from noosphere.models import (
    InvestmentMemo,
    MemoDispatch,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
)
from noosphere.store import Store


# ── canonical_input_hash invariants — the runtime's idempotency primitive ─


def test_canonical_input_hash_is_stable_for_equivalent_inputs() -> None:
    a = canonical_input_hash({"x": 1, "y": 2})
    b = canonical_input_hash({"y": 2, "x": 1})
    assert a == b, "hash must not depend on key order"


def test_canonical_input_hash_differs_for_different_inputs() -> None:
    assert canonical_input_hash({"x": 1}) != canonical_input_hash({"x": 2})


# ── Algorithm runtime replay detection ───────────────────────────────────


def _runtime() -> AlgorithmRuntime:
    # The replay check is the property under test. We bypass __init__
    # — which requires a resolver and llm — and only populate the two
    # attributes the helper consults.
    runtime = object.__new__(AlgorithmRuntime)
    runtime._idempotency_window = 3600  # type: ignore[attr-defined]
    return runtime


def test_runtime_replay_returns_true_for_same_inputs_within_window() -> None:
    runtime = _runtime()
    now = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    algorithm = SimpleNamespace(id="alg_idem", inputs=[])
    trigger_inputs = {"x": 1, "y": 2}
    target_hash = canonical_input_hash(trigger_inputs)

    prior_invocation = SimpleNamespace(
        invoked_at=now - timedelta(seconds=60),
        derived_output={"_meta": {"input_hash": target_hash}},
        trigger_inputs=trigger_inputs,
    )
    fake_store = SimpleNamespace(
        list_invocations_for_algorithm=lambda algorithm_id, limit=64: [prior_invocation],
    )

    assert runtime._is_recent_replay(  # type: ignore[attr-defined]
        fake_store, algorithm, trigger_inputs, now
    ) is True


def test_runtime_replay_returns_false_outside_window() -> None:
    runtime = _runtime()
    now = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    algorithm = SimpleNamespace(id="alg_idem", inputs=[])
    trigger_inputs = {"x": 1}
    target_hash = canonical_input_hash(trigger_inputs)

    # Older than the idempotency window — must not be considered a replay.
    stale = SimpleNamespace(
        invoked_at=now - timedelta(seconds=7200),
        derived_output={"_meta": {"input_hash": target_hash}},
        trigger_inputs=trigger_inputs,
    )
    fake_store = SimpleNamespace(
        list_invocations_for_algorithm=lambda algorithm_id, limit=64: [stale],
    )
    assert runtime._is_recent_replay(  # type: ignore[attr-defined]
        fake_store, algorithm, trigger_inputs, now
    ) is False


def test_runtime_replay_distinguishes_different_inputs() -> None:
    runtime = _runtime()
    now = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    algorithm = SimpleNamespace(id="alg_idem", inputs=[])

    prior = SimpleNamespace(
        invoked_at=now - timedelta(seconds=60),
        derived_output={"_meta": {"input_hash": canonical_input_hash({"x": 1})}},
        trigger_inputs={"x": 1},
    )
    fake_store = SimpleNamespace(
        list_invocations_for_algorithm=lambda algorithm_id, limit=64: [prior],
    )
    assert runtime._is_recent_replay(  # type: ignore[attr-defined]
        fake_store, algorithm, {"x": 2}, now
    ) is False


# ── Synthesizer memo dedup ────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_memo() -> InvestmentMemo:
    return InvestmentMemo(
        id="memo_idem_001",
        organization_id="org_idem",
        title="Idempotency fixture memo",
        slug="idempotency-fixture-memo",
        question_type=MemoQuestionType.EXPLANATORY,
        status=MemoStatus.DRAFT,
        md_path="/tmp/idem.md",
        synthesizer_version="test-v1",
    )


def test_synthesizer_memo_put_is_idempotent_by_id() -> None:
    store = _store()
    memo = _make_memo()
    store.put_investment_memo(memo)
    store.put_investment_memo(memo)
    store.put_investment_memo(memo)

    fetched = store.get_investment_memo(memo.id)
    assert fetched is not None
    assert fetched.id == memo.id

    # Count rows directly to confirm there's exactly one.
    from noosphere.store import StoredInvestmentMemo
    from sqlmodel import select

    with store.session() as s:
        rows = s.exec(
            select(StoredInvestmentMemo).where(
                StoredInvestmentMemo.id == memo.id
            )
        ).all()
    assert len(rows) == 1, f"expected 1 memo row, found {len(rows)}"


# ── Portfolio dispatch dedup ──────────────────────────────────────────────


def test_memo_dispatch_put_is_idempotent_by_id() -> None:
    store = _store()
    # Seed memo for the FK.
    memo = _make_memo()
    store.put_investment_memo(memo)

    dispatch = MemoDispatch(
        id="dispatch_idem_001",
        organization_id="org_idem",
        memo_id=memo.id,
        agent_id="agent_human",
        dispatched_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        outcome_action=MemoDispatchOutcome.PENDING,
        rationale="Initial dispatch.",
    )
    store.put_memo_dispatch(dispatch)
    store.put_memo_dispatch(dispatch)
    store.put_memo_dispatch(dispatch)

    from noosphere.store import StoredMemoDispatch
    from sqlmodel import select

    with store.session() as s:
        rows = s.exec(
            select(StoredMemoDispatch).where(StoredMemoDispatch.id == dispatch.id)
        ).all()
    assert len(rows) == 1, f"expected 1 dispatch row, found {len(rows)}"


# ── Contradiction engine — canonical hashing primitive ────────────────────


def test_contradiction_pair_canonical_hash_stable() -> None:
    """Same principle pair + same method version → same canonical hash.

    The contradiction engine's persistence is gated on a deterministic
    key composed of (principle_id_a, principle_id_b, method_version,
    window_start, window_end). We pin the primitive that produces it
    so a future regression that introduces non-determinism is caught
    immediately. ``canonical_input_hash`` is the same primitive the
    algorithm runtime uses for replay detection, so reusing it here
    is the documented pattern.
    """

    pair = {
        "principle_id_a": "prn_left",
        "principle_id_b": "prn_right",
        "method_version": "citation_entailment.v3",
        "window_start": "2026-05-16T00:00:00Z",
        "window_end": "2026-05-16T23:59:59Z",
    }
    h1 = canonical_input_hash(pair)
    h2 = canonical_input_hash(dict(reversed(list(pair.items()))))
    assert h1 == h2

    # A different method version → different hash → the engine would
    # treat it as a fresh evaluation (which is correct — a method
    # version bump invalidates the prior result).
    h3 = canonical_input_hash({**pair, "method_version": "citation_entailment.v4"})
    assert h1 != h3
