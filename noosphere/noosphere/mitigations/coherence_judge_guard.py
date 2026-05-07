"""Post-hoc validation that the LLM judge cites real prior-layer numbers."""

from __future__ import annotations

from noosphere.models import LLMJudgeVerdictPacket, SixLayerScore

_LAYER_ATTRS: dict[str, tuple[str, ...]] = {
    "s1_consistency": ("s1_consistency", "consistency"),
    "s2_argumentation": ("s2_argumentation", "argumentation"),
    "s3_probabilistic": ("s3_probabilistic", "probabilistic"),
    "s4_geometric": ("s4_geometric", "geometric"),
    "s5_compression": ("s5_compression", "information"),
}


def _prior_layer_value(prior: SixLayerScore, layer: str) -> float | None:
    for attr in _LAYER_ATTRS.get(layer, ()):
        try:
            return float(getattr(prior, attr))
        except AttributeError:
            continue
    return None


def judge_cited_scores_match_prior(
    pkt: LLMJudgeVerdictPacket,
    prior: SixLayerScore,
    *,
    tol: float = 5e-3,
) -> bool:
    """Reject judge packets that mis-quote prior automation (social-engineering surface)."""
    for ref in pkt.cited_prior_scores:
        expected = _prior_layer_value(prior, ref.layer)
        if expected is None:
            return False
        if abs(expected - float(ref.value)) > tol:
            return False
    return True
