"""Peer-review independence: reviewer outputs must not depend on invocation order."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from noosphere.models import (
    Actor,
    Conclusion,
    ConfidenceTier,
    Finding,
    ReviewReport,
)
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review.reviewers import register, _REVIEWERS
from noosphere.peer_review.swarm import SwarmOrchestrator
from noosphere.store import Store


class _AlphaReviewer(Reviewer):
    name = "alpha"
    bias_profile = BiasProfile(
        name="alpha", prior="Skeptical of causal claims", known_blindspots=["confirmation bias"]
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        return ReviewReport(
            report_id=f"alpha-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=[
                Finding(
                    severity="minor",
                    category="methodology",
                    detail="Weak causal link",
                    evidence=["p>0.05"],
                    suggested_action="Add controls",
                )
            ],
            overall_verdict="revise",
            confidence=0.7,
            completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            method_invocation_ids=[],
        )


class _BetaReviewer(Reviewer):
    name = "beta"
    bias_profile = BiasProfile(
        name="beta", prior="Trusts quantitative evidence", known_blindspots=["ecological fallacy"]
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        return ReviewReport(
            report_id=f"beta-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=[],
            overall_verdict="accept",
            confidence=0.9,
            completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            method_invocation_ids=[],
        )


@pytest.fixture(autouse=True)
def _clean_registry():
    _REVIEWERS.clear()
    register(_AlphaReviewer)
    register(_BetaReviewer)
    yield
    _REVIEWERS.clear()


def _make_store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_conclusion(store: Store) -> Conclusion:
    c = Conclusion(
        id=str(uuid.uuid4()),
        text="Test conclusion",
        reasoning="Some reasoning",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    store.put_conclusion(c)
    return c


def test_independence_across_runs():
    store = _make_store()
    conclusion = _seed_conclusion(store)
    orch = SwarmOrchestrator(store)

    report_a = orch.run(conclusion.id)
    alpha_a = [r for r in report_a.reviews if r.reviewer == "alpha"][0]
    beta_a = [r for r in report_a.reviews if r.reviewer == "beta"][0]

    store2 = _make_store()
    store2.put_conclusion(conclusion)
    orch2 = SwarmOrchestrator(store2)
    report_b = orch2.run(conclusion.id)
    alpha_b = [r for r in report_b.reviews if r.reviewer == "alpha"][0]
    beta_b = [r for r in report_b.reviews if r.reviewer == "beta"][0]

    assert alpha_a.overall_verdict == alpha_b.overall_verdict
    assert alpha_a.confidence == alpha_b.confidence
    assert len(alpha_a.findings) == len(alpha_b.findings)

    assert beta_a.overall_verdict == beta_b.overall_verdict
    assert beta_a.confidence == beta_b.confidence
    assert len(beta_a.findings) == len(beta_b.findings)


def test_reviewer_reports_are_stable_with_randomized_order():
    store = _make_store()
    conclusion = _seed_conclusion(store)

    reviewers = [_AlphaReviewer(), _BetaReviewer()]
    random.shuffle(reviewers)

    results = {}
    for r in reviewers:
        report = r.review(conclusion, {})
        results[report.reviewer] = report

    assert results["alpha"].overall_verdict == "revise"
    assert results["beta"].overall_verdict == "accept"
