"""Data Subject Request (DSR) handler.

Given an email or other identifier, walks every store the firm holds
and produces a JSON ``everything we have`` report. On confirmation it
also produces an executable deletion plan.

This module backs the firm's GDPR/CCPA-aligned posture: the access
report and the deletion plan are generated *from the same retention
policy table* used by the runner, so there is no parallel definition of
"what we hold" — adding a class of data to ``retention_policies.POLICIES``
automatically makes it discoverable by DSR.

The handler is intentionally read-only by default. ``build_report`` only
queries; ``build_deletion_plan`` describes work to be done; ``execute``
applies it. The execute step requires explicit confirmation by the
caller (CLI flag or operator UI checkbox) — there is no flow that turns
a single API call into bulk deletion.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from noosphere.decay.retention_policies import (
    LifecycleAction,
    all_policies,
    get_policy,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


# ── Adapter shape ────────────────────────────────────────────────────────────


@dataclass
class DSRContext:
    """Adapters the DSR handler uses to find rows tied to a subject.

    Each ``find_*`` returns an iterable of ``DSRRecord`` for the given
    identifier. Each ``delete_*`` accepts a list of object_ids and
    returns the count actually deleted.
    """

    find_contact_submissions: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_contact_submissions: Optional[Callable[[list[str]], int]] = None

    find_public_responses: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_public_responses: Optional[Callable[[list[str]], int]] = None

    find_transcripts: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_transcripts: Optional[Callable[[list[str]], int]] = None

    find_embeddings: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_embeddings: Optional[Callable[[list[str]], int]] = None

    find_spans: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_spans: Optional[Callable[[list[str]], int]] = None

    find_draft_conclusions: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    delete_draft_conclusions: Optional[Callable[[list[str]], int]] = None

    find_retired_objects: Optional[Callable[[str], Iterable["DSRRecord"]]] = None
    # No deleter for retired_objects: policy is LOCKED.


@dataclass
class DSRRecord:
    """One row that matched the subject."""

    object_id: str
    summary: str
    """Short description suitable for the access report (e.g.
    ``"contact form: subject='Question about ...' from 2026-01-12"``)."""

    created_at: Optional[datetime] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "summary": self.summary,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            **({"extra": self.extra} if self.extra else {}),
        }


# ── Reports ──────────────────────────────────────────────────────────────────


@dataclass
class DSRReport:
    subject_identifier: str
    subject_kind: str
    """``email`` | ``orcid`` | ``object_id``"""

    generated_at: datetime
    findings: dict[str, list[DSRRecord]]
    """Keyed by retention-policy key. Empty list means the firm holds
    nothing in that class for this subject."""

    def total(self) -> int:
        return sum(len(v) for v in self.findings.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_identifier": self.subject_identifier,
            "subject_kind": self.subject_kind,
            "generated_at": self.generated_at.isoformat(),
            "total_records": self.total(),
            "findings": {
                k: [r.to_dict() for r in v] for k, v in self.findings.items()
            },
            "policy_summaries": {
                p.key: {
                    "label": p.label,
                    "ttl_days": p.ttl_days,
                    "action": p.action.value,
                    "founder_override": p.override.value,
                }
                for p in all_policies()
            },
        }


@dataclass
class DSRDeletionPlan:
    subject_identifier: str
    deletable: dict[str, list[str]]
    """Per-policy list of object_ids that the firm *can* delete."""

    held: dict[str, list[str]]
    """Per-policy list of object_ids the firm holds but cannot
    auto-delete (e.g. retired_objects: legal hold)."""

    def total_deletable(self) -> int:
        return sum(len(v) for v in self.deletable.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_identifier": self.subject_identifier,
            "total_deletable": self.total_deletable(),
            "deletable": self.deletable,
            "held": self.held,
        }


# ── Build report ─────────────────────────────────────────────────────────────


_FINDERS: dict[str, str] = {
    "contact_submissions": "find_contact_submissions",
    "public_responses": "find_public_responses",
    "transcripts": "find_transcripts",
    "embeddings": "find_embeddings",
    "spans": "find_spans",
    "draft_conclusions": "find_draft_conclusions",
    "retired_objects": "find_retired_objects",
}

_DELETERS: dict[str, str] = {
    "contact_submissions": "delete_contact_submissions",
    "public_responses": "delete_public_responses",
    "transcripts": "delete_transcripts",
    "embeddings": "delete_embeddings",
    "spans": "delete_spans",
    "draft_conclusions": "delete_draft_conclusions",
}


def detect_subject_kind(identifier: str) -> str:
    if "@" in identifier:
        return "email"
    if identifier.startswith("0000-") or identifier.count("-") == 3:
        return "orcid"
    return "object_id"


def build_report(
    identifier: str,
    ctx: DSRContext,
    *,
    subject_kind: Optional[str] = None,
) -> DSRReport:
    """Produce a comprehensive ``everything we have`` report.

    Walks every retention-policy class. Classes whose finder is not
    wired show up as an empty list (rather than being silently skipped),
    which is what makes the report a useful audit artifact.
    """
    kind = subject_kind or detect_subject_kind(identifier)
    findings: dict[str, list[DSRRecord]] = {}
    for policy in all_policies():
        attr = _FINDERS.get(policy.key)
        finder = getattr(ctx, attr, None) if attr else None
        if finder is None:
            findings[policy.key] = []
            continue
        try:
            records = list(finder(identifier))
        except Exception:
            logger.exception("DSR finder failed for %s", policy.key)
            records = []
        findings[policy.key] = records

    return DSRReport(
        subject_identifier=identifier,
        subject_kind=kind,
        generated_at=_utcnow(),
        findings=findings,
    )


# ── Build deletion plan ──────────────────────────────────────────────────────


def build_deletion_plan(report: DSRReport) -> DSRDeletionPlan:
    """Translate a report into ``what can/can't be deleted``."""
    deletable: dict[str, list[str]] = {}
    held: dict[str, list[str]] = {}
    for policy_key, records in report.findings.items():
        ids = [r.object_id for r in records]
        if not ids:
            continue
        policy = get_policy(policy_key)
        # Policies whose action is KEEP_WHILE_SOURCE_EXISTS (embeddings)
        # are deletable on DSR — the source is the user's data.
        # ARCHIVE policies (retired_objects) are LOCKED.
        if policy.action == LifecycleAction.ARCHIVE:
            held[policy_key] = ids
        else:
            deletable[policy_key] = ids
    return DSRDeletionPlan(
        subject_identifier=report.subject_identifier,
        deletable=deletable,
        held=held,
    )


# ── Execute deletion plan ────────────────────────────────────────────────────


@dataclass
class DSRExecutionResult:
    deleted: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def total_deleted(self) -> int:
        return sum(self.deleted.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_deleted": self.total_deleted(),
            "deleted": self.deleted,
            "errors": self.errors,
        }


def execute_deletion_plan(
    plan: DSRDeletionPlan,
    ctx: DSRContext,
    *,
    confirm_token: str,
) -> DSRExecutionResult:
    """Apply the deletion plan.

    The caller MUST supply ``confirm_token`` matching the subject
    identifier — this is a deliberate friction point so a forwarded
    plan dict cannot be auto-executed by mistake.
    """
    if confirm_token != plan.subject_identifier:
        raise ValueError("confirm_token must equal plan.subject_identifier")
    result = DSRExecutionResult()
    for policy_key, ids in plan.deletable.items():
        attr = _DELETERS.get(policy_key)
        deleter = getattr(ctx, attr, None) if attr else None
        if deleter is None:
            result.errors.append(f"no deleter wired for {policy_key}")
            result.deleted[policy_key] = 0
            continue
        try:
            n = int(deleter(ids) or 0)
        except Exception as exc:
            result.errors.append(f"{policy_key}: {exc!r}")
            n = 0
        result.deleted[policy_key] = n
    return result


# ── Public hash helper (for senderHash matching) ────────────────────────────


def email_hash(email: str) -> str:
    """SHA-256 of the lowercased email — matches the convention in
    ``ResponseTriage.senderHash`` so finders can join on a hashed key
    without expanding the PII surface."""
    return _hash_email(email)
