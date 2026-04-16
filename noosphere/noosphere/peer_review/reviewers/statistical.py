from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry

_MIN_SAMPLE_SIZE = 30
_CRITICAL_SAMPLE_SIZE = 10


@register_method(
    name="review_statistical",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether uncertainty is honestly quantified and sample size is sufficient",
    rationale="Statistical validity underlies confidence in any quantitative conclusion",
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
    cal = context.get("calibration_data", {})

    sample_size = cal.get("sample_size")
    if sample_size is not None:
        if sample_size < _CRITICAL_SAMPLE_SIZE:
            findings.append(Finding(
                severity="blocker",
                category="insufficient_n",
                detail=f"Sample size {sample_size} is below critical threshold ({_CRITICAL_SAMPLE_SIZE})",
                evidence=[f"n={sample_size}", f"threshold={_CRITICAL_SAMPLE_SIZE}"],
                suggested_action="Collect more data before drawing conclusions",
            ))
        elif sample_size < _MIN_SAMPLE_SIZE:
            findings.append(Finding(
                severity="major",
                category="insufficient_n",
                detail=f"Sample size {sample_size} is below recommended minimum ({_MIN_SAMPLE_SIZE})",
                evidence=[f"n={sample_size}", f"recommended_min={_MIN_SAMPLE_SIZE}"],
                suggested_action="Increase sample size or explicitly qualify the limitation",
            ))

    if cal and not cal.get("confidence_interval"):
        findings.append(Finding(
            severity="minor",
            category="underquantified_uncertainty",
            detail="No confidence interval provided for the estimate",
            evidence=["confidence_interval=missing"],
            suggested_action="Report confidence intervals alongside point estimates",
        ))

    expected_confidence = cal.get("expected_confidence")
    if expected_confidence is not None:
        delta = abs(conclusion.confidence - expected_confidence)
        if delta > 0.3:
            findings.append(Finding(
                severity="major",
                category="miscalibrated_discount",
                detail=f"Stated confidence {conclusion.confidence:.2f} diverges from calibrated estimate {expected_confidence:.2f}",
                evidence=[f"stated={conclusion.confidence}", f"calibrated={expected_confidence}", f"delta={delta:.2f}"],
                suggested_action="Align confidence with calibration data or justify the discrepancy",
            ))
        elif delta > 0.15:
            findings.append(Finding(
                severity="minor",
                category="miscalibrated_discount",
                detail=f"Stated confidence {conclusion.confidence:.2f} differs from calibrated estimate {expected_confidence:.2f}",
                evidence=[f"stated={conclusion.confidence}", f"calibrated={expected_confidence}", f"delta={delta:.2f}"],
                suggested_action="Review calibration alignment",
            ))

    return findings


class StatisticalReviewer(Reviewer):
    name = "statistical"
    bias_profile = BiasProfile(
        name="statistical",
        prior="Is the uncertainty honestly quantified? Is sample size sufficient?",
        known_blindspots=[
            "Applies frequentist thresholds that may not suit Bayesian workflows",
            "Cannot detect subtle p-hacking or selective reporting",
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


_registry.register(StatisticalReviewer)
