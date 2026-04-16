"""Unit tests for calibration scoring helpers."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from noosphere.models import (
    PredictionResolution,
    PredictiveClaim,
    PredictiveClaimStatus,
)
from noosphere.scoring import (
    aggregate_author_domain,
    brier_score,
    discount_conclusion_confidence,
    log_loss_binary,
    prob_mid,
    scoreboard_payload,
)
from noosphere.store import Store


def _pc(
    *,
    author: str = "a1",
    domain: str = "Philosophy",
    lo: float = 0.7,
    hi: float = 0.9,
    status: PredictiveClaimStatus = PredictiveClaimStatus.RESOLVED,
    scoring_eligible: bool = True,
    honest: bool = False,
) -> PredictiveClaim:
    return PredictiveClaim(
        id=str(uuid.uuid4()),
        source_claim_id="c1",
        author_key=author,
        artifact_id="art",
        domains=[domain],
        event_text="e",
        resolution_date=date(2026, 1, 1),
        resolution_criteria_true="t",
        resolution_criteria_false="f",
        prob_low=lo,
        prob_high=hi,
        honest_uncertainty=honest,
        scoring_eligible=scoring_eligible,
        extraction_human_confirmed=True,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _res(pc_id: str, y: int) -> PredictionResolution:
    return PredictionResolution(
        id=str(uuid.uuid4()),
        predictive_claim_id=pc_id,
        outcome=y,  # type: ignore[arg-type]
        resolved_at=datetime.now(timezone.utc),
        justification="test resolution with enough chars",
        evidence_artifact_ids=["ev1"],
        mode="manual",
        resolver_founder_id="f1",
    )


def test_brier_and_logloss() -> None:
    assert abs(brier_score(0.8, 1) - 0.04) < 1e-9
    assert log_loss_binary(0.5, 1) > 0


def test_prob_mid() -> None:
    p = _pc(lo=0.2, hi=0.4)
    assert abs(prob_mid(p) - 0.3) < 1e-9


def test_aggregate_and_discount(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't.db'}"
    st = Store.from_database_url(url)
    p0 = _pc(author="alice", domain="AI", lo=0.75, hi=0.85)
    p1 = _pc(author="alice", domain="AI", lo=0.75, hi=0.85)
    st.put_predictive_claim(p0)
    st.put_predictive_claim(p1)
    st.put_prediction_resolution(_res(p0.id, 1))
    st.put_prediction_resolution(_res(p1.id, 0))
    pm0 = prob_mid(p0)
    agg = aggregate_author_domain(st)
    assert "alice" in agg
    assert "AI" in agg["alice"]
    assert agg["alice"]["AI"]["n"] == 2.0
    mean_b = agg["alice"]["AI"]["mean_brier"]
    expected = (brier_score(pm0, 1) + brier_score(pm0, 0)) / 2
    assert abs(mean_b - expected) < 1e-6

    adj, note = discount_conclusion_confidence(
        st, author_key="alice", domain="AI", stated_confidence=0.8
    )
    assert 0.01 <= adj <= 0.99
    assert "trials=" in note or "insufficient" in note

    sb = scoreboard_payload(st)
    assert "alice" in sb["authors"]


def test_honest_uncertainty_excluded_from_aggregate(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't2.db'}"
    st = Store.from_database_url(url)
    p0 = _pc(author="bob", lo=0.48, hi=0.52, honest=True, scoring_eligible=False)
    st.put_predictive_claim(p0)
    st.put_prediction_resolution(_res(p0.id, 1))
    agg = aggregate_author_domain(st)
    assert agg == {} or "bob" not in agg
