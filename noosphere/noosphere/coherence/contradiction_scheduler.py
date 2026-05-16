"""Pre-filter: schedule only cluster-relevant pairs through the engine.

Sits between the principle-add event and ``ContradictionEngine`` (prompt 06).
The engine remains the source of truth for verdicts; this module decides
WHICH pairs the engine looks at.

Three sampling rails per new principle, all configurable:

1. INTRA-cluster — every other principle in the same cluster. Pair priority
   ``HIGH``. This is where the per-CPU-second yield is highest.
2. NEIGHBORING-cluster sample — ``CROSS_CLUSTER_SAMPLE_FRACTION`` (default
   0.05) of principles in the top-k nearest other clusters. Priority
   ``NORMAL``.
3. DISTANT-cluster surprise check — ``CROSS_CLUSTER_RANDOM_FRACTION``
   (default 0.01) of principles in all far clusters. Priority ``LOW``.

Setting either cross-cluster fraction to exactly 0 is a config error (see
``cluster_index.validate_fractions``). The whole point is to never lose
surprise links.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from noosphere.coherence.cluster_index import (
    CONTRADICTION_TEST_BUDGET_PER_TICK_S,
    CROSS_CLUSTER_RANDOM_FRACTION,
    CROSS_CLUSTER_SAMPLE_FRACTION,
    ClusterConfigError,
    ClusterIndex,
    sample_cross_cluster_pool,
    validate_fractions,
)

__all__ = [
    "ClusterConfigError",
    "DEFAULT_PROVENANCE_POLICY",
    "DrainReport",
    "PERMISSIVE_PROVENANCE_POLICY",
    "ProvenancePolicy",
    "ScheduleReport",
    "run_pending_tests",
    "schedule_tests_for_principle",
]
from noosphere.coherence.contradiction_engine import (
    ContradictionEngine,
    ContradictionResult,
    stable_pair_id,
)
from noosphere.models import (
    ContradictionTestPriority,
    ContradictionTestStatus,
    Principle,
    ProvenanceKind,
    coerce_provenance,
)

logger = logging.getLogger(__name__)


# ── Provenance policy (prompt 09) ───────────────────────────────────────────


@dataclass(frozen=True)
class ProvenancePolicy:
    """Which cross-provenance pairs the scheduler is allowed to enqueue.

    The default policy reflects the founder's directive: a piece the firm
    explicitly disagrees with is *expected* to contradict proprietary
    material — testing those pairs would flood the queue without
    surfacing anything new. The operator can override via the cost
    monitor (prompt 07) to broaden coverage temporarily.

    ``allowed_against_proprietary`` is the set of provenance kinds that
    may be paired with PROPRIETARY material. PROPRIETARY ↔ PROPRIETARY is
    always allowed (intra-firm coherence is the whole point). Pairs that
    don't touch PROPRIETARY are allowed as long as both kinds are in
    ``allowed_pure_external_pairs`` — empty by default, meaning we don't
    waste cycles checking Thiel vs. Strauss.
    """

    allowed_against_proprietary: frozenset[ProvenanceKind] = frozenset(
        {ProvenanceKind.PROPRIETARY, ProvenanceKind.ENDORSED_EXTERNAL}
    )
    allowed_pure_external_pairs: frozenset[ProvenanceKind] = frozenset()


DEFAULT_PROVENANCE_POLICY = ProvenancePolicy()
PERMISSIVE_PROVENANCE_POLICY = ProvenancePolicy(
    allowed_against_proprietary=frozenset(ProvenanceKind),
    allowed_pure_external_pairs=frozenset(ProvenanceKind),
)


def _principle_provenance(store: Any, principle_id: str) -> ProvenanceKind:
    """Look up a principle's provenance via the store, defaulting to PROPRIETARY.

    Resilient to stores that pre-date prompt 09 or to stub stores used in
    tests — when no principle row is found, we fall back to PROPRIETARY
    rather than raising. The scheduler is best-effort: a missing row
    means "we don't know", and the safe default is to behave as if the
    principle were proprietary (i.e. testable).
    """

    fetched = None
    try:
        if hasattr(store, "get_principle"):
            fetched = store.get_principle(principle_id)
    except Exception:
        fetched = None
    if fetched is None or not hasattr(fetched, "provenance"):
        return ProvenanceKind.PROPRIETARY
    return coerce_provenance(getattr(fetched, "provenance", None))


def _pair_allowed_by_policy(
    a: ProvenanceKind, b: ProvenanceKind, policy: ProvenancePolicy
) -> bool:
    if a == ProvenanceKind.PROPRIETARY and b == ProvenanceKind.PROPRIETARY:
        return True
    if ProvenanceKind.PROPRIETARY in (a, b):
        other = b if a == ProvenanceKind.PROPRIETARY else a
        return other in policy.allowed_against_proprietary
    # neither side is proprietary
    return (
        a in policy.allowed_pure_external_pairs
        and b in policy.allowed_pure_external_pairs
    )


# ── Result carriers ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScheduleReport:
    """Summary of one ``schedule_tests_for_principle`` invocation."""

    principle_id: str
    cluster_id: str
    is_new_cluster: bool
    high_priority_enqueued: int
    normal_priority_enqueued: int
    low_priority_enqueued: int
    skipped_dedupe: int
    total_pool_intra: int
    total_pool_neighboring: int
    total_pool_distant: int


@dataclass(frozen=True)
class DrainReport:
    """Summary of one ``run_pending_tests`` invocation."""

    started_at: datetime
    duration_s: float
    attempted: int
    completed: int
    failed: int
    timed_out_at_budget: bool
    detection_method: str


# ── Internals ───────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_principle(
    store: Any, principle_id: str, *, principle: Principle | None = None
) -> Principle | None:
    if principle is not None:
        return principle
    if hasattr(store, "get_principle"):
        try:
            return store.get_principle(principle_id)
        except Exception:
            pass
    # Fall back to scanning list_principles; OK because the catalog is tiny
    # relative to the contradiction-test queue itself.
    if hasattr(store, "list_principles"):
        for p in store.list_principles():
            if p.id == principle_id:
                return p
    return None


def _enqueue(
    store: Any,
    *,
    a_id: str,
    b_id: str,
    priority: ContradictionTestPriority,
) -> bool:
    pair_key = stable_pair_id(a_id, b_id)
    task_id = store.enqueue_contradiction_test_task(
        principle_a_id=a_id,
        principle_b_id=b_id,
        priority=priority.value
        if hasattr(priority, "value")
        else str(priority),
        pair_key=pair_key,
    )
    return task_id is not None


# ── Schedule ────────────────────────────────────────────────────────────────


async def schedule_tests_for_principle(
    store: Any,
    new_principle_id: str,
    *,
    index: ClusterIndex,
    embedding: Sequence[float] | None = None,
    principle: Principle | None = None,
    sample_fraction: float = CROSS_CLUSTER_SAMPLE_FRACTION,
    random_fraction: float = CROSS_CLUSTER_RANDOM_FRACTION,
    neighbor_k: int = 3,
    rng: random.Random | None = None,
    provenance_policy: ProvenancePolicy = DEFAULT_PROVENANCE_POLICY,
) -> ScheduleReport:
    """Decide which contradiction tests to schedule for one new principle.

    The cluster index handles join-or-create. We then enqueue:
      - HIGH for every other intra-cluster member,
      - NORMAL for the cross-cluster sample (from the top-``neighbor_k``
        nearest clusters),
      - LOW for the surprise check (from all distant clusters).

    Zero fractions are a config error.

    Prompt 09: pairs are gated by ``provenance_policy``. By default the
    scheduler skips PROPRIETARY ↔ STUDIED_EXTERNAL / OPPOSING_EXTERNAL —
    those are *expected* to differ. Passing
    :data:`PERMISSIVE_PROVENANCE_POLICY` (e.g. from the cost monitor)
    lifts the gate temporarily.
    """

    validate_fractions(sample_fraction, random_fraction)

    new_provenance = _principle_provenance(store, new_principle_id)
    resolved = _resolve_principle(store, new_principle_id, principle=principle)
    vec = (
        list(embedding)
        if embedding is not None
        else (list(resolved.embedding) if resolved and resolved.embedding else None)
    )
    if not vec:
        raise ValueError(
            f"schedule_tests_for_principle: principle {new_principle_id!r} "
            "needs an embedding (pass via `embedding=` or attach to the "
            "Principle row)"
        )

    assignment = index.assign(new_principle_id, vec)
    cluster_id = assignment.cluster_id

    rng = rng or random.Random()
    high = normal = low = 0
    skipped = 0

    def _gate(pid: str) -> bool:
        other = _principle_provenance(store, pid)
        return _pair_allowed_by_policy(new_provenance, other, provenance_policy)

    # ── intra-cluster ───────────────────────────────────────────────────
    intra_pool = [
        pid for pid in index.members_of(cluster_id) if pid != new_principle_id
    ]
    intra_pool = [pid for pid in intra_pool if _gate(pid)]
    for pid in intra_pool:
        if _enqueue(
            store,
            a_id=new_principle_id,
            b_id=pid,
            priority=ContradictionTestPriority.HIGH,
        ):
            high += 1
        else:
            skipped += 1

    # ── neighboring-cluster sample ──────────────────────────────────────
    neighbor_ids = index.neighboring_cluster_ids(cluster_id, k=neighbor_k)
    neighboring_pool: list[str] = []
    for nid in neighbor_ids:
        neighboring_pool.extend(index.members_of(nid))
    neighboring_pool = [pid for pid in neighboring_pool if _gate(pid)]
    sampled_neighbors = sample_cross_cluster_pool(
        neighboring_pool, sample_fraction, rng=rng, minimum=1
    )
    for pid in sampled_neighbors:
        if _enqueue(
            store,
            a_id=new_principle_id,
            b_id=pid,
            priority=ContradictionTestPriority.NORMAL,
        ):
            normal += 1
        else:
            skipped += 1

    # ── distant-cluster surprise ────────────────────────────────────────
    distant_ids = index.distant_cluster_ids(cluster_id)
    # Exclude the neighbor pool so the surprise check is truly "far".
    distant_only = [cid for cid in distant_ids if cid not in set(neighbor_ids)]
    distant_pool: list[str] = []
    for cid in distant_only:
        distant_pool.extend(index.members_of(cid))
    distant_pool = [pid for pid in distant_pool if _gate(pid)]
    sampled_distant = sample_cross_cluster_pool(
        distant_pool, random_fraction, rng=rng, minimum=1
    )
    for pid in sampled_distant:
        if _enqueue(
            store,
            a_id=new_principle_id,
            b_id=pid,
            priority=ContradictionTestPriority.LOW,
        ):
            low += 1
        else:
            skipped += 1

    logger.info(
        "contradiction_scheduler.schedule principle=%s cluster=%s new_cluster=%s "
        "high=%d normal=%d low=%d skipped=%d",
        new_principle_id,
        cluster_id,
        assignment.is_new_cluster,
        high,
        normal,
        low,
        skipped,
    )
    return ScheduleReport(
        principle_id=new_principle_id,
        cluster_id=cluster_id,
        is_new_cluster=assignment.is_new_cluster,
        high_priority_enqueued=high,
        normal_priority_enqueued=normal,
        low_priority_enqueued=low,
        skipped_dedupe=skipped,
        total_pool_intra=len(intra_pool),
        total_pool_neighboring=len(neighboring_pool),
        total_pool_distant=len(distant_pool),
    )


# ── Drain ───────────────────────────────────────────────────────────────────


async def _run_one(
    store: Any,
    task: dict[str, Any],
    *,
    engine: ContradictionEngine,
    semaphore: asyncio.Semaphore,
) -> tuple[bool, str | None, str | None]:
    """Detect one pair. Returns (succeeded, result_id, error)."""

    async with semaphore:
        a = _resolve_principle(store, task["principle_a_id"])
        b = _resolve_principle(store, task["principle_b_id"])
        if a is None or b is None:
            err = (
                f"missing principle a={task['principle_a_id']!r} "
                f"b={task['principle_b_id']!r}"
            )
            return False, None, err
        try:
            result: ContradictionResult = await engine.detect(a, b)
        except Exception as exc:  # noqa: BLE001 — surface as task FAILED
            return False, None, f"{type(exc).__name__}: {exc}"
        # Persist via the canonical kwargs API. The Store may not be wired
        # up (e.g. in unit tests against a partial fixture), so failures
        # here demote to a logged warning — the queue still drains.
        result_id: Optional[str] = None
        if hasattr(store, "put_contradiction_result"):
            try:
                generated_id = (
                    f"cr_{stable_pair_id(result.principle_a_id, result.principle_b_id)}"
                )
                store.put_contradiction_result(
                    result_id=generated_id,
                    principle_a_id=result.principle_a_id,
                    principle_b_id=result.principle_b_id,
                    score=result.score,
                    confidence_low=result.confidence_low,
                    confidence_high=result.confidence_high,
                    verdict=result.verdict.value
                    if hasattr(result.verdict, "value")
                    else str(result.verdict),
                    axis=result.axis,
                    human_explanation=result.human_explanation,
                    detection_method=result.detection_method,
                    detected_at=result.detected_at,
                    raw_sparsity=result.raw_sparsity,
                    direction_method=result.direction_method,
                    extras=result.extras,
                )
                result_id = generated_id
            except Exception as exc:  # noqa: BLE001 — never block drain
                logger.warning(
                    "contradiction_scheduler.persist_result_failed: %s",
                    f"{type(exc).__name__}: {exc}",
                )
        return True, result_id, None


async def run_pending_tests(
    store: Any,
    *,
    engine: ContradictionEngine,
    max_concurrency: int = 4,
    time_budget_seconds: float = CONTRADICTION_TEST_BUDGET_PER_TICK_S,
) -> DrainReport:
    """Drain the contradiction test queue, respecting a wall-clock budget.

    Tasks are picked in (priority, enqueued_at) order. The budget is
    enforced between tasks — an individual detect call that itself exceeds
    the budget will still finish, but no new task is started after the
    budget elapses. This is what keeps the per-tick latency bounded so
    contradiction work doesn't starve forecasts/currents.
    """

    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")
    start = time.monotonic()
    started_at = _utcnow()
    semaphore = asyncio.Semaphore(max_concurrency)
    attempted = completed = failed = 0
    timed_out = False

    while True:
        if time.monotonic() - start >= time_budget_seconds:
            timed_out = True
            break
        # Pull a batch up to max_concurrency * 2 to keep the semaphore fed.
        batch_size = max(1, max_concurrency * 2)
        batch = store.list_pending_contradiction_test_tasks(limit=batch_size)
        if not batch:
            break
        runnable = batch[:max_concurrency]
        for task in runnable:
            store.mark_contradiction_test_task(
                task["id"],
                status=ContradictionTestStatus.RUNNING.value,
                started_at=_utcnow(),
            )

        async def _wrapped(t: dict[str, Any]) -> tuple[dict[str, Any], bool, str | None, str | None]:
            ok, rid, err = await _run_one(
                store, t, engine=engine, semaphore=semaphore
            )
            return t, ok, rid, err

        results = await asyncio.gather(
            *(_wrapped(t) for t in runnable), return_exceptions=False
        )
        for task, ok, rid, err in results:
            attempted += 1
            if ok:
                completed += 1
                store.mark_contradiction_test_task(
                    task["id"],
                    status=ContradictionTestStatus.DONE.value,
                    result_id=rid,
                    finished_at=_utcnow(),
                )
            else:
                failed += 1
                store.mark_contradiction_test_task(
                    task["id"],
                    status=ContradictionTestStatus.FAILED.value,
                    last_error=err,
                    finished_at=_utcnow(),
                )
        if time.monotonic() - start >= time_budget_seconds:
            timed_out = True
            break

    duration = time.monotonic() - start
    return DrainReport(
        started_at=started_at,
        duration_s=float(duration),
        attempted=attempted,
        completed=completed,
        failed=failed,
        timed_out_at_budget=timed_out,
        detection_method=engine.detection_method,
    )
