from __future__ import annotations

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.reviewers.evidential import EvidentialReviewer


def _conclusion(**kw):
    defaults = dict(
        text="Test conclusion",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.8,
    )
    defaults.update(kw)
    return Conclusion(**defaults)


def test_clean_pass_with_strong_evidence():
    reviewer = EvidentialReviewer()
    ctx = {
        "nli_scores": {"claim_1": 0.9, "claim_2": 0.85},
        "retrieval_hits": [
            {"claim_id": "claim_1", "text": "Supporting", "score": 0.9, "supports_conclusion": True},
        ],
    }
    report = reviewer.review(_conclusion(claims_used=["claim_1", "claim_2"]), ctx)
    assert report.overall_verdict == "accept"
    assert len(report.findings) == 0
    assert report.reviewer == "evidential"


def test_weak_entailment_produces_minor_finding():
    reviewer = EvidentialReviewer()
    ctx = {
        "nli_scores": {"claim_1": 0.4},
        "retrieval_hits": [],
    }
    report = reviewer.review(_conclusion(claims_used=["claim_1"]), ctx)
    assert any(
        f.severity == "minor" and f.category == "citation_mismatch"
        for f in report.findings
    )


def test_very_low_entailment_produces_blocker():
    reviewer = EvidentialReviewer()
    ctx = {
        "nli_scores": {"claim_1": 0.1},
        "retrieval_hits": [
            {"claim_id": "claim_1", "text": "Weak", "score": 0.1, "supports_conclusion": True},
        ],
    }
    report = reviewer.review(_conclusion(claims_used=["claim_1"]), ctx)
    assert any(f.severity == "blocker" for f in report.findings)
    assert report.overall_verdict == "reject"
