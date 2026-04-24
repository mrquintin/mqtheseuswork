from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry

_NLI_MINOR_THRESHOLD = 0.5
_NLI_BLOCKER_THRESHOLD = 0.3
_RETRIEVAL_WEAK_THRESHOLD = 0.25


@register_method(
    name="review_evidential",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether cited evidence actually supports the conclusion claims",
    rationale="Each cited chunk must genuinely entail what the conclusion says it does",
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
    nli_scores = context.get("nli_scores", {})
    retrieval_hits = context.get("retrieval_hits", [])
    cited_ids = set(conclusion.claims_used)

    for claim_id in conclusion.claims_used:
        score = nli_scores.get(claim_id)
        if score is not None:
            if score < _NLI_BLOCKER_THRESHOLD:
                findings.append(Finding(
                    severity="blocker",
                    category="citation_mismatch",
                    detail=f"Cited claim '{claim_id}' has very low entailment (NLI={score:.2f})",
                    evidence=[f"claim_id={claim_id}", f"nli_score={score}"],
                    suggested_action="Remove or replace this citation; it does not support the claim",
                ))
            elif score < _NLI_MINOR_THRESHOLD:
                findings.append(Finding(
                    severity="minor",
                    category="citation_mismatch",
                    detail=f"Cited claim '{claim_id}' has weak entailment (NLI={score:.2f})",
                    evidence=[f"claim_id={claim_id}", f"nli_score={score}"],
                    suggested_action="Strengthen the citation or weaken the claim it supports",
                ))

    counter_evidence = [
        h for h in retrieval_hits
        if not h.get("supports_conclusion", True) and h.get("score", 0) > 0.7
    ]
    uncited_counter = [h for h in counter_evidence if h.get("claim_id") not in cited_ids]
    if uncited_counter:
        findings.append(Finding(
            severity="major",
            category="cherry_picking",
            detail=f"{len(uncited_counter)} high-relevance counter-evidence chunk(s) not cited",
            evidence=[h.get("claim_id", "unknown") for h in uncited_counter[:3]],
            suggested_action="Engage with counter-evidence explicitly",
        ))

    for hit in retrieval_hits:
        cid = hit.get("claim_id", "")
        if cid in cited_ids and hit.get("score", 1.0) < _RETRIEVAL_WEAK_THRESHOLD:
            findings.append(Finding(
                severity="blocker",
                category="load_bearing_on_weak_chunk",
                detail=f"Conclusion depends on low-confidence chunk '{cid}' (score={hit['score']:.2f})",
                evidence=[f"claim_id={cid}", f"retrieval_score={hit['score']}"],
                suggested_action="Find stronger evidence or reduce conclusion confidence",
            ))

    return findings


class EvidentialReviewer(Reviewer):
    name = "evidential"
    bias_profile = BiasProfile(
        name="evidential",
        prior="Does each cited chunk actually support what the conclusion claims?",
        known_blindspots=[
            "Cannot verify evidence outside the corpus",
            "NLI scores may miss domain-specific entailment patterns",
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


_registry.register(EvidentialReviewer)
