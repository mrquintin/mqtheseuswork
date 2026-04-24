from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.replication import ReplicationReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_deterministic_trace():
    reviewer = ReplicationReviewer()
    ctx = {
        "cascade_trace": {
            "declared_inputs": ["input_a", "input_b"],
            "actual_inputs": ["input_a", "input_b"],
            "deterministic": True,
            "replication_success": True,
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "replication"


def test_nondeterministic_without_seed_produces_minor():
    reviewer = ReplicationReviewer()
    ctx = {
        "cascade_trace": {
            "declared_inputs": ["input_a"],
            "actual_inputs": ["input_a"],
            "deterministic": False,
            "seed": None,
            "replication_success": True,
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "minor" and f.category == "non_determinism_without_seed"
        for f in report.findings
    )


def test_replication_failure_produces_blocker():
    reviewer = ReplicationReviewer()
    ctx = {
        "cascade_trace": {
            "declared_inputs": ["input_a"],
            "actual_inputs": ["input_a"],
            "deterministic": True,
            "replication_success": False,
            "original_hash": "abc123",
            "replicated_hash": "def456",
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "blocker" and f.category == "non_replicable"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
