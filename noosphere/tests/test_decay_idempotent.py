"""Tests: re-validating a fresh object is a no-op and emits REVALIDATION_NOOP."""

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


class TestIdempotent:
    def test_fresh_object_yields_no_results(self):
        """A fresh object with no triggered policies produces no revalidation."""
        cid = _uid()
        claim = _make_claim(
            claim_id=cid,
            freshness=Freshness.FRESH,
            last_validated_at=_now(),
        )

        store = MagicMock()
        store.get_claim.side_effect = lambda x: claim if x == cid else None
        store.get_conclusion.return_value = None
        store.list_revalidations.return_value = []
        store.insert_revalidation.return_value = None

        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[cid],
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 999999},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(store, budget_per_run=50)
            results = scheduler.run_once()
            assert results == []

    def test_confirmed_revalidation_is_noop_marker(self):
        """When scheduler revalidates and output matches, outcome is 'confirmed'."""
        cid = _uid()
        claim = _make_claim(
            claim_id=cid,
            freshness=Freshness.STALE,
            last_validated_at=_now() - timedelta(days=30),
        )

        store = MagicMock()
        store.get_claim.side_effect = lambda x: claim if x == cid else None
        store.get_conclusion.return_value = None
        store.list_revalidations.return_value = []
        store.insert_revalidation.return_value = None

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

            scheduler = Scheduler(store, budget_per_run=50)
            results = scheduler.run_once()
            assert len(results) == 1
            assert results[0].outcome == "confirmed"
            assert results[0].object_id == cid
            store.insert_revalidation.assert_called_once()

    def test_repeated_revalidation_of_fresh_is_idempotent(self):
        """Running scheduler twice on a fresh object produces no results both times."""
        cid = _uid()
        claim = _make_claim(
            claim_id=cid,
            freshness=Freshness.FRESH,
            last_validated_at=_now(),
        )

        store = MagicMock()
        store.get_claim.side_effect = lambda x: claim if x == cid else None
        store.get_conclusion.return_value = None
        store.list_revalidations.return_value = []
        store.insert_revalidation.return_value = None

        with patch(
            "noosphere.decay.scheduler.Scheduler._all_bound_object_ids",
            return_value=[cid],
        ), patch(
            "noosphere.decay.freshness._get_bound_policies",
        ) as mock_policies:
            policy = DecayPolicy(
                policy_kind=DecayPolicyKind.FIXED_INTERVAL,
                params={"interval_seconds": 999999},
            )
            mock_policies.return_value = [policy]

            scheduler = Scheduler(store, budget_per_run=50)
            r1 = scheduler.run_once()
            r2 = scheduler.run_once()
            assert r1 == []
            assert r2 == []
