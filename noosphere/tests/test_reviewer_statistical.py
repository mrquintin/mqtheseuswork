from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.statistical import StatisticalReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_adequate_statistics():
    reviewer = StatisticalReviewer()
    ctx = {
        "calibration_data": {
            "sample_size": 500,
            "confidence_interval": [0.7, 0.9],
            "expected_confidence": 0.8,
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "statistical"


def test_missing_confidence_interval_produces_minor():
    reviewer = StatisticalReviewer()
    ctx = {
        "calibration_data": {
            "sample_size": 500,
            "expected_confidence": 0.8,
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "minor" and f.category == "underquantified_uncertainty"
        for f in report.findings
    )


def test_tiny_sample_produces_blocker():
    reviewer = StatisticalReviewer()
    ctx = {
        "calibration_data": {
            "sample_size": 3,
            "confidence_interval": [0.1, 0.9],
        },
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "blocker" and f.category == "insufficient_n"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
