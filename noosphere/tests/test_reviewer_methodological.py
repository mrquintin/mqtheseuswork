from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.methodological import MethodologicalReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_valid_methods():
    reviewer = MethodologicalReviewer()
    ctx = {
        "methods_used": [
            {"name": "extract_claims", "version": "2.0.0", "status": "active"},
        ],
        "method_registry": {"extract_claims": {"latest_version": "2.0.0"}},
    }
    report = reviewer.review(_conclusion(), ctx)
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "methodological"


def test_version_regression_produces_minor_finding():
    reviewer = MethodologicalReviewer()
    ctx = {
        "methods_used": [
            {"name": "extract_claims", "version": "1.0.0", "status": "active"},
        ],
        "method_registry": {"extract_claims": {"latest_version": "2.0.0"}},
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "minor" and f.category == "version_regression"
        for f in report.findings
    )


def test_deprecated_method_produces_blocker():
    reviewer = MethodologicalReviewer()
    ctx = {
        "methods_used": [
            {"name": "old_method", "version": "1.0.0", "status": "deprecated"},
        ],
        "method_registry": {"old_method": {"latest_version": "2.0.0"}},
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "blocker" and f.category == "deprecated_method"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
