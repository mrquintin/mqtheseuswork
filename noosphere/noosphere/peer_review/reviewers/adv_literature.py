from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry

_OUTDATED_YEARS = 10


@register_method(
    name="review_adv_literature",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether external literature contains unaddressed counter-evidence",
    rationale="Honest scholarship engages with disagreement in the published record",
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
    literature_matches = context.get("literature_matches", [])
    engaged_titles = set(context.get("engaged_counter_titles", []))
    today = date.today()

    counter_evidence = []
    for match in literature_matches:
        stance = match.get("stance", "neutral")
        title = match.get("title", "unknown")
        pub_date_str = match.get("date", "")

        if stance in ("contradicts", "opposes"):
            counter_evidence.append(match)

        if pub_date_str:
            try:
                pub_date = date.fromisoformat(pub_date_str)
                age_years = (today - pub_date).days / 365.25
                if age_years > _OUTDATED_YEARS:
                    findings.append(Finding(
                        severity="minor",
                        category="outdated_reference",
                        detail=f"Reference '{title}' is {age_years:.0f} years old",
                        evidence=[f"title={title}", f"date={pub_date_str}"],
                        suggested_action="Check for more recent publications on this topic",
                    ))
            except ValueError:
                pass

    unaddressed = [m for m in counter_evidence if m.get("title") not in engaged_titles]
    if unaddressed:
        severity = "blocker" if len(unaddressed) >= 2 else "major"
        findings.append(Finding(
            severity=severity,
            category="unaddressed_counter_evidence",
            detail=f"{len(unaddressed)} contradicting source(s) not engaged with",
            evidence=[m.get("title", "unknown") for m in unaddressed[:5]],
            suggested_action="Explicitly address or rebut contradicting literature",
        ))

    return findings


class AdvLiteratureReviewer(Reviewer):
    name = "adv_literature"
    bias_profile = BiasProfile(
        name="adv_literature",
        prior="Does the external literature contain counter-evidence not engaged with?",
        known_blindspots=[
            "Limited to literature already indexed in the system",
            "Cannot assess quality or relevance of counter-evidence itself",
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


_registry.register(AdvLiteratureReviewer)
