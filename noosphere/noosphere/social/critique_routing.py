"""Open-critique routing — Python side of the bounty + moderation flow.

Outside experts submit structured critiques of specific firm
conclusions through the codex (see
``theseus-codex/src/components/ChallengeThisCta.tsx``). This module is
the noosphere-side bridge: it owns the moderation state machine, the
severity scoring (delegated to :mod:`noosphere.peer_review.severity`),
the bridge to the revision engine (:mod:`noosphere.cascade.revision`),
and the bounty queueing rules.

The module is deliberately Prisma-free so the same code runs in
offline backfills, unit tests, and the codex-side bridge. Persistence
happens through the ``CritiqueWriter`` Protocol; production wires it to
the codex API; tests use :class:`InMemoryCritiqueWriter`.

Moderation ladder
-----------------
``pending``     — submitted, untriaged.
``accepted``    — published with credit. Severity ``high`` queues a bounty
                  in ``pending_founder_confirmation`` (no payout fires).
``partial``     — private discussion. Not published.
``rejected``    — closed with a reason.
``archived``    — audit-only.

Bounty rule (load-bearing)
--------------------------
The codex never sends money. ``accept_critique(...)`` queues a payout
row; the *only* way to move the bounty out of
``pending_founder_confirmation`` is :func:`confirm_bounty`. The same
rule is enforced on the codex side
(``src/lib/critiquesApi.ts::confirmBountyPayout``).

Lineage
-------
A critic's contribution remains visible even if a later revision moves
the firm's position elsewhere. The :class:`CritiqueLineage` dataclass
records what changed and who caused it; revisions append to the
lineage, they don't overwrite it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional, Protocol

from noosphere.cascade.revision import RevisionInput
from noosphere.peer_review.severity import (
    SeverityInputs,
    SeverityLabel,
    score_objection,
)


# ── public vocabulary ────────────────────────────────────────────────


CritiqueStatus = Literal[
    "pending",
    "accepted",
    "partial",
    "rejected",
    "archived",
]

BountyStatus = Literal[
    "pending_founder_confirmation",
    "confirmed",
    "cancelled",
]

PayoutMode = Literal["self", "charity"]

# Default bounty for an accepted high-severity critique. The codex
# stores the per-critique amount; this is the seed value used when the
# founder accepts without overriding.
DEFAULT_BOUNTY_USD = 500


# ── data ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CritiqueSubmission:
    """A structured critique filed against a specific conclusion.

    Mirrors the columns of the Prisma ``CritiqueSubmission`` row. We
    keep this Prisma-free so the noosphere test harness stays fast and
    Node-free.
    """

    submission_id: str
    organization_id: str
    article_slug: str
    target_claim: str
    counter_evidence: str
    derivation_method: str
    citations: str
    submitter_email: str
    display_name: str = ""
    public_url: str = ""
    bio: str = ""
    orcid: str = ""
    published_conclusion_id: Optional[str] = None
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def credit_label(self) -> str:
        """Public-facing display name for the hall-of-fame.

        Same rule as ``critiqueDisplayName`` on the codex side.
        """

        if self.display_name.strip():
            return self.display_name.strip()
        if not self.submitter_email:
            return "Anonymous"
        local, _, _ = self.submitter_email.partition("@")
        return local or "Anonymous"


@dataclass(frozen=True)
class BountyPayout:
    """A queued bounty payout for an accepted high-severity critique.

    Lives in ``pending_founder_confirmation`` until
    :func:`confirm_bounty` runs. The codex never sends money — this
    record only tells the firm's payouts pipeline that a payout is
    eligible.
    """

    payout_id: str
    submission_id: str
    amount_usd: int = DEFAULT_BOUNTY_USD
    payout_mode: PayoutMode = "self"
    destination: str = ""
    status: BountyStatus = "pending_founder_confirmation"
    cancellation_note: str = ""
    confirmed_at: Optional[datetime] = None
    external_ref: str = ""


@dataclass(frozen=True)
class CritiqueDecision:
    """Snapshot of a moderator decision.

    ``severity_label`` and ``severity_value`` are populated only when
    ``status == 'accepted'``. The decision is the source of truth for
    the codex moderation queue and is written through ``CritiqueWriter``.
    """

    submission_id: str
    status: CritiqueStatus
    moderator_note: str = ""
    severity_label: SeverityLabel = "low"
    severity_value: float = 0.0
    decided_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    bounty: Optional[BountyPayout] = None
    revision_event_id: Optional[str] = None


@dataclass(frozen=True)
class LineageEntry:
    """One entry in a critique's lineage trail.

    The lineage records *who* caused *what* to change *when*. Revisions
    append entries; nothing in this module overwrites prior entries.
    """

    at: datetime
    kind: str  # "accepted" | "revision_routed" | "addendum_published" | "later_revision"
    note: str
    actor: str  # critic credit label or "firm"


@dataclass
class CritiqueLineage:
    """Mutable lineage trail per critique submission.

    The trail is append-only — keeping the original critic in the
    record even when a later revision moves the firm's position
    elsewhere. The ``trail`` order is chronological.
    """

    submission_id: str
    credit_label: str
    trail: list[LineageEntry] = field(default_factory=list)

    def append(self, entry: LineageEntry) -> None:
        self.trail.append(entry)

    def credits(self) -> list[str]:
        """Distinct actors in the lineage, oldest first."""

        seen: list[str] = []
        for entry in self.trail:
            if entry.actor not in seen:
                seen.append(entry.actor)
        return seen


# ── persistence Protocols ───────────────────────────────────────────


class CritiqueWriter(Protocol):
    """Pluggable persistence for moderation decisions and lineage."""

    def write_decision(self, decision: CritiqueDecision) -> None: ...

    def write_bounty(self, payout: BountyPayout) -> None: ...

    def write_lineage(self, lineage: CritiqueLineage) -> None: ...


@dataclass
class InMemoryCritiqueWriter:
    """Test/dev double for :class:`CritiqueWriter`."""

    decisions: list[CritiqueDecision] = field(default_factory=list)
    bounties: dict[str, BountyPayout] = field(default_factory=dict)
    lineages: dict[str, CritiqueLineage] = field(default_factory=dict)

    def write_decision(self, decision: CritiqueDecision) -> None:
        self.decisions.append(decision)

    def write_bounty(self, payout: BountyPayout) -> None:
        self.bounties[payout.submission_id] = payout

    def write_lineage(self, lineage: CritiqueLineage) -> None:
        self.lineages[lineage.submission_id] = CritiqueLineage(
            submission_id=lineage.submission_id,
            credit_label=lineage.credit_label,
            trail=list(lineage.trail),
        )

    def latest_decision(self, submission_id: str) -> Optional[CritiqueDecision]:
        for d in reversed(self.decisions):
            if d.submission_id == submission_id:
                return d
        return None


# ── helpers: severity ────────────────────────────────────────────────


def score_severity(
    submission: CritiqueSubmission,
    inputs: SeverityInputs,
) -> tuple[SeverityLabel, float]:
    """Run the severity rubric for an inbound critique.

    The structural inputs (cascade weight, claim centrality, curated
    failure-mode match, source credibility) are caller-provided —
    production wires them through the cascade graph; tests pass the
    intended bracket directly. Returns ``(label, value)`` for the
    codex to persist.
    """

    severity = score_objection(inputs, rationale=f"critique:{submission.submission_id}")
    return severity.label, severity.value


def is_bounty_eligible(decision: CritiqueDecision) -> bool:
    """A critique is bounty-eligible iff it is accepted AND severity=high."""

    return decision.status == "accepted" and decision.severity_label == "high"


# ── flow: accept / partial / reject ──────────────────────────────────


def accept_critique(
    submission: CritiqueSubmission,
    *,
    severity_inputs: SeverityInputs,
    moderator_note: str = "",
    queue_bounty: bool = True,
    bounty_amount_usd: int = DEFAULT_BOUNTY_USD,
    payout_mode: PayoutMode = "self",
    bounty_destination: str = "",
    writer: Optional[CritiqueWriter] = None,
    lineage: Optional[CritiqueLineage] = None,
) -> CritiqueDecision:
    """Mark a critique accepted and (when severity=high) queue a bounty.

    The bounty sits in ``pending_founder_confirmation`` until
    :func:`confirm_bounty` is called. The codex never sends money;
    this function only records intent.

    The lineage gets an ``accepted`` entry crediting the critic. If the
    caller hands in an existing lineage the entry is appended;
    otherwise a fresh lineage is created.
    """

    label, value = score_severity(submission, severity_inputs)
    decision = CritiqueDecision(
        submission_id=submission.submission_id,
        status="accepted",
        moderator_note=moderator_note,
        severity_label=label,
        severity_value=value,
    )

    bounty: Optional[BountyPayout] = None
    if queue_bounty and label == "high":
        bounty = BountyPayout(
            payout_id=f"bounty_{submission.submission_id}",
            submission_id=submission.submission_id,
            amount_usd=max(0, int(bounty_amount_usd)),
            payout_mode=payout_mode,
            destination=bounty_destination.strip(),
            status="pending_founder_confirmation",
        )
        decision = replace(decision, bounty=bounty)

    lineage = _ensure_lineage(submission, lineage)
    lineage.append(
        LineageEntry(
            at=decision.decided_at,
            kind="accepted",
            note=f"severity={label}",
            actor=submission.credit_label(),
        )
    )

    if writer is not None:
        writer.write_decision(decision)
        if bounty is not None:
            writer.write_bounty(bounty)
        writer.write_lineage(lineage)

    return decision


def mark_partial(
    submission: CritiqueSubmission,
    *,
    moderator_note: str,
    writer: Optional[CritiqueWriter] = None,
    lineage: Optional[CritiqueLineage] = None,
) -> CritiqueDecision:
    """Mark a critique as a partial match — private discussion, no publish."""

    decision = CritiqueDecision(
        submission_id=submission.submission_id,
        status="partial",
        moderator_note=moderator_note,
    )
    lineage = _ensure_lineage(submission, lineage)
    lineage.append(
        LineageEntry(
            at=decision.decided_at,
            kind="partial",
            note=moderator_note,
            actor="firm",
        )
    )
    if writer is not None:
        writer.write_decision(decision)
        writer.write_lineage(lineage)
    return decision


def reject_critique(
    submission: CritiqueSubmission,
    *,
    moderator_note: str,
    writer: Optional[CritiqueWriter] = None,
    lineage: Optional[CritiqueLineage] = None,
) -> CritiqueDecision:
    """Mark a critique rejected. ``moderator_note`` is shown to the critic."""

    decision = CritiqueDecision(
        submission_id=submission.submission_id,
        status="rejected",
        moderator_note=moderator_note,
    )
    lineage = _ensure_lineage(submission, lineage)
    lineage.append(
        LineageEntry(
            at=decision.decided_at,
            kind="rejected",
            note=moderator_note,
            actor="firm",
        )
    )
    if writer is not None:
        writer.write_decision(decision)
        writer.write_lineage(lineage)
    return decision


# ── flow: bounty confirmation (founder gate) ─────────────────────────


def confirm_bounty(
    payout: BountyPayout,
    *,
    founder_confirmed: bool,
    external_ref: str = "",
) -> BountyPayout:
    """Move a queued bounty out of ``pending_founder_confirmation``.

    This is the *only* path that flips a bounty to ``confirmed``. The
    ``founder_confirmed`` argument is a hard precondition — the call
    raises ``PermissionError`` if it is False, mirroring the codex
    server-action that requires the founder to be authenticated.
    """

    if payout.status != "pending_founder_confirmation":
        raise ValueError(
            f"Bounty {payout.payout_id} is not pending — status={payout.status}"
        )
    if not founder_confirmed:
        raise PermissionError(
            "Bounty payout requires founder confirmation. The codex never "
            "sends money without it."
        )
    return replace(
        payout,
        status="confirmed",
        confirmed_at=datetime.now(timezone.utc),
        external_ref=external_ref.strip(),
    )


def cancel_bounty(payout: BountyPayout, *, note: str) -> BountyPayout:
    """Cancel a pending bounty. Confirmed bounties cannot be cancelled here."""

    if payout.status == "confirmed":
        raise ValueError("Confirmed bounties cannot be cancelled in noosphere")
    return replace(payout, status="cancelled", cancellation_note=note.strip())


# ── flow: bridge to revision + addendum ──────────────────────────────


def to_revision_input(
    submission: CritiqueSubmission,
    *,
    claim_id: str,
    weight: float = -0.5,
) -> RevisionInput:
    """Convert a critique into a :class:`RevisionInput` for prompt 16.

    ``weight`` defaults to ``-0.5`` because a critique is, by
    definition, evidence that contradicts the targeted claim. Callers
    can override; the cascade engine clamps to [-1, 1].
    """

    return RevisionInput(
        claim_id=claim_id,
        new_evidence=submission.counter_evidence,
        weight=weight,
    )


def record_revision_in_lineage(
    submission: CritiqueSubmission,
    lineage: CritiqueLineage,
    *,
    revision_event_id: str,
    summary: str = "",
    writer: Optional[CritiqueWriter] = None,
) -> CritiqueLineage:
    """Append a revision entry. Critic credit stays in the lineage."""

    lineage.append(
        LineageEntry(
            at=datetime.now(timezone.utc),
            kind="revision_routed",
            note=summary or f"event={revision_event_id}",
            actor=submission.credit_label(),
        )
    )
    if writer is not None:
        writer.write_lineage(lineage)
    return lineage


def record_later_revision(
    lineage: CritiqueLineage,
    *,
    summary: str,
    writer: Optional[CritiqueWriter] = None,
) -> CritiqueLineage:
    """Record a *later* firm-driven revision that moves the position again.

    The original critic stays credited (the prior entries are not
    overwritten). The new entry's actor is ``firm`` so the public
    surface can show "the firm later moved further" without erasing
    the critic.
    """

    lineage.append(
        LineageEntry(
            at=datetime.now(timezone.utc),
            kind="later_revision",
            note=summary,
            actor="firm",
        )
    )
    if writer is not None:
        writer.write_lineage(lineage)
    return lineage


# ── helpers ──────────────────────────────────────────────────────────


def _ensure_lineage(
    submission: CritiqueSubmission,
    lineage: Optional[CritiqueLineage],
) -> CritiqueLineage:
    if lineage is not None:
        return lineage
    return CritiqueLineage(
        submission_id=submission.submission_id,
        credit_label=submission.credit_label(),
    )


def credits_for_article(
    lineages: Iterable[CritiqueLineage],
    *,
    article_slug: str,
    submissions_by_id: dict[str, CritiqueSubmission],
) -> list[str]:
    """All critic credits attached (via accepted critiques) to one article.

    Stable across later revisions — the lineage is append-only, so a
    revision that overrides the critic's position does not remove the
    critic from the credit list.
    """

    out: list[str] = []
    for lineage in lineages:
        sub = submissions_by_id.get(lineage.submission_id)
        if sub is None or sub.article_slug != article_slug:
            continue
        for credit in lineage.credits():
            if credit and credit != "firm" and credit not in out:
                out.append(credit)
    return out


__all__ = [
    "BOUNTY_DEFAULT_USD",
    "BountyPayout",
    "BountyStatus",
    "CritiqueDecision",
    "CritiqueLineage",
    "CritiqueStatus",
    "CritiqueSubmission",
    "CritiqueWriter",
    "DEFAULT_BOUNTY_USD",
    "InMemoryCritiqueWriter",
    "LineageEntry",
    "PayoutMode",
    "accept_critique",
    "cancel_bounty",
    "confirm_bounty",
    "credits_for_article",
    "is_bounty_eligible",
    "mark_partial",
    "record_later_revision",
    "record_revision_in_lineage",
    "reject_critique",
    "score_severity",
    "to_revision_input",
]


# Alias kept for callers that match the codex constant name.
BOUNTY_DEFAULT_USD = DEFAULT_BOUNTY_USD
