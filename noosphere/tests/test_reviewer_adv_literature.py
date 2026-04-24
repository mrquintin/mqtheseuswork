from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.adv_literature import AdvLiteratureReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_supporting_literature():
    reviewer = AdvLiteratureReviewer()
    ctx = {
        "literature_matches": [
            {"title": "Supporting Study", "stance": "supports", "date": "2024-01-15"},
        ],
    }
    report = reviewer.review(_conclusion(), ctx)
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "adv_literature"


def test_outdated_reference_produces_minor():
    reviewer = AdvLiteratureReviewer()
    ctx = {
        "literature_matches": [
            {"title": "Old Study", "stance": "supports", "date": "2000-01-01"},
        ],
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "minor" and f.category == "outdated_reference"
        for f in report.findings
    )


def test_multiple_unaddressed_counter_evidence_produces_blocker():
    reviewer = AdvLiteratureReviewer()
    ctx = {
        "literature_matches": [
            {"title": "Counter A", "stance": "contradicts", "date": "2024-01-15"},
            {"title": "Counter B", "stance": "contradicts", "date": "2024-06-01"},
        ],
        "engaged_counter_titles": [],
    }
    report = reviewer.review(_conclusion(), ctx)
    assert any(
        f.severity == "blocker" and f.category == "unaddressed_counter_evidence"
        for f in report.findings
    )
    assert report.overall_verdict == "reject"
