from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry


@register_method(
    name="review_replication",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether a conclusion can be re-derived from its stated inputs alone",
    rationale="Reproducibility is a prerequisite for trust in any derived conclusion",
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
    trace = context.get("cascade_trace", {})

    declared_inputs = set(trace.get("declared_inputs", []))
    actual_inputs = set(trace.get("actual_inputs", []))
    hidden = actual_inputs - declared_inputs
    if hidden:
        findings.append(Finding(
            severity="major",
            category="hidden_input",
            detail=f"{len(hidden)} undeclared input(s) detected in the derivation",
            evidence=sorted(hidden),
            suggested_action="Declare all inputs explicitly in the method specification",
        ))

    if not trace.get("deterministic", True) and trace.get("seed") is None:
        findings.append(Finding(
            severity="minor",
            category="non_determinism_without_seed",
            detail="Non-deterministic method used without a fixed seed",
            evidence=["deterministic=False", "seed=None"],
            suggested_action="Provide a seed value to enable reproducible runs",
        ))

    if trace.get("replication_success") is False:
        findings.append(Finding(
            severity="blocker",
            category="non_replicable",
            detail="Re-derivation from stated inputs produced a different result",
            evidence=[
                f"original={trace.get('original_hash', 'unknown')}",
                f"replicated={trace.get('replicated_hash', 'unknown')}",
            ],
            suggested_action="Investigate divergence; check for hidden state or non-determinism",
        ))

    return findings


class ReplicationReviewer(Reviewer):
    name = "replication"
    bias_profile = BiasProfile(
        name="replication",
        prior="Can I re-derive this conclusion from the stated inputs alone?",
        known_blindspots=[
            "Cannot detect semantic equivalence of differently-formatted outputs",
            "Single-attempt replication may miss intermittent failures",
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


_registry.register(ReplicationReviewer)
