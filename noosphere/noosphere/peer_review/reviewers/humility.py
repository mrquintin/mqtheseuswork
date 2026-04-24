from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry

_OVERCLAIM_MARKERS = {
    "proves", "proven", "definitely", "certainly", "indisputably",
    "without question", "guaranteed", "conclusively", "unambiguously",
    "irrefutably",
}

_HEDGING_MARKERS = {
    "may", "might", "suggests", "possibly", "further research",
    "tentatively", "appears to", "limited by", "caveats",
}

_CONSENSUS_PATTERN = re.compile(
    r"\b(consensus|widely accepted|universally agreed|settled science|beyond debate)\b",
    re.IGNORECASE,
)


@register_method(
    name="review_humility",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether unresolved points and open questions are faithfully surfaced",
    rationale="Honest conclusions acknowledge their own limits",
    owner="founder",
    nondeterministic=True,
)
def _execute(input_data: dict[str, Any]) -> dict[str, Any]:
    conclusion: Conclusion = input_data["conclusion"]
    context: dict[str, Any] = input_data.get("context", {})
    findings = _analyze(conclusion, context)
    return _verdict(findings)


def _verdict(findings: list[Finding]) -> dict[str, Any]:
    has_blocker = any(f.severity == "blocker" for f in findings)
    has_major = any(f.severity == "major" for f in findings)
    return {
        "findings": [f.model_dump() for f in findings],
        "verdict": "reject" if has_blocker else "revise" if (has_major or findings) else "accept",
        "confidence": max(0.5, 0.95 - 0.1 * len(findings)),
    }


def _analyze(conclusion: Conclusion, context: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    text = f"{conclusion.text} {conclusion.reasoning}".lower()

    found_overclaim = {
        m for m in _OVERCLAIM_MARKERS
        if re.search(r"\b" + re.escape(m) + r"\b", text)
    }
    if found_overclaim and conclusion.confidence_tier.value != "founder":
        findings.append(Finding(
            severity="blocker",
            category="overclaim",
            detail=f"Absolute certainty language used: {', '.join(sorted(found_overclaim))}",
            evidence=sorted(found_overclaim),
            suggested_action="Qualify claims with appropriate uncertainty",
        ))

    unresolved = context.get("unresolved_questions", [])
    acknowledged = context.get("acknowledged_limitations", [])
    suppressed = [q for q in unresolved if q not in acknowledged]
    if suppressed:
        severity = "major" if len(suppressed) >= 3 else "minor"
        findings.append(Finding(
            severity=severity,
            category="suppressed_unresolved",
            detail=f"{len(suppressed)} unresolved question(s) not acknowledged",
            evidence=suppressed[:5],
            suggested_action="Explicitly list unresolved questions in the conclusion",
        ))

    match = _CONSENSUS_PATTERN.search(text)
    if match:
        findings.append(Finding(
            severity="major",
            category="premature_consensus",
            detail="Claims consensus without citing supporting meta-evidence",
            evidence=[match.group()],
            suggested_action="Cite specific sources supporting the consensus claim or remove it",
        ))

    has_hedging = any(
        re.search(r"\b" + re.escape(m) + r"\b", text) for m in _HEDGING_MARKERS
    )
    if (
        not has_hedging
        and conclusion.confidence_tier.value != "founder"
        and conclusion.confidence > 0.9
    ):
        findings.append(Finding(
            severity="minor",
            category="overclaim",
            detail="High-confidence conclusion with no hedging language",
            evidence=[f"confidence={conclusion.confidence}", "hedging_markers=0"],
            suggested_action="Add appropriate qualifications to the conclusion",
        ))

    return findings


class HumilityReviewer(Reviewer):
    name = "humility"
    bias_profile = BiasProfile(
        name="humility",
        prior="Are unresolved points and open questions faithfully surfaced?",
        known_blindspots=[
            "May penalize confident conclusions that are genuinely well-supported",
            "Keyword-based overclaim detection can miss subtle overclaiming",
        ],
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        result = _execute({"conclusion": conclusion, "context": context})
        findings = [Finding(**f) for f in result["findings"]]
        inv_ids = [_execute.__method_spec__.method_id] if hasattr(_execute, "__method_spec__") else []
        return ReviewReport(
            report_id=f"{self.name}-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=findings,
            overall_verdict=result["verdict"],
            confidence=result["confidence"],
            completed_at=datetime.now(timezone.utc),
            method_invocation_ids=inv_ids,
        )


_registry.register(HumilityReviewer)
