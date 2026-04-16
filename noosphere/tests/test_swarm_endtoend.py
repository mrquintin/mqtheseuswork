"""End-to-end: register reviewers, run swarm, submit rebuttals, advance."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from noosphere.models import (
    Actor,
    Conclusion,
    ConfidenceTier,
    Finding,
    Rebuttal,
    ReviewReport,
)
from noosphere.peer_review.rebuttal import BlockedPublicationError, RebuttalRegistry
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review.reviewers import register, _REVIEWERS
from noosphere.peer_review.swarm import SwarmOrchestrator
from noosphere.store import Store


class _StrictReviewer(Reviewer):
    name = "strict"
    bias_profile = BiasProfile(
        name="strict", prior="Demands rigorous evidence", known_blindspots=[]
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        return ReviewReport(
            report_id=f"strict-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=[
                Finding(
                    severity="blocker",
                    category="evidence",
                    detail="Insufficient evidence",
                    evidence=["No RCT"],
                    suggested_action="Run controlled trial",
                )
            ],
            overall_verdict="reject",
            confidence=0.9,
            completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            method_invocation_ids=[],
        )


class _LenientReviewer(Reviewer):
    name = "lenient"
    bias_profile = BiasProfile(
        name="lenient", prior="Accepts observational evidence", known_blindspots=["overconfidence"]
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        return ReviewReport(
            report_id=f"lenient-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=[],
            overall_verdict="accept",
            confidence=0.85,
            completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            method_invocation_ids=[],
        )


@pytest.fixture(autouse=True)
def _clean_registry():
    _REVIEWERS.clear()
    register(_StrictReviewer)
    register(_LenientReviewer)
    yield
    _REVIEWERS.clear()


def _make_store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_conclusion(store: Store) -> Conclusion:
    c = Conclusion(
        id=str(uuid.uuid4()),
        text="Observable correlation implies causation in controlled settings",
        reasoning="Multiple observational studies converge",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.82,
    )
    store.put_conclusion(c)
    return c


def test_endtoend_swarm_and_rebuttal():
    store = _make_store()
    conclusion = _seed_conclusion(store)

    orch = SwarmOrchestrator(store)
    swarm_report = orch.run(conclusion.id)

    assert len(swarm_report.reviews) == 2
    reviewers_seen = {r.reviewer for r in swarm_report.reviews}
    assert reviewers_seen == {"strict", "lenient"}

    registry = RebuttalRegistry(store)
    required = registry.required_rebuttals(swarm_report)
    assert len(required) == 1
    assert required[0].severity == "blocker"

    with pytest.raises(BlockedPublicationError):
        registry.advance_to_publication(conclusion.id)

    strict_report = [r for r in swarm_report.reviews if r.reviewer == "strict"][0]
    finding_id = f"{strict_report.report_id}:0"
    human = Actor(kind="human", id="reviewer-1", display_name="Lead Reviewer")
    rebuttal = Rebuttal(
        finding_id=finding_id,
        form="accept_and_revise",
        rationale="Will add controlled trial data in revision",
        by_actor=human,
    )
    registry.submit_rebuttal(finding_id, rebuttal, report_id=strict_report.report_id)

    registry.advance_to_publication(conclusion.id)


def test_all_reports_persisted_to_store():
    store = _make_store()
    conclusion = _seed_conclusion(store)

    orch = SwarmOrchestrator(store)
    orch.run(conclusion.id)

    stored = store.list_review_reports(conclusion.id)
    assert len(stored) == 2


def test_swarm_report_preserves_all_reviews():
    store = _make_store()
    conclusion = _seed_conclusion(store)

    orch = SwarmOrchestrator(store)
    swarm_report = orch.run(conclusion.id)

    assert len(swarm_report.reviews) == 2
    verdicts = {r.overall_verdict for r in swarm_report.reviews}
    assert "reject" in verdicts
    assert "accept" in verdicts
