"""Tests: scheduler respects budget and priority order; warmup suppresses early decay."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from noosphere.models import (
    Claim,
    DecayPolicy,
    DecayPolicyKind,
    Freshness,
    RevalidationResult,
    Speaker,
)
from noosphere.decay.scheduler import Scheduler


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_claim(
    claim_id: str | None = None,
    freshness: Freshness = Freshness.FRESH,
    last_validated_at: datetime | None = None,
) -> Claim:
    return Claim(
        id=claim_id or _uid(),
        text="test",
        speaker=Speaker(name="Alice"),
        episode_id="ep1",
        episode_date="2025-01-01",
        freshness=freshness,
        last_validated_at=last_validated_at,
    )


def _mock_store_with_candidates(claims: list[Claim]) -> MagicMock:
    store = MagicMock()

    def get_claim(cid):
        for c in claims:
            if c.id == cid:
                return c
        return None

    store.get_claim.side_effect = get_claim
    store.get_conclusion.return_value = None
    store.list_revalidations.return_value = []
    store.insert_revalidation.return_value = None
    return store


class TestBudgetCap:
    def test_respects_budget_limit(self):
        ids = [_uid() for _ in range(10)]
        claims = [
            _make_claim(claim_id=cid, last_validated_at=None) for cid in ids
        ]
        store = _mock_store_with_candidates(claims)

        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=ids,
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 1},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(store, budget_per_run=3)
            results = scheduler.run_once()
            assert len(results) == 3

    def test_processes_zero_when_no_candidates(self):
        store = MagicMock()
        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[],
        ):
            scheduler = Scheduler(store, budget_per_run=50)
            results = scheduler.run_once()
            assert results == []


class TestPriorityOrder:
    def test_stale_before_aging(self):
        stale_id = _uid()
        aging_id = _uid()
        stale_claim = _make_claim(
            claim_id=stale_id,
            freshness=Freshness.STALE,
            last_validated_at=_now() - timedelta(days=30),
        )
        aging_claim = _make_claim(
            claim_id=aging_id,
            freshness=Freshness.AGING,
            last_validated_at=_now() - timedelta(days=1),
        )

        store = _mock_store_with_candidates([stale_claim, aging_claim])

        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[aging_id, stale_id],
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 1},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(store, budget_per_run=1)
            results = scheduler.run_once()
            assert len(results) == 1
            assert results[0].object_id == stale_id


class TestWarmup:
    def test_warmup_suppresses_all_candidates(self):
        cid = _uid()
        claim = _make_claim(claim_id=cid, last_validated_at=None)
        store = _mock_store_with_candidates([claim])

        deploy = _now() - timedelta(days=5)
        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[cid],
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 1},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(
                store, budget_per_run=50, warmup_days=14, deploy_time=deploy,
            )
            results = scheduler.run_once()
            assert results == []

    def test_warmup_allows_after_period(self):
        cid = _uid()
        claim = _make_claim(claim_id=cid, last_validated_at=None)
        store = _mock_store_with_candidates([claim])

        deploy = _now() - timedelta(days=30)
        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[cid],
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 1},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(
                store, budget_per_run=50, warmup_days=14, deploy_time=deploy,
            )
            results = scheduler.run_once()
            assert len(results) >= 1
