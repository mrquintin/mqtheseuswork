"""
Coherence layer 6 — LLM meta-judge with citation-enforced prior-layer scores.
"""

from __future__ import annotations

import json
import re
from pydantic import ValidationError

from noosphere.llm import LLMClient
from noosphere.models import (
    Claim,
    CoherenceVerdict,
    JudgePriorScoreRef,
    LLMJudgeVerdictPacket,
    SixLayerScore,
)
from noosphere.observability import get_logger

logger = get_logger(__name__)

# Explanation must mention each cited layer using at least one alias.
_LAYER_ALIASES: dict[str, tuple[str, ...]] = {
    "s1_consistency": ("s1_consistency", "s1", "consistency", "nli"),
    "s2_argumentation": ("s2_argumentation", "s2", "argumentation", "dung"),
    "s3_probabilistic": ("s3_probabilistic", "s3", "probabilistic", "kolmogorov"),
    "s4_geometric": ("s4_geometric", "s4", "geometry", "hoyer", "embedding"),
    "s5_compression": ("s5_compression", "s5", "compression", "information"),
}


def explanation_cites_prior_layers(
    explanation: str, cited: list[JudgePriorScoreRef]
) -> bool:
    low = explanation.lower()
    for ref in cited:
        aliases = _LAYER_ALIASES.get(ref.layer, (ref.layer,))
        if not any(a.lower() in low for a in aliases):
            return False
        # Require the numeric value (or close string) to appear — discourages empty citations.
        val_s = f"{ref.value:.3f}".rstrip("0").rstrip(".")
        if val_s not in explanation and f"{ref.value:.2f}" not in explanation:
            if f"{ref.value:.1f}" not in explanation:
                return False
    return True


def _parse_json_object(raw: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("no_json_object")
    return json.loads(m.group(0))


def _build_user_prompt(
    a: Claim, b: Claim, prior: SixLayerScore, neighbor_note: str = ""
) -> str:
    return (
        f"Claim A ({a.id}): {a.text}\n"
        f"Claim B ({b.id}): {b.text}\n"
        f"{neighbor_note}\n"
        "Prior layer scores (use these exact keys in cited_prior_scores):\n"
        f"  s1_consistency: {prior.s1_consistency:.4f}\n"
        f"  s2_argumentation: {prior.s2_argumentation:.4f}\n"
        f"  s3_probabilistic: {prior.s3_probabilistic:.4f}\n"
        f"  s4_geometric: {prior.s4_geometric:.4f}\n"
        f"  s5_compression: {prior.s5_compression:.4f}\n"
        "\nReturn JSON only with keys: verdict (cohere|contradict|unresolved), "
        "confidence (0-1), explanation (plain English, must reference at least two "
        "prior scores by layer name AND include their numeric values inline), "
        "cited_prior_scores: array of {{layer, value}} with layer one of "
        "s1_consistency, s2_argumentation, s3_probabilistic, s4_geometric, s5_compression "
        "and value matching the numbers above."
    )


def run_llm_judge(
    llm: LLMClient,
    a: Claim,
    b: Claim,
    prior_scores: SixLayerScore,
    *,
    neighbor_note: str = "",
) -> LLMJudgeVerdictPacket:
    """
    Call the LLM judge with schema validation; retry once if citations are invalid.
    """
    system = (
        "You arbitrate coherence between two claims using prior automated scores. "
        "You must ground your explanation in at least two distinct prior scores "
        "and quote their numeric values in the explanation text."
    )
    user = _build_user_prompt(a, b, prior_scores, neighbor_note=neighbor_note)
    last_err: str = ""
    for attempt in range(2):
        raw = llm.complete(system=system, user=user, max_tokens=700, temperature=0.0)
        try:
            data = _parse_json_object(raw)
            data["verdict"] = CoherenceVerdict(str(data["verdict"]).lower())
            pkt = LLMJudgeVerdictPacket.model_validate(data)
            if not explanation_cites_prior_layers(pkt.explanation, pkt.cited_prior_scores):
                raise ValueError("citation_mismatch")
            return pkt
        except (ValueError, KeyError, json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)
            logger.warning(
                "llm_judge_parse_failed",
                attempt=attempt,
                error=last_err,
            )
            user = (
                _build_user_prompt(a, b, prior_scores, neighbor_note=neighbor_note)
                + "\n\nYour previous answer failed validation: "
                f"{last_err}. Fix JSON; ensure explanation names layers and repeats "
                "at least two numeric score values exactly as given."
            )
    raise RuntimeError(f"LLM judge failed after retry: {last_err}")
