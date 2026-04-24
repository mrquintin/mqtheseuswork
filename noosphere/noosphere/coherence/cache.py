"""Coherence evaluation cache keyed by claim pair, content hash, and model version bundle."""

from __future__ import annotations

from noosphere.coherence.aggregator import (
    AggregationResult,
    CoherenceAggregator,
    CoherenceModelVersions,
    evaluation_cache_key,
    pair_content_hash,
)
from noosphere.models import Claim
from noosphere.store import Store


def get_cached_evaluation(
    store: Store,
    a: Claim,
    b: Claim,
    versions: CoherenceModelVersions,
) -> AggregationResult | None:
    vj = versions.to_json()
    ch = pair_content_hash(a, b)
    key = evaluation_cache_key(a.id, b.id, vj, ch)
    payload = store.get_coherence_evaluation(key)
    if payload is None:
        return None
    return AggregationResult(payload=payload, judge_packet=None)


def put_cached_evaluation(
    store: Store,
    a: Claim,
    b: Claim,
    versions: CoherenceModelVersions,
    result: AggregationResult,
) -> None:
    vj = versions.to_json()
    ch = pair_content_hash(a, b)
    key = evaluation_cache_key(a.id, b.id, vj, ch)
    store.put_coherence_evaluation(
        evaluation_key=key,
        claim_a_id=a.id,
        claim_b_id=b.id,
        content_hash=ch,
        versions_json=vj,
        payload=result.payload,
    )


def evaluate_pair_cached(
    store: Store,
    aggregator: CoherenceAggregator,
    a: Claim,
    b: Claim,
    **evaluate_kwargs: object,
) -> tuple[AggregationResult, bool]:
    """
    Return ``(result, cache_hit)``. On miss, runs ``evaluate_pair`` and writes cache.
    """
    hit = get_cached_evaluation(store, a, b, aggregator.versions)
    if hit is not None:
        return hit, True
    res = aggregator.evaluate_pair(a, b, **evaluate_kwargs)
    put_cached_evaluation(store, a, b, aggregator.versions, res)
    return res, False
