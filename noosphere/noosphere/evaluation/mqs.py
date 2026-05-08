"""Methodology Quality Score (MQS): operational form of the five working
criteria from THE_META_METHOD.md.

Each Conclusion that has at least one MethodologyProfile gets an MQS row with
five sub-scores in [0,1], an LLM-or-stub-judged evidence blob per sub-score,
and a composite that uses Domain Sensitivity as a multiplicative gate.

The composite formula and sub-score rubrics are documented in
docs/methods/MQS_Specification.md. The doc and this module are kept in sync
by scripts/check_mqs_doc_consistency.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

from pydantic import BaseModel, Field, field_validator


MQS_SCHEMA = "theseus.mqs.v1"
PROMPT_VERSION = "mqs-prompt-v1.0"

# Mirrored verbatim by docs/methods/MQS_Specification.md and verified by
# scripts/check_mqs_doc_consistency.py.
COMPOSITE_FORMULA = (
    "domain_sensitivity * mean(progressivity, severity, aim_method_fit, compressibility)"
)

SUBSCORE_WEIGHTS: dict[str, float] = {
    "progressivity": 0.25,
    "severity": 0.25,
    "aim_method_fit": 0.25,
    "compressibility": 0.25,
}

_DECISION_RULE_RE = re.compile(
    r"\b(if [a-z]+.*?then |we will |we'll |exit if |by [0-9]{4}|by q[1-4] |"
    r"check back |trigger |would falsif|will revisit)",
    re.IGNORECASE,
)
_EVIDENCE_STR_CAP = 600


class MqsJudge(Protocol):
    """LLM-judge contract. Tests pass a stub; production wires the real LLM."""

    def judge(self, *, criterion: str, prompt: dict[str, Any]) -> dict[str, Any]:
        """Return a dict with at least {"score": float in [0,1], "rationale": str}."""
        ...


@dataclass
class StubMqsJudge:
    """Deterministic judge used by tests and by the no-LLM backfill path.

    `responses` lets a test pin a per-criterion score; otherwise every call
    returns `default_score` with rationale "stub".
    """

    responses: dict[str, dict[str, Any]] | None = None
    default_score: float = 0.5

    def judge(self, *, criterion: str, prompt: dict[str, Any]) -> dict[str, Any]:
        if self.responses and criterion in self.responses:
            return self.responses[criterion]
        return {"score": self.default_score, "rationale": "stub"}


class MethodologyProfileSummary(BaseModel):
    """Slimmed-down view of MethodologyProfile fields the scorer reads."""

    pattern_type: str = ""
    title: str = ""
    summary: str = ""
    reasoning_moves: list[str] = Field(default_factory=list)
    transfer_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class MqsInput(BaseModel):
    """Everything the scorer needs about a conclusion to produce an MQS."""

    conclusion_id: str
    conclusion_text: str = ""
    rationale: str = ""
    topic_hint: str = ""
    profiles: list[MethodologyProfileSummary] = Field(default_factory=list)
    forecast_count: int = 0
    has_check_back_date: bool = False
    dissent_claim_count: int = 0

    # Track-record coupling (prompt 02). Caller looks up the relevant
    # `MethodTrackRecord` row(s) for this conclusion's domain via
    # `noosphere.evaluation.method_track_record.severity_ceiling_for` and
    # passes the resulting cap here. None means "no track record available
    # / no cap"; a value caps `score_severity` from above so that methods
    # with thin or poor track records cannot project high severity onto
    # new conclusions in their domain.
    severity_track_record_ceiling: Optional[float] = None

    # Drift coupling (prompt 04 + composition prompt). Multiplicative
    # penalty in (0, 1] applied to the Severity sub-score AFTER the
    # track-record ceiling. Callers derive this from the *inherited*
    # drift state across the method's composition DAG via
    # `noosphere.methods.composition.severity_penalty_multiplier_with_inheritance`,
    # NOT from the leaf state alone — a method whose composed dependency
    # is drifting must inherit that risk. 1.0 means "no penalty"
    # (default). Documented in docs/methods/MQS_Specification.md §
    # Drift coupling.
    severity_drift_penalty: float = 1.0

    # Peer-review objection coupling (prompt 21). Severity-weighted
    # aggregate of the swarm's objections, computed via
    # `noosphere.peer_review.severity.aggregate`. Replaces the prior
    # "flat objection count" feed: ten low-severity nitpicks no longer
    # have the same impact as two high-severity structural objections.
    # Multiplicative on the Severity sub-score after drift; 1.0 means
    # no objections / no penalty.
    objection_severity_penalty: float = 1.0
    objection_blocking: bool = False
    objection_high_count: int = 0
    objection_medium_count: int = 0
    objection_low_count: int = 0
    objection_weighted_count: float = 0.0

    # Domain-bounds coupling (prompt 06). When the orchestrator has
    # already checked the conclusion against the method's declared
    # ``DomainBound``, it surfaces the verdict here so the MQS scorer
    # can gate Domain Sensitivity deterministically rather than asking
    # the LLM judge to "guess in-domain".
    #
    #   * ``"in_bounds"`` — no gate; ``score_domain_sensitivity`` runs
    #     the LLM judge and the deterministic floor as before.
    #   * ``"edge_case"`` — soft cap at 0.4 on the sub-score, regardless
    #     of the judge's number, and the composite remains continuous.
    #   * ``"out_of_bounds"`` — hard zero on the sub-score, which
    #     multiplicatively gates the composite to 0 by construction
    #     of ``COMPOSITE_FORMULA``.
    #
    # ``None`` means "no bound declared / not checked" — preserves the
    # legacy behavior so untouched call sites continue to work.
    domain_bound_verdict: Optional[str] = None
    domain_bound_margin: Optional[float] = None
    domain_bound_revision_id: Optional[str] = None


_EDGE_CASE_DOMAIN_CEILING = 0.4


class SubScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence")
    @classmethod
    def _cap_strings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _cap_evidence(value)


class MethodologyQualityScore(BaseModel):
    """Operational form of the five meta-method criteria for one conclusion."""

    schema_: str = Field(default=MQS_SCHEMA, alias="schema")
    conclusion_id: str
    progressivity: SubScore
    severity: SubScore
    aim_method_fit: SubScore
    compressibility: SubScore
    domain_sensitivity: SubScore
    composite: float = Field(ge=0.0, le=1.0)
    composite_formula: str = COMPOSITE_FORMULA
    model_name: str = "stub"
    prompt_version: str = PROMPT_VERSION
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True}


def _cap_evidence(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_EVIDENCE_STR_CAP]
    if isinstance(value, list):
        return [_cap_evidence(item) for item in value]
    if isinstance(value, dict):
        return {k: _cap_evidence(v) for k, v in value.items()}
    return value


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(x)))


def _decision_rule_phrase_count(text: str) -> int:
    return len(_DECISION_RULE_RE.findall(text or ""))


def _aggregate_profile_lists(
    profiles: Iterable[MethodologyProfileSummary],
    field: str,
) -> list[str]:
    out: list[str] = []
    for p in profiles:
        out.extend(getattr(p, field, []) or [])
    return out


def score_progressivity(input_data: MqsInput) -> SubScore:
    """Deterministic. Reads forecast count, check-back, decision-rule phrases."""
    text = f"{input_data.conclusion_text} {input_data.rationale}"
    rule_phrases = _decision_rule_phrase_count(text)
    forecasts = max(0, int(input_data.forecast_count))
    has_check_back = bool(input_data.has_check_back_date)

    if has_check_back and forecasts >= 2 and rule_phrases >= 1:
        score = 1.00
    elif (has_check_back and forecasts >= 1) or forecasts >= 2:
        score = 0.85
    elif has_check_back or forecasts >= 1:
        score = 0.65
    elif rule_phrases >= 1:
        score = 0.40
    else:
        score = 0.00

    return SubScore(
        score=score,
        evidence={
            "rule": "progressivity_v1",
            "forecast_count": forecasts,
            "has_check_back_date": has_check_back,
            "decision_rule_phrases": rule_phrases,
        },
    )


def score_severity(input_data: MqsInput, judge: MqsJudge) -> SubScore:
    failure_modes = _aggregate_profile_lists(input_data.profiles, "failure_modes")
    dissent = max(0, int(input_data.dissent_claim_count))

    floor = min(1.0, 0.15 * len(failure_modes) + 0.10 * dissent)

    judged = judge.judge(
        criterion="severity",
        prompt={
            "conclusion": input_data.conclusion_text,
            "failure_modes": failure_modes,
            "assumptions": _aggregate_profile_lists(input_data.profiles, "assumptions"),
            "dissent_claim_count": dissent,
        },
    )
    llm_score = _clamp01(judged.get("score", 0.0))
    score = max(floor, llm_score)

    capped = False
    if not failure_modes and dissent == 0:
        score = min(score, 0.35)
        capped = True

    track_record_ceiling = input_data.severity_track_record_ceiling
    track_record_capped = False
    if track_record_ceiling is not None:
        ceiling = _clamp01(track_record_ceiling)
        if score > ceiling:
            score = ceiling
            track_record_capped = True

    # Drift penalty: multiplicative on the score, applied AFTER the
    # ceiling so that a method whose track record was already capped
    # gets penalized further still when it is actively drifting.
    drift_penalty = _clamp01(float(input_data.severity_drift_penalty))
    if drift_penalty < 1.0:
        score = score * drift_penalty

    # Objection penalty: severity-weighted aggregate from the
    # peer-review swarm. Two unresolved high-severity objections drop
    # the score below the publish bar; ten low-severity nitpicks do
    # not. Applied after the drift penalty so it composes
    # multiplicatively with both gates.
    objection_penalty = _clamp01(float(input_data.objection_severity_penalty))
    if objection_penalty < 1.0:
        score = score * objection_penalty

    return SubScore(
        score=score,
        evidence={
            "rule": "severity_v1",
            "deterministic_floor": round(floor, 4),
            "llm_score": round(llm_score, 4),
            "llm_rationale": str(judged.get("rationale", "")),
            "no_failure_modes_cap": capped,
            "track_record_ceiling": (
                None if track_record_ceiling is None else round(track_record_ceiling, 4)
            ),
            "track_record_capped": track_record_capped,
            "drift_penalty": round(drift_penalty, 4),
            "drift_penalty_applied": drift_penalty < 1.0,
            "objection_penalty": round(objection_penalty, 4),
            "objection_penalty_applied": objection_penalty < 1.0,
            "objection_blocking": bool(input_data.objection_blocking),
            "objection_high_count": int(input_data.objection_high_count),
            "objection_medium_count": int(input_data.objection_medium_count),
            "objection_low_count": int(input_data.objection_low_count),
            "objection_weighted_count": round(
                float(input_data.objection_weighted_count), 4
            ),
        },
    )


def _topic_in_targets(topic_hint: str, targets: list[str]) -> bool:
    if not topic_hint:
        return True
    needle = topic_hint.strip().lower()
    if not needle:
        return True
    root = re.split(r"\W+", needle)[0]
    if not root:
        return True
    return any(root in (t or "").lower() for t in targets)


def score_aim_method_fit(input_data: MqsInput, judge: MqsJudge) -> SubScore:
    transfer_targets = _aggregate_profile_lists(input_data.profiles, "transfer_targets")
    pattern_types = [p.pattern_type for p in input_data.profiles]

    judged = judge.judge(
        criterion="aim_method_fit",
        prompt={
            "conclusion": input_data.conclusion_text,
            "topic_hint": input_data.topic_hint,
            "transfer_targets": transfer_targets,
            "pattern_types": pattern_types,
        },
    )
    score = _clamp01(judged.get("score", 0.0))

    penalty = 0.0
    if input_data.topic_hint and not _topic_in_targets(
        input_data.topic_hint, transfer_targets
    ):
        penalty = 0.10
        score = max(0.0, score - penalty)

    return SubScore(
        score=score,
        evidence={
            "rule": "aim_method_fit_v1",
            "llm_score": round(_clamp01(judged.get("score", 0.0)), 4),
            "llm_rationale": str(judged.get("rationale", "")),
            "topic_hint": input_data.topic_hint,
            "transfer_targets": transfer_targets,
            "topic_outside_targets_penalty": penalty,
        },
    )


def score_compressibility(input_data: MqsInput, judge: MqsJudge) -> SubScore:
    assumptions = _aggregate_profile_lists(input_data.profiles, "assumptions")
    n = len(assumptions)

    judged = judge.judge(
        criterion="compressibility",
        prompt={
            "assumptions": assumptions,
            "reasoning_moves": _aggregate_profile_lists(
                input_data.profiles, "reasoning_moves"
            ),
        },
    )
    decorative = int(judged.get("decorative_count", 0) or 0)
    decorative = max(0, min(decorative, n))
    effective_n = max(1, n - decorative)

    base = 1.0 / (1.0 + max(0, effective_n - 1) * 0.25)
    score = _clamp01(base)

    return SubScore(
        score=score,
        evidence={
            "rule": "compressibility_v1",
            "assumption_count": n,
            "decorative_count": decorative,
            "effective_n": effective_n,
            "llm_rationale": str(judged.get("rationale", "")),
        },
    )


def score_domain_sensitivity(input_data: MqsInput, judge: MqsJudge) -> SubScore:
    failure_modes = _aggregate_profile_lists(input_data.profiles, "failure_modes")
    transfer_targets = _aggregate_profile_lists(input_data.profiles, "transfer_targets")

    # Declarative bound override: when the orchestrator has already
    # checked the conclusion against the method's ``DomainBound``, the
    # verdict is the source of truth — we don't ask the LLM to second-
    # guess it. ``out_of_bounds`` forces 0, which gates the composite
    # to 0 via the multiplicative formula. ``edge_case`` caps the
    # sub-score so it can't dominate the composite.
    bound_verdict = input_data.domain_bound_verdict
    if bound_verdict == "out_of_bounds":
        return SubScore(
            score=0.0,
            evidence={
                "rule": "domain_sensitivity_v1",
                "domain_bound_verdict": "out_of_bounds",
                "domain_bound_margin": (
                    None
                    if input_data.domain_bound_margin is None
                    else round(float(input_data.domain_bound_margin), 6)
                ),
                "domain_bound_revision_id": input_data.domain_bound_revision_id,
                "gated_to_zero": True,
            },
        )

    judged = judge.judge(
        criterion="domain_sensitivity",
        prompt={
            "conclusion": input_data.conclusion_text,
            "topic_hint": input_data.topic_hint,
            "failure_modes": failure_modes,
            "transfer_targets": transfer_targets,
        },
    )
    raw = judged.get("score", None)
    if raw is None:
        # Backfill default: uncertain, not failed.
        score = 0.5
        used_default = True
    else:
        score = _clamp01(raw)
        used_default = False

    floor = 0.10 if not failure_modes else 0.0
    score = max(score, floor)

    edge_case_capped = False
    if bound_verdict == "edge_case" and score > _EDGE_CASE_DOMAIN_CEILING:
        score = _EDGE_CASE_DOMAIN_CEILING
        edge_case_capped = True

    return SubScore(
        score=score,
        evidence={
            "rule": "domain_sensitivity_v1",
            "llm_score": None if used_default else round(_clamp01(raw), 4),
            "llm_rationale": str(judged.get("rationale", "")),
            "no_failure_modes_floor": floor,
            "used_uncertain_default": used_default,
            "domain_bound_verdict": bound_verdict,
            "domain_bound_margin": (
                None
                if input_data.domain_bound_margin is None
                else round(float(input_data.domain_bound_margin), 6)
            ),
            "domain_bound_revision_id": input_data.domain_bound_revision_id,
            "edge_case_capped": edge_case_capped,
        },
    )


def composite_score(
    *,
    progressivity: float,
    severity: float,
    aim_method_fit: float,
    compressibility: float,
    domain_sensitivity: float,
) -> float:
    mean_other = (
        SUBSCORE_WEIGHTS["progressivity"] * _clamp01(progressivity)
        + SUBSCORE_WEIGHTS["severity"] * _clamp01(severity)
        + SUBSCORE_WEIGHTS["aim_method_fit"] * _clamp01(aim_method_fit)
        + SUBSCORE_WEIGHTS["compressibility"] * _clamp01(compressibility)
    )
    return _clamp01(_clamp01(domain_sensitivity) * mean_other)


def score_conclusion(
    input_data: MqsInput,
    *,
    judge: Optional[MqsJudge] = None,
    model_name: str = "stub",
    prompt_version: str = PROMPT_VERSION,
) -> MethodologyQualityScore:
    """Produce a complete MQS for one conclusion. Composable with the peer-
    review swarm: callers may inject a real LLM judge or pass `judge=None` to
    use the deterministic stub (used by the backfill CLI when no LLM is
    configured)."""
    judge_ = judge or StubMqsJudge()

    prog = score_progressivity(input_data)
    sev = score_severity(input_data, judge_)
    fit = score_aim_method_fit(input_data, judge_)
    comp = score_compressibility(input_data, judge_)
    dom = score_domain_sensitivity(input_data, judge_)

    composite = composite_score(
        progressivity=prog.score,
        severity=sev.score,
        aim_method_fit=fit.score,
        compressibility=comp.score,
        domain_sensitivity=dom.score,
    )

    return MethodologyQualityScore(
        conclusion_id=input_data.conclusion_id,
        progressivity=prog,
        severity=sev,
        aim_method_fit=fit,
        compressibility=comp,
        domain_sensitivity=dom,
        composite=composite,
        model_name=model_name,
        prompt_version=prompt_version,
    )


def evidence_payload(score: MethodologyQualityScore) -> dict[str, Any]:
    """Build the JSON blob persisted in `MethodologyQualityScore.evidence`.

    Stable shape so a human reviewer can contest a sub-score and so the doc
    consistency check can verify keys."""
    return {
        "schema": MQS_SCHEMA,
        "composite_formula": COMPOSITE_FORMULA,
        "subscore_weights": SUBSCORE_WEIGHTS,
        "progressivity": score.progressivity.evidence,
        "severity": score.severity.evidence,
        "aim_method_fit": score.aim_method_fit.evidence,
        "compressibility": score.compressibility.evidence,
        "domain_sensitivity": score.domain_sensitivity.evidence,
    }


def evidence_payload_json(score: MethodologyQualityScore) -> str:
    return json.dumps(evidence_payload(score), sort_keys=True, default=str)


__all__ = [
    "COMPOSITE_FORMULA",
    "MQS_SCHEMA",
    "PROMPT_VERSION",
    "SUBSCORE_WEIGHTS",
    "MethodologyProfileSummary",
    "MethodologyQualityScore",
    "MqsInput",
    "MqsJudge",
    "StubMqsJudge",
    "SubScore",
    "composite_score",
    "evidence_payload",
    "evidence_payload_json",
    "score_aim_method_fit",
    "score_compressibility",
    "score_conclusion",
    "score_domain_sensitivity",
    "score_progressivity",
    "score_severity",
]
