"""Quarterly self-critique pass over the firm's published corpus.

The peer-review swarm (see :mod:`noosphere.peer_review.swarm`) runs at
publish time. This module runs the *retrospective* counterpart: every
quarter, each published article is re-read by a fresh adversarial
reviewer whose only job is to identify what aged poorly, what
citations have shifted, what predictions resolved against the firm,
and what blind spots are now visible.

Three constraints shape the design:

1. **Fresh evidence only.** The reviewer is given evidence the firm
   gathered *after* publication. It does not get to use evidence that
   was available at publish time and then complain — that would be a
   cheap unfair-surprise gotcha and would muddy the calibration story.
2. **Original text is immutable.** Findings whose action is
   ``addend`` produce a dated addendum block, never a stealth rewrite.
   Only the revision engine (prompt 16) edits the original article
   text; this module produces ``Addendum`` rows.
3. **Different reviewer configuration.** Self-critique must use a
   reviewer config distinct from the original publication's swarm —
   otherwise the two passes share blind spots and the retrospective
   pass cannot catch what the original missed.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Verdict / action vocabulary ─────────────────────────────────────


class SelfCritiqueVerdict(str, Enum):
    STILL_HOLDS = "still holds"
    WEAKENED = "weakened"
    CONTRADICTED = "contradicted by new evidence"
    NO_LONGER_SUPPORTED = "no longer supported"


class SelfCritiqueAction(str, Enum):
    REVISE = "revise"
    ADDEND = "addend"
    DISMISS = "dismiss"


# Mapping of verdict → recommended default action. Used both as a
# starting point for the LLM judge and as a fallback when a judge
# response omits ``recommended_action``.
DEFAULT_ACTION_FOR_VERDICT: dict[SelfCritiqueVerdict, SelfCritiqueAction] = {
    SelfCritiqueVerdict.STILL_HOLDS: SelfCritiqueAction.DISMISS,
    SelfCritiqueVerdict.WEAKENED: SelfCritiqueAction.ADDEND,
    SelfCritiqueVerdict.CONTRADICTED: SelfCritiqueAction.REVISE,
    SelfCritiqueVerdict.NO_LONGER_SUPPORTED: SelfCritiqueAction.REVISE,
}


# ── Inputs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence (a citation, observation, or resolution).

    The self-critique reviewer cares about three metadata fields:
    ``source_id`` (so the "now / then" pair can be matched), ``summary``
    (what the firm thinks this evidence says), and ``observed_at`` —
    used by the scheduler to refuse evidence that pre-dates the
    article's publication.
    """

    source_id: str
    summary: str
    observed_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)


# ── Outputs ─────────────────────────────────────────────────────────


class SelfCritiqueFinding(BaseModel):
    """One claim-level finding from a self-critique pass.

    The shape matches the spec verbatim: a claim is paired with the
    evidence that supported it at publish time and the evidence that
    supports (or contradicts) it now, plus a verdict from the four-way
    vocabulary and a recommended_action that the founder can override
    in triage.
    """

    claim: str
    was_supported_by: list[str] = Field(default_factory=list)
    now_supported_by: list[str] = Field(default_factory=list)
    verdict: SelfCritiqueVerdict
    recommended_action: SelfCritiqueAction
    rationale: str = ""

    model_config = ConfigDict(use_enum_values=False, extra="forbid")


class SelfCritiqueReport(BaseModel):
    """Aggregate output of a single self-critique run."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    article_id: str
    reviewer: str
    findings: list[SelfCritiqueFinding] = Field(default_factory=list)
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reviewer_config: str = ""

    model_config = ConfigDict(extra="forbid")


# ── Reviewer ────────────────────────────────────────────────────────


JudgeFn = Callable[
    [str, str, str, list[EvidenceItem], list[EvidenceItem]],
    list[dict[str, Any]],
]
"""Signature: (article_id, article_text, reviewer_config_label,
original_evidence, evidence_now) -> list of raw finding dicts."""


# Reviewer-config label used when the operator does not specify their
# own. The string is recorded on every report so the firm can prove,
# after the fact, that self-critique used a configuration distinct
# from the original publication swarm.
DEFAULT_REVIEWER_CONFIG = "self-critique:v1"


SELF_CRITIQUE_SYSTEM_PROMPT = (
    "You are an adversarial retrospective reviewer for a knowledge "
    "firm. The firm published the article below some time ago. Your "
    "job is to identify, claim by claim, what the firm got wrong, "
    "what aged poorly, and what is now embarrassing. Use ONLY the "
    "evidence-now items below — never penalise the firm for evidence "
    "they could not have seen at publish time. For each claim that "
    "has shifted, return: claim text; the source ids that supported "
    "it then; the source ids that bear on it now; one of {still "
    "holds, weakened, contradicted by new evidence, no longer "
    "supported}; one of {revise, addend, dismiss}; a one-paragraph "
    "rationale. Output strict JSON with key 'findings'."
)


class SelfCritiqueReviewer:
    """Adversarial reviewer that re-reads a published article.

    The reviewer is intentionally decoupled from the LLM provider
    layer: it accepts a ``judge_fn`` callable so tests can inject a
    deterministic stub and so the operator can swap in a different
    provider configuration from the publication swarm. The default
    ``judge_fn`` raises ``RuntimeError`` — operators must wire in a
    real judge before running against production articles.
    """

    name = "self_critique"

    def __init__(
        self,
        *,
        judge_fn: Optional[JudgeFn] = None,
        reviewer_config: str = DEFAULT_REVIEWER_CONFIG,
    ) -> None:
        self.judge_fn = judge_fn or _default_judge_fn
        self.reviewer_config = reviewer_config

    def review(
        self,
        *,
        article_id: str,
        article_text: str,
        original_evidence_at_publish_time: list[EvidenceItem],
        evidence_now: list[EvidenceItem],
        published_at: Optional[datetime] = None,
    ) -> SelfCritiqueReport:
        """Run one self-critique pass.

        ``evidence_now`` is filtered against ``published_at`` so the
        reviewer never sees pre-publication evidence — the constraint
        in the prompt header is enforced by the caller, not asked of
        the LLM.
        """

        gated_now = _filter_post_publication(evidence_now, published_at)
        raw = self.judge_fn(
            article_id,
            article_text,
            self.reviewer_config,
            list(original_evidence_at_publish_time),
            gated_now,
        )
        findings = [coerce_finding(item) for item in raw]
        return SelfCritiqueReport(
            article_id=article_id,
            reviewer=self.name,
            findings=findings,
            reviewer_config=self.reviewer_config,
        )


def _default_judge_fn(
    _article_id: str,
    _article_text: str,
    _reviewer_config: str,
    _then: list[EvidenceItem],
    _now: list[EvidenceItem],
) -> list[dict[str, Any]]:
    raise RuntimeError(
        "SelfCritiqueReviewer requires an explicit judge_fn — wire one "
        "in via the constructor (e.g. an LLM provider adapter or, in "
        "tests, a deterministic stub)."
    )


def _filter_post_publication(
    evidence: list[EvidenceItem],
    published_at: Optional[datetime],
) -> list[EvidenceItem]:
    if published_at is None:
        return list(evidence)
    cutoff = _ensure_aware(published_at)
    return [e for e in evidence if _ensure_aware(e.observed_at) >= cutoff]


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def coerce_finding(raw: dict[str, Any]) -> SelfCritiqueFinding:
    """Coerce a loose LLM/test payload into a strict :class:`SelfCritiqueFinding`."""

    verdict_raw = raw.get("verdict", SelfCritiqueVerdict.STILL_HOLDS.value)
    if isinstance(verdict_raw, SelfCritiqueVerdict):
        verdict = verdict_raw
    else:
        verdict = SelfCritiqueVerdict(str(verdict_raw))

    action_raw = raw.get("recommended_action")
    if isinstance(action_raw, SelfCritiqueAction):
        action = action_raw
    elif action_raw is None or action_raw == "":
        action = DEFAULT_ACTION_FOR_VERDICT[verdict]
    else:
        action = SelfCritiqueAction(str(action_raw))

    return SelfCritiqueFinding(
        claim=str(raw.get("claim", "")).strip(),
        was_supported_by=list(raw.get("was_supported_by", []) or []),
        now_supported_by=list(raw.get("now_supported_by", []) or []),
        verdict=verdict,
        recommended_action=action,
        rationale=str(raw.get("rationale", "")).strip(),
    )


# ── Addendum lifecycle ──────────────────────────────────────────────


class AddendumStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    DISMISSED = "dismissed"


class Addendum(BaseModel):
    """A dated "later view" attached to a published article.

    The original article body is immutable — the public page renders
    the addendum below the article as visibly later content. Status
    progresses ``pending → published`` (founder accepted the addend
    action) or ``pending → dismissed`` (founder rejected with reason).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    article_id: str
    article_slug: str = ""
    finding_id: str = ""
    summary: str
    body: str = ""
    status: AddendumStatus = AddendumStatus.PENDING
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    published_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    dismissed_reason: str = ""
    reviewer_config: str = ""

    model_config = ConfigDict(extra="forbid")


def addendum_from_finding(
    finding: SelfCritiqueFinding,
    *,
    article_id: str,
    article_slug: str = "",
    finding_id: str = "",
    reviewer_config: str = "",
) -> Addendum:
    """Build a pending :class:`Addendum` from an ``addend`` finding.

    Refuses non-``addend`` findings — a contradicted claim must go
    through the revision engine, not the addendum path.
    """

    if finding.recommended_action is not SelfCritiqueAction.ADDEND:
        raise ValueError(
            f"addendum_from_finding requires recommended_action=addend; "
            f"got {finding.recommended_action.value!r}"
        )
    summary = finding.rationale or finding.claim
    body = (
        f"Claim: {finding.claim}\n\n"
        f"Verdict: {finding.verdict.value}.\n\n"
        f"{finding.rationale}".strip()
    )
    return Addendum(
        article_id=article_id,
        article_slug=article_slug,
        finding_id=finding_id,
        summary=summary,
        body=body,
        reviewer_config=reviewer_config,
    )


def publish_addendum(
    addendum: Addendum,
    *,
    now: Optional[datetime] = None,
) -> Addendum:
    """Transition a pending addendum to ``published``.

    Returns a *new* :class:`Addendum` instance — the inputs are kept
    immutable so a caller that already wrote the pending row to a
    store can compare before/after.
    """

    if addendum.status is not AddendumStatus.PENDING:
        raise ValueError(
            f"publish_addendum requires status=pending; got {addendum.status.value!r}"
        )
    return addendum.model_copy(
        update={
            "status": AddendumStatus.PUBLISHED,
            "published_at": now or datetime.now(timezone.utc),
        }
    )


def dismiss_addendum(
    addendum: Addendum,
    *,
    reason: str,
    now: Optional[datetime] = None,
) -> Addendum:
    """Transition a pending addendum to ``dismissed`` with a reason.

    A dismissal without a reason is rejected — per spec, dismissals
    are recorded explicitly so the corpus can be audited later for
    "things the firm chose not to address".
    """

    if addendum.status is not AddendumStatus.PENDING:
        raise ValueError(
            f"dismiss_addendum requires status=pending; got {addendum.status.value!r}"
        )
    if not reason.strip():
        raise ValueError("dismiss_addendum requires a non-empty reason")
    return addendum.model_copy(
        update={
            "status": AddendumStatus.DISMISSED,
            "dismissed_at": now or datetime.now(timezone.utc),
            "dismissed_reason": reason.strip(),
        }
    )


# ── Helper: render the finding back to a JSON dict ──────────────────


def finding_to_dict(finding: SelfCritiqueFinding) -> dict[str, Any]:
    """JSON-friendly representation used when persisting to the
    attention queue.

    The enums round-trip via their string values so a downstream
    consumer can read the row without importing this module.
    """

    return {
        "claim": finding.claim,
        "was_supported_by": list(finding.was_supported_by),
        "now_supported_by": list(finding.now_supported_by),
        "verdict": finding.verdict.value,
        "recommended_action": finding.recommended_action.value,
        "rationale": finding.rationale,
    }


def report_to_dict(report: SelfCritiqueReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "article_id": report.article_id,
        "reviewer": report.reviewer,
        "completed_at": report.completed_at.isoformat(),
        "reviewer_config": report.reviewer_config,
        "findings": [finding_to_dict(f) for f in report.findings],
    }


def report_to_json(report: SelfCritiqueReport) -> str:
    return json.dumps(report_to_dict(report), sort_keys=True)


__all__ = [
    "Addendum",
    "AddendumStatus",
    "DEFAULT_ACTION_FOR_VERDICT",
    "DEFAULT_REVIEWER_CONFIG",
    "EvidenceItem",
    "JudgeFn",
    "SELF_CRITIQUE_SYSTEM_PROMPT",
    "SelfCritiqueAction",
    "SelfCritiqueFinding",
    "SelfCritiqueReport",
    "SelfCritiqueReviewer",
    "SelfCritiqueVerdict",
    "addendum_from_finding",
    "coerce_finding",
    "dismiss_addendum",
    "finding_to_dict",
    "publish_addendum",
    "report_to_dict",
    "report_to_json",
]
