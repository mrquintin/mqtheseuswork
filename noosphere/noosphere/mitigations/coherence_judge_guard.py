"""Post-hoc validation that the LLM judge cites real prior-layer numbers."""

from __future__ import annotations

from noosphere.models import LLMJudgeVerdictPacket, SixLayerScore

_LAYER_ATTR: dict[str, str] = {
    "s1_consistency": "s1_consistency",
    "s2_argumentation": "s2_argumentation",
    "s3_probabilistic": "s3_probabilistic",
    "s4_geometric": "s4_geometric",
    "s5_compression": "s5_compression",
}


def judge_cited_scores_match_prior(
    pkt: LLMJudgeVerdictPacket,
    prior: SixLayerScore,
    *,
    tol: float = 5e-3,
) -> bool:
    """Reject judge packets that mis-quote prior automation (social-engineering surface)."""
    for ref in pkt.cited_prior_scores:
        attr = _LAYER_ATTR.get(ref.layer)
        if attr is None:
            return False
        expected = float(getattr(prior, attr))
        if abs(expected - float(ref.value)) > tol:
            return False
    return True
