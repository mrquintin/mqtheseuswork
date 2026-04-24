from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.rhetorical import RhetoricalReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        reasoning="Test reasoning",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_neutral_language():
    reviewer = RhetoricalReviewer()
    report = reviewer.review(
        _conclusion(
            text="Based on the evidence, we observe a moderate correlation between X and Y.",
            reasoning="The data supports a correlation with r=0.6 because the sample is large enough.",
        ),
        {},
    )
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "rhetorical"


def test_loaded_term_produces_minor():
    reviewer = RhetoricalReviewer()
    report = reviewer.review(
        _conclusion(
            text="This is obviously the correct interpretation.",
            reasoning="The data is clear.",
        ),
        {},
    )
    assert any(
        f.severity == "minor" and f.category == "loaded_term"
        for f in report.findings
    )


def test_motte_and_bailey_produces_blocker():
    reviewer = RhetoricalReviewer()
    report = reviewer.review(
        _conclusion(
            text="This certainly proves that all cases are explained by X.",
            reasoning="Some observations may suggest a limited connection perhaps.",
        ),
        {},
    )
    assert any(
        f.severity == "blocker" and f.category == "motte_and_bailey"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
