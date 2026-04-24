from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.humility import HumilityReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        reasoning="Test reasoning",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_appropriate_hedging():
    reviewer = HumilityReviewer()
    report = reviewer.review(
        _conclusion(
            text="The data may suggest a correlation, but further research is needed.",
            reasoning="While the sample appears to show a trend, we are limited by sample size.",
            confidence=0.6,
        ),
        {},
    )
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "humility"


def test_suppressed_unresolved_produces_minor():
    reviewer = HumilityReviewer()
    ctx = {
        "unresolved_questions": ["What about confounding variables?"],
        "acknowledged_limitations": [],
    }
    report = reviewer.review(
        _conclusion(
            text="This analysis suggests a possible link.",
            reasoning="Further research may be needed.",
            confidence=0.7,
        ),
        ctx,
    )
    assert any(
        f.severity == "minor" and f.category == "suppressed_unresolved"
        for f in report.findings
    )


def test_overclaim_produces_blocker():
    reviewer = HumilityReviewer()
    report = reviewer.review(
        _conclusion(
            text="This conclusively proves the hypothesis without question.",
            reasoning="The evidence is irrefutable and the result is guaranteed.",
            confidence=0.99,
        ),
        {},
    )
    assert any(
        f.severity == "blocker" and f.category == "overclaim"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
