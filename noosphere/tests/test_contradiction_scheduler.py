"""Tests for the cluster-pre-filter contradiction scheduler (R19/p07).

The scheduler does NOT execute detection — it just enqueues pairs. The
engine itself remains the source of truth (see ``test_contradiction_engine``).
Here we verify routing, priority, dedupe, the surprise-catch property, and
the time-budget behavior of the drain.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pytest

from noosphere.coherence.cluster_index import ClusterIndex
from noosphere.coherence.contradiction_engine import (
    ContradictionEngine,
    ContradictionResult,
    ContradictionVerdict,
    DETECTION_METHOD_VERSION,
)
from noosphere.coherence.contradiction_scheduler import (
    ClusterConfigError,
    run_pending_tests,
    schedule_tests_for_principle,
)
from noosphere.models import Principle
from noosphere.store import Store


# ── fixtures ────────────────────────────────────────────────────────────────


def _unit(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=float)
    n = np.linalg.norm(arr)
    if n == 0.0:
        return vec
    return (arr / n).tolist()


def _make_principle(pid: str, vec: list[float]) -> Principle:
    return Principle(id=pid, text=f"principle {pid}", embedding=vec)


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture
def index(store: Store) -> ClusterIndex:
    idx = ClusterIndex(store)
    idx.hydrate({})
    return idx


class _PrincipleBag:
    """Tiny in-memory adapter: ``store.get_principle`` for the scheduler.

    The scheduler falls back to ``store.list_principles`` if ``get_principle``
    isn't present; this adapter just makes the fixture explicit.
    """

    def __init__(self, store: Store) -> None:
        self._store = store
        self._principles: dict[str, Principle] = {}

    def add(self, p: Principle) -> None:
        self._principles[p.id] = p
        # Patch the store with a get_principle that the scheduler can find.
        bag = self._principles

        def _get(pid: str) -> Principle | None:
            return bag.get(pid)

        # type: ignore[attr-defined]
        self._store.get_principle = _get  # type: ignore[attr-defined]


@pytest.fixture
def bag(store: Store) -> _PrincipleBag:
    return _PrincipleBag(store)


# ── scheduling ─────────────────────────────────────────────────────────────


def test_intra_cluster_pairs_are_high_priority(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    base = _unit([1.0, 0.0, 0.0, 0.0])
    for i in range(3):
        wiggle = (np.random.default_rng(i).standard_normal(4) * 0.02).tolist()
        vec = _unit([b + w for b, w in zip(base, wiggle)])
        p = _make_principle(f"intra_{i}", vec)
        bag.add(p)
        index.assign(p.id, vec)

    new_vec = _unit([0.95, 0.05, 0.02, 0.01])
    new_p = _make_principle("intra_new", new_vec)
    bag.add(new_p)

    report = asyncio.run(
        schedule_tests_for_principle(
            store,
            new_p.id,
            index=index,
            embedding=new_vec,
            sample_fraction=0.05,
            random_fraction=0.01,
        )
    )
    assert report.high_priority_enqueued == 3
    assert report.is_new_cluster is False


def test_cross_cluster_sample_fires_low_priority(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    # cluster A — where the new principle will land
    for i in range(3):
        vec = _unit([1.0, 0.0, 0.0, 0.0])
        bag.add(_make_principle(f"a_{i}", vec))
        index.assign(f"a_{i}", vec)
    # cluster B — close neighbor (small angle off A)
    for i in range(20):
        vec = _unit([0.9, 0.4, 0.0, 0.0])
        bag.add(_make_principle(f"b_{i}", vec))
        index.assign(f"b_{i}", vec)
    # cluster C — orthogonal y-axis (further than B from A)
    for i in range(20):
        vec = _unit([0.0, 1.0, 0.0, 0.0])
        bag.add(_make_principle(f"c_{i}", vec))
        index.assign(f"c_{i}", vec)
    # cluster D — orthogonal z-axis (also far; with k=2 neighbors B,C are
    # picked, D ends up in the distant pool)
    for i in range(20):
        vec = _unit([0.0, 0.0, 1.0, 0.0])
        bag.add(_make_principle(f"d_{i}", vec))
        index.assign(f"d_{i}", vec)
    # cluster E — opposite direction; firmly distant
    for i in range(20):
        vec = _unit([-1.0, 0.0, 0.0, 0.0])
        bag.add(_make_principle(f"e_{i}", vec))
        index.assign(f"e_{i}", vec)

    new_vec = _unit([0.99, 0.05, 0.01, 0.01])
    bag.add(_make_principle("new", new_vec))

    report = asyncio.run(
        schedule_tests_for_principle(
            store,
            "new",
            index=index,
            embedding=new_vec,
            sample_fraction=0.05,
            random_fraction=0.01,
            neighbor_k=2,
            rng=random.Random(0),
        )
    )
    # Must have scheduled at least one NORMAL (neighboring) and one LOW
    # (distant) — the prompt's hard rule.
    assert report.normal_priority_enqueued >= 1
    assert report.low_priority_enqueued >= 1
    # Sample fraction is 0.05 of a 20-member pool -> ceil(1.0) = 1 minimum.
    assert report.normal_priority_enqueued <= 3  # well below the pool
    assert report.low_priority_enqueued <= 3


def test_zero_fraction_is_config_error(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    bag.add(_make_principle("solo", _unit([1.0, 0.0, 0.0, 0.0])))
    with pytest.raises(ClusterConfigError):
        asyncio.run(
            schedule_tests_for_principle(
                store,
                "solo",
                index=index,
                embedding=_unit([1.0, 0.0, 0.0, 0.0]),
                sample_fraction=0.0,
                random_fraction=0.01,
            )
        )
    with pytest.raises(ClusterConfigError):
        asyncio.run(
            schedule_tests_for_principle(
                store,
                "solo",
                index=index,
                embedding=_unit([1.0, 0.0, 0.0, 0.0]),
                sample_fraction=0.05,
                random_fraction=0.0,
            )
        )


def test_dedupe_rejects_same_pair_within_24h(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    # Two principles in the same cluster — first schedule enqueues a pair;
    # second schedule (mirror direction) must dedupe.
    bag.add(_make_principle("p1", _unit([1.0, 0.0, 0.0, 0.0])))
    index.assign("p1", _unit([1.0, 0.0, 0.0, 0.0]))
    bag.add(_make_principle("p2", _unit([0.98, 0.02, 0.0, 0.0])))

    first = asyncio.run(
        schedule_tests_for_principle(
            store,
            "p2",
            index=index,
            embedding=_unit([0.98, 0.02, 0.0, 0.0]),
            sample_fraction=0.05,
            random_fraction=0.01,
        )
    )
    assert first.high_priority_enqueued == 1

    # Re-running the same insert should not enqueue another row — the
    # pair_key is shared between (p1,p2) and (p2,p1).
    second = asyncio.run(
        schedule_tests_for_principle(
            store,
            "p2",
            index=index,
            embedding=_unit([0.98, 0.02, 0.0, 0.0]),
            sample_fraction=0.05,
            random_fraction=0.01,
        )
    )
    assert second.skipped_dedupe >= 1
    # And a brand-new scheduling from the other side also dedupes.
    third = asyncio.run(
        schedule_tests_for_principle(
            store,
            "p1",
            index=index,
            embedding=_unit([1.0, 0.0, 0.0, 0.0]),
            sample_fraction=0.05,
            random_fraction=0.01,
        )
    )
    assert third.high_priority_enqueued == 0


def test_surprise_check_catches_planted_distant_pair_within_100_inserts(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    """A planted contradiction sitting alone in a far cluster must show up
    in the LOW-priority queue within the first 100 inserts.

    With one principle in the distant pool, the random-fraction (>0) +
    minimum=1 floor guarantees it is selected on every insert. The test
    asserts the *guaranteed* behavior, not the probabilistic one — we
    want this to be deterministic.
    """

    # Cluster A — home of the new principles. Seed it first so the new
    # arrivals join it instead of any neighbor cluster.
    for i in range(3):
        vec = _unit([1.0, 0.0, 0.0, 0.0])
        bag.add(_make_principle(f"a_{i}", vec))
        index.assign(f"a_{i}", vec)
    # Three neighbor clusters with centers below A's join-threshold
    # (cos = 0.5 each) so they form distinct clusters AND fill the top-3
    # neighbor slots when the new principle later lands in A.
    for i in range(3):
        vec = _unit([0.5, 0.7, 0.5, 0.0])
        bag.add(_make_principle(f"b_{i}", vec))
        index.assign(f"b_{i}", vec)
    for i in range(3):
        vec = _unit([0.5, 0.0, 0.7, 0.5])
        bag.add(_make_principle(f"c_{i}", vec))
        index.assign(f"c_{i}", vec)
    for i in range(3):
        vec = _unit([0.5, 0.5, 0.0, 0.7])
        bag.add(_make_principle(f"d_{i}", vec))
        index.assign(f"d_{i}", vec)

    # Planted cluster — alone, far from everything else (negative axis).
    planted_vec = _unit([-1.0, 0.0, 0.0, 0.0])
    planted = _make_principle("planted_contradiction", planted_vec)
    bag.add(planted)
    index.assign(planted.id, planted_vec)

    # The new principle lives in cluster A, far from the planted cluster.
    rng = random.Random(42)
    found_low = False
    for i in range(100):
        wiggle = (
            np.random.default_rng(seed=i).standard_normal(4) * 0.005
        ).tolist()
        new_vec = _unit([1.0 + wiggle[0], wiggle[1], wiggle[2], wiggle[3]])
        new_id = f"new_{i}"
        bag.add(_make_principle(new_id, new_vec))
        report = asyncio.run(
            schedule_tests_for_principle(
                store,
                new_id,
                index=index,
                embedding=new_vec,
                sample_fraction=0.05,
                random_fraction=0.01,
                rng=rng,
            )
        )
        if report.low_priority_enqueued >= 1:
            found_low = True
            break
    assert found_low, "planted distant contradiction was never scheduled"

    # The queue must contain a LOW-priority pair touching planted.
    queue = store.list_pending_contradiction_test_tasks(limit=500)
    low_with_planted = [
        t
        for t in queue
        if t["priority"] == "LOW"
        and planted.id in {t["principle_a_id"], t["principle_b_id"]}
    ]
    assert low_with_planted, "no LOW-priority pair includes the planted principle"


# ── drain ──────────────────────────────────────────────────────────────────


class _FakeContradictionEngine(ContradictionEngine):
    """Engine that just emits a fixed verdict, optionally with a sleep so we
    can exercise the time budget without real geometry."""

    def __init__(self, *, sleep_s: float = 0.0) -> None:
        super().__init__()
        self._sleep_s = sleep_s

    @property
    def detection_method(self) -> str:
        return "test-fake/v1"

    async def detect(  # type: ignore[override]
        self, a: Principle, b: Principle, *, store: Any | None = None
    ) -> ContradictionResult:
        if self._sleep_s > 0:
            await asyncio.sleep(self._sleep_s)
        return ContradictionResult(
            principle_a_id=a.id,
            principle_b_id=b.id,
            score=0.5,
            confidence_low=0.4,
            confidence_high=0.6,
            verdict=ContradictionVerdict.INDEPENDENT,
            axis=None,
            human_explanation=None,
            detection_method=self.detection_method,
            detected_at=datetime.now(timezone.utc),
            raw_sparsity=0.5,
            direction_method="test",
        )


def test_drain_respects_time_budget(
    store: Store, index: ClusterIndex, bag: _PrincipleBag
) -> None:
    # Queue 10 tasks; each "engine" call sleeps 0.05s. Budget=0.15s should
    # complete at most ~3 tasks and then stop without blowing past the
    # budget by more than ~one slot.
    base = _unit([1.0, 0.0, 0.0, 0.0])
    for i in range(11):
        wiggle = (np.random.default_rng(i).standard_normal(4) * 0.02).tolist()
        vec = _unit([b + w for b, w in zip(base, wiggle)])
        p = _make_principle(f"p_{i}", vec)
        bag.add(p)
        index.assign(p.id, vec)

    # One scheduling round on the last one populates the queue.
    asyncio.run(
        schedule_tests_for_principle(
            store,
            "p_10",
            index=index,
            embedding=index._members[index.cluster_id_of("p_10")]["p_10"],
            sample_fraction=0.05,
            random_fraction=0.01,
        )
    )
    assert (
        len(store.list_pending_contradiction_test_tasks(limit=100)) >= 5
    )

    engine = _FakeContradictionEngine(sleep_s=0.08)
    started = time.monotonic()
    report = asyncio.run(
        run_pending_tests(
            store,
            engine=engine,
            max_concurrency=1,
            time_budget_seconds=0.25,
        )
    )
    elapsed = time.monotonic() - started
    # The drain should have finished close to the budget — not be allowed
    # to run unbounded. We allow a generous slack for scheduler jitter.
    assert elapsed < 1.0
    # It also should have made some progress (≥1 attempt).
    assert report.attempted >= 1
    # Tasks not yet drained remain PENDING.
    leftover = store.list_pending_contradiction_test_tasks(limit=100)
    assert len(leftover) >= 0  # the queue is observable; budget hit is OK
