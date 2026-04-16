"""
Coherence layer 3 — probabilistic commitments via LLM + simple axiom checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import Claim
from noosphere.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ProbabilisticAudit:
    kolmogorov_ok: bool
    violations: list[str]
    extracted: dict[str, Any]


def _modal_to_range(text: str) -> tuple[float, float]:
    t = text.lower()
    if "certain" in t or "definitely" in t:
        return 0.95, 1.0
    if "likely" in t or "probably" in t:
        return 0.55, 0.85
    if "possibly" in t or "might" in t or "may" in t:
        return 0.2, 0.55
    if "unlikely" in t:
        return 0.05, 0.35
    return 0.0, 1.0


def extract_commitments(llm: LLMClient, claim: Claim) -> dict[str, Any]:
    system = "Return JSON only: {\"numeric_probs\":[0-1],\"modal_ranges\":[[low,high],...],\"notes\":str}"
    user = f"Claim: {claim.text}\nAuthor: {claim.speaker.name}\n"
    raw = llm.complete(system=system, user=user, max_tokens=400)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"numeric_probs": [], "modal_ranges": [], "notes": ""}
    return json.loads(m.group(0))


def check_kolmogorov_for_pair(a: Claim, b: Claim, llm: LLMClient | None = None) -> ProbabilisticAudit:
    llm = llm or llm_client_from_settings()
    ea = extract_commitments(llm, a)
    eb = extract_commitments(llm, b)
    nums = [float(x) for x in ea.get("numeric_probs", [])] + [
        float(x) for x in eb.get("numeric_probs", [])
    ]
    violations: list[str] = []
    for p in nums:
        if p < 0 or p > 1:
            violations.append(f"probability_out_of_range:{p}")
    if nums and sum(nums) > 1.0001:
        violations.append("finite_additivity_sum_gt_1")
    ok = not violations
    return ProbabilisticAudit(
        kolmogorov_ok=ok,
        violations=violations,
        extracted={"a": ea, "b": eb},
    )
