from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry

_LOADED_TERMS = {
    "obviously", "clearly", "undeniably", "devastating", "catastrophic",
    "absurd", "ridiculous", "trivially", "unquestionably", "indisputable",
}

_NORMATIVE_WORDS = re.compile(
    r"\b(should|must|ought to|need to|has to|have to)\b", re.IGNORECASE
)
_JUSTIFICATION_WORDS = re.compile(
    r"\b(because|since|given that|due to|as a result of)\b", re.IGNORECASE
)

_MOTTE_BAILEY_MARKERS = [
    (re.compile(r"\ball\b.*\bare\b", re.IGNORECASE),
     re.compile(r"\bsome\b.*\bmay\b", re.IGNORECASE)),
    (re.compile(r"\bproves?\b", re.IGNORECASE),
     re.compile(r"\bsuggests?\b", re.IGNORECASE)),
    (re.compile(r"\bcertainly\b", re.IGNORECASE),
     re.compile(r"\bperhaps\b", re.IGNORECASE)),
]


@register_method(
    name="review_rhetorical",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether the argument is rhetorically clean or smuggles moves",
    rationale="Rhetorical sleights undermine the reader's ability to evaluate claims",
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
    text = f"{conclusion.text} {conclusion.reasoning}"
    words = text.lower().split()

    found_loaded = _LOADED_TERMS.intersection(words)
    if found_loaded:
        findings.append(Finding(
            severity="minor",
            category="loaded_term",
            detail=f"Loaded term(s) detected: {', '.join(sorted(found_loaded))}",
            evidence=sorted(found_loaded),
            suggested_action="Replace with neutral language",
        ))

    for sentence in re.split(r"[.!?]", text):
        if _NORMATIVE_WORDS.search(sentence) and not _JUSTIFICATION_WORDS.search(sentence):
            findings.append(Finding(
                severity="major",
                category="hidden_normative",
                detail="Normative claim made without explicit justification",
                evidence=[sentence.strip()[:200]],
                suggested_action="Provide explicit reasoning for normative statements",
            ))
            break

    for strong, weak in _MOTTE_BAILEY_MARKERS:
        if strong.search(text) and weak.search(text):
            findings.append(Finding(
                severity="blocker",
                category="motte_and_bailey",
                detail="Text oscillates between strong and weak versions of the claim",
                evidence=[f"strong_match={strong.pattern}", f"weak_match={weak.pattern}"],
                suggested_action="State the claim at one consistent strength throughout",
            ))
            break

    for eq in context.get("equivocations", []):
        findings.append(Finding(
            severity="major",
            category="equivocation",
            detail=f"Term '{eq['term']}' used with shifting meaning",
            evidence=eq.get("evidence", []),
            suggested_action="Define terms precisely and use them consistently",
        ))

    return findings


class RhetoricalReviewer(Reviewer):
    name = "rhetorical"
    bias_profile = BiasProfile(
        name="rhetorical",
        prior="Is the argument rhetorically clean or does it smuggle moves past the reader?",
        known_blindspots=[
            "Keyword heuristics miss sophisticated rhetorical maneuvers",
            "May flag legitimate emphatic language as loaded",
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


_registry.register(RhetoricalReviewer)
