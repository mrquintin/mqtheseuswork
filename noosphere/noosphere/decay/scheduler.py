"""Scheduler: priority queue + budget cap + thrashing detector."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noosphere.models import Freshness, RevalidationResult

from noosphere.decay.freshness import compute_freshness

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Candidate:
    object_id: str
    freshness: Freshness
    last_validated_at: Optional[datetime] = None
    prior_output: Any = None


class Scheduler:
    def __init__(
        self,
        store: Any,
        budget_per_run: int = 50,
        warmup_days: int = 14,
        thrashing_threshold: int = 5,
        deploy_time: Optional[datetime] = None,
    ) -> None:
        self.store = store
        self.budget_per_run = budget_per_run
        self.warmup_days = warmup_days
        self.thrashing_threshold = thrashing_threshold
        self.deploy_time = deploy_time
        self._escalation_log: list[str] = []

    def run_once(self) -> list[RevalidationResult]:
        now = utc_now()
        candidates = self._enumerate_candidates(now)
        candidates = self._filter_warmup(candidates, now)
        candidates.sort(key=lambda c: self._priority(c), reverse=True)
        results: list[RevalidationResult] = []
        for obj in candidates[: self.budget_per_run]:
            if self._thrashing(obj, now):
                self._escalate_to_human(obj)
                continue
            results.append(self._revalidate(obj))
        return results

    def _enumerate_candidates(self, now: datetime) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for object_id in self._all_bound_object_ids():
            freshness = compute_freshness(self.store, object_id, as_of=now)
            if freshness in (Freshness.STALE, Freshness.AGING):
                obj = self._load_object(object_id)
                candidates.append(
                    _Candidate(
                        object_id=object_id,
                        freshness=freshness,
                        last_validated_at=getattr(obj, "last_validated_at", None) if obj else None,
                        prior_output=obj,
                    )
                )
        return candidates

    def _filter_warmup(
        self, candidates: list[_Candidate], now: datetime
    ) -> list[_Candidate]:
        if self.deploy_time is None:
            return candidates
        cutoff = self.deploy_time + timedelta(days=self.warmup_days)
        if now < cutoff:
            return []
        return candidates

    def _priority(self, candidate: _Candidate) -> float:
        score = 0.0
        if candidate.freshness == Freshness.STALE:
            score += 10.0
        elif candidate.freshness == Freshness.AGING:
            score += 5.0
        if candidate.last_validated_at is not None:
            age = (utc_now() - _ensure_tz(candidate.last_validated_at)).total_seconds()
            score += min(age / 86400.0, 30.0)
        else:
            score += 15.0
        return score

    def _thrashing(self, candidate: _Candidate, now: datetime) -> bool:
        revals = self.store.list_revalidations(candidate.object_id)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = 0
        for r in revals:
            count += 1
        if count >= self.thrashing_threshold:
            recent_count = len(revals)
            if recent_count >= self.thrashing_threshold:
                return True
        return False

    def _escalate_to_human(self, candidate: _Candidate) -> None:
        logger.warning(
            "Thrashing detected for object %s — escalating to human review",
            candidate.object_id,
        )
        self._escalation_log.append(candidate.object_id)

    def _revalidate(self, candidate: _Candidate) -> RevalidationResult:
        method = self._canonical_revalidation_method_for(candidate)
        if method is not None:
            output = method(candidate.prior_output)
            if self._materially_differs(output, candidate.prior_output):
                result = RevalidationResult(
                    object_id=candidate.object_id,
                    outcome="disagreement",
                    prior_tier=_tier_of(candidate.prior_output),
                    new_tier=_tier_of(output),
                    ledger_entry_id="",
                )
                self.store.insert_revalidation(result)
                return result

        result = RevalidationResult(
            object_id=candidate.object_id,
            outcome="confirmed",
            prior_tier=_tier_of(candidate.prior_output),
            new_tier=_tier_of(candidate.prior_output),
            ledger_entry_id="",
        )
        self.store.insert_revalidation(result)
        return result

    def _canonical_revalidation_method_for(
        self, candidate: _Candidate
    ) -> Optional[Callable]:
        try:
            from noosphere.methods._registry import REGISTRY
            spec, fn = REGISTRY.get("revalidate_object")
            return fn
        except Exception:
            return None

    def _materially_differs(self, output: Any, prior: Any) -> bool:
        if output is None or prior is None:
            return output is not prior
        out_tier = _tier_of(output)
        prior_tier = _tier_of(prior)
        if out_tier != prior_tier:
            return True
        out_text = getattr(output, "text", None)
        prior_text = getattr(prior, "text", None)
        if out_text is not None and prior_text is not None:
            return out_text != prior_text
        return False

    def _all_bound_object_ids(self) -> list[str]:
        try:
            from sqlmodel import select
            from noosphere.store import StoredObjectPolicyBinding

            with self.store.session() as s:
                rows = s.exec(select(StoredObjectPolicyBinding)).all()
                return list({r.object_id for r in rows})
        except Exception:
            return []

    def _load_object(self, object_id: str) -> Any:
        from noosphere.decay.policies import _resolve_object
        return _resolve_object(self.store, object_id)


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _tier_of(obj: Any) -> str:
    if obj is None:
        return "unknown"
    ct = getattr(obj, "confidence_tier", None)
    if ct is not None:
        return ct.value if hasattr(ct, "value") else str(ct)
    return "unknown"
