"""Rebuttal enforcement: blockers block publication; reject_with_reason requires human."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from noosphere.models import (
    Actor,
    Finding,
    Rebuttal,
    ReviewReport,
    SwarmReport,
)
from noosphere.peer_review.rebuttal import BlockedPublicationError, RebuttalRegistry
from noosphere.store import Store


def _make_store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _blocker_finding() -> Finding:
    return Finding(
        severity="blocker",
        category="validity",
        detail="Core assumption unverified",
        evidence=["No source cited"],
        suggested_action="Provide citation",
    )


def _report(conclusion_id: str, finding: Finding) -> ReviewReport:
    return ReviewReport(
        report_id=str(uuid.uuid4()),
        reviewer="test-reviewer",
        conclusion_id=conclusion_id,
        findings=[finding],
        overall_verdict="reject",
        confidence=0.95,
        completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        method_invocation_ids=[],
    )


def test_unresolved_blocker_blocks_advance():
    store = _make_store()
    cid = "conclusion-1"
    finding = _blocker_finding()
    report = _report(cid, finding)
    store.insert_review_report(report)

    registry = RebuttalRegistry(store)
    with pytest.raises(BlockedPublicationError):
        registry.advance_to_publication(cid)


def test_agent_cannot_reject_with_reason():
    store = _make_store()
    registry = RebuttalRegistry(store)
    agent_actor = Actor(kind="agent", id="agent-1", display_name="Bot")
    rebuttal = Rebuttal(
        finding_id="rpt:0",
        form="reject_with_reason",
        rationale="I disagree",
        by_actor=agent_actor,
    )
    with pytest.raises(PermissionError, match="human actor"):
        registry.submit_rebuttal("rpt:0", rebuttal, report_id="rpt")


def test_human_can_reject_with_reason():
    store = _make_store()
    cid = "conclusion-2"
    finding = _blocker_finding()
    report = _report(cid, finding)
    store.insert_review_report(report)

    registry = RebuttalRegistry(store)
    human_actor = Actor(kind="human", id="user-1", display_name="Reviewer")
    finding_id = f"{report.report_id}:0"
    rebuttal = Rebuttal(
        finding_id=finding_id,
        form="reject_with_reason",
        rationale="Finding is based on outdated data",
        by_actor=human_actor,
    )
    registry.submit_rebuttal(finding_id, rebuttal, report_id=report.report_id)

    registry.advance_to_publication(cid)


def test_required_rebuttals_lists_major_and_blocker():
    cid = "conclusion-3"
    blocker = _blocker_finding()
    major = Finding(
        severity="major",
        category="methodology",
        detail="Sample size too small",
        evidence=["n=5"],
        suggested_action="Increase sample",
    )
    minor = Finding(
        severity="minor",
        category="style",
        detail="Awkward phrasing",
        evidence=[],
        suggested_action="Rephrase",
    )
    report = ReviewReport(
        report_id="rpt-3",
        reviewer="test",
        conclusion_id=cid,
        findings=[blocker, major, minor],
        overall_verdict="revise",
        confidence=0.8,
        completed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        method_invocation_ids=[],
    )
    swarm = SwarmReport(conclusion_id=cid, reviews=[report], rebuttals=[])

    store = _make_store()
    registry = RebuttalRegistry(store)
    required = registry.required_rebuttals(swarm)
    assert len(required) == 2
    severities = {f.severity for f in required}
    assert severities == {"blocker", "major"}
