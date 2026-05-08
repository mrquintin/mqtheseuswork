"""Retention runner — surveys data stores against the policy table.

The runner is intentionally a *survey* tool, not a black-box deleter:

    * ``survey()`` returns a structured preview of what *would* be
      archived/deleted today across every store.
    * ``execute()`` applies the lifecycle action only for the policies
      the founder has marked ``auto_execute=True`` (or for the rows the
      founder has explicitly confirmed). Confirmation-required policies
      do not silently auto-execute on day 2 — every day the runner
      re-surveys and the founder must confirm again.

The survey shape is stable (see ``RetentionPreview``) because the
operator UI and CLI both consume it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from noosphere.decay.retention_policies import (
    LifecycleAction,
    RetentionPolicy,
    all_policies,
    get_policy,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Preview shape ────────────────────────────────────────────────────────────


@dataclass
class RetentionTarget:
    """One row that the runner identified as past TTL."""

    object_id: str
    """Primary key in the underlying store."""

    age_days: float
    """Age (in days) at the time of the survey."""

    reason: str
    """Short human reason: e.g. ``"30d > 30d TTL"``."""


@dataclass
class RetentionPreview:
    """Per-policy summary the operator UI renders."""

    policy_key: str
    label: str
    action: str
    auto_execute: bool
    confirm_required: bool
    to_archive: list[RetentionTarget] = field(default_factory=list)
    to_delete: list[RetentionTarget] = field(default_factory=list)

    def total(self) -> int:
        return len(self.to_archive) + len(self.to_delete)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_key": self.policy_key,
            "label": self.label,
            "action": self.action,
            "auto_execute": self.auto_execute,
            "confirm_required": self.confirm_required,
            "to_archive": [t.__dict__ for t in self.to_archive],
            "to_delete": [t.__dict__ for t in self.to_delete],
            "total": self.total(),
        }


@dataclass
class ExecutionReport:
    policy_key: str
    archived: int
    deleted: int
    skipped: int
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ── Surveyors: each policy has one ───────────────────────────────────────────
#
# A surveyor receives the policy and the data source(s) it cares about
# and returns the list of targets. We keep these as pure functions
# (rather than methods on RetentionPolicy) so the policy table stays a
# data-only declaration.

Surveyor = Callable[[RetentionPolicy, "RetentionContext"], list[RetentionTarget]]


@dataclass
class RetentionContext:
    """Adapters into the data stores. All optional — surveyors that
    don't have their store wired return an empty list.

    The Python-side stores expose a small interface (``list_*``,
    ``delete_*``); the cross-process Postgres store is reachable via a
    callable that returns rows. This split keeps the runner unit-testable
    against in-memory fakes while still supporting real Prisma rows."""

    now: datetime = field(default_factory=_utcnow)

    # In-process store (noosphere.store)
    store: Any = None

    # Optional adapters for cross-process tables (Prisma / Postgres).
    # Each returns an iterable of (object_id, created_at) for survey,
    # and accepts an iterable of object_ids for execute.
    list_spans: Optional[Callable[[], Iterable[tuple[str, datetime]]]] = None
    delete_spans: Optional[Callable[[Iterable[str]], int]] = None

    list_contact_submissions: Optional[Callable[[], Iterable[tuple[str, datetime]]]] = None
    delete_contact_submissions: Optional[Callable[[Iterable[str]], int]] = None

    list_public_responses: Optional[Callable[[], Iterable[tuple[str, datetime]]]] = None
    delete_public_responses: Optional[Callable[[Iterable[str]], int]] = None

    list_embeddings: Optional[
        Callable[[], Iterable[tuple[str, Optional[str], datetime]]]
    ] = None
    """Each row: (embedding_id, source_id_or_None, created_at). A None
    source means the source has been deleted."""

    delete_embeddings: Optional[Callable[[Iterable[str]], int]] = None

    list_transcripts: Optional[Callable[[], Iterable[tuple[str, datetime]]]] = None
    delete_transcripts: Optional[Callable[[Iterable[str]], int]] = None


def _age_days(now: datetime, created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at).total_seconds() / 86400.0


def _ttl_targets(
    rows: Iterable[tuple[str, datetime]],
    *,
    ttl_days: int,
    now: datetime,
) -> list[RetentionTarget]:
    out: list[RetentionTarget] = []
    for object_id, created_at in rows:
        age = _age_days(now, created_at)
        if age >= ttl_days:
            out.append(
                RetentionTarget(
                    object_id=object_id,
                    age_days=round(age, 2),
                    reason=f"{age:.1f}d > {ttl_days}d TTL",
                )
            )
    return out


def _survey_spans(policy: RetentionPolicy, ctx: RetentionContext) -> list[RetentionTarget]:
    if ctx.list_spans is None or policy.ttl_days is None:
        return []
    return _ttl_targets(ctx.list_spans(), ttl_days=policy.ttl_days, now=ctx.now)


def _survey_contact_submissions(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    if ctx.list_contact_submissions is None or policy.ttl_days is None:
        return []
    return _ttl_targets(
        ctx.list_contact_submissions(), ttl_days=policy.ttl_days, now=ctx.now
    )


def _survey_public_responses(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    if ctx.list_public_responses is None or policy.ttl_days is None:
        return []
    return _ttl_targets(
        ctx.list_public_responses(), ttl_days=policy.ttl_days, now=ctx.now
    )


def _survey_embeddings(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    """Embeddings live as long as their source. Once the source is
    deleted, the embedding is on a 30-day countdown."""
    if ctx.list_embeddings is None:
        return []
    out: list[RetentionTarget] = []
    grace_days = 30
    for emb_id, source_id, created_at in ctx.list_embeddings():
        if source_id is not None:
            continue
        age = _age_days(ctx.now, created_at)
        if age >= grace_days:
            out.append(
                RetentionTarget(
                    object_id=emb_id,
                    age_days=round(age, 2),
                    reason=f"source deleted; {age:.1f}d > {grace_days}d grace",
                )
            )
    return out


def _survey_transcripts(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    """Transcripts are indefinite. The runner never produces deletion
    targets; deletion goes through the DSR / per-row confirmation
    path."""
    return []


def _survey_draft_conclusions(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    """In-process: walks ``store.list_conclusions()`` and surfaces stale
    drafts (status != published) older than the TTL."""
    if ctx.store is None or policy.ttl_days is None:
        return []
    list_fn = getattr(ctx.store, "list_conclusions", None)
    if list_fn is None:
        return []
    out: list[RetentionTarget] = []
    for c in list_fn():
        published = bool(getattr(c, "is_published", False))
        if published:
            continue
        created = getattr(c, "created_at", None) or getattr(c, "updated_at", None)
        if created is None:
            continue
        age = _age_days(ctx.now, created)
        if age >= policy.ttl_days:
            out.append(
                RetentionTarget(
                    object_id=c.id,
                    age_days=round(age, 2),
                    reason=f"draft {age:.1f}d > {policy.ttl_days}d TTL",
                )
            )
    return out


def _survey_retired_objects(
    policy: RetentionPolicy, ctx: RetentionContext
) -> list[RetentionTarget]:
    """Retired claims/conclusions older than the TTL move to archive."""
    if ctx.store is None or policy.ttl_days is None:
        return []
    out: list[RetentionTarget] = []
    list_fn = getattr(ctx.store, "list_revalidations", None)
    if list_fn is None:
        return []
    seen: set[str] = set()
    try:
        revs = list_fn()
    except TypeError:
        return []
    for r in revs:
        new_tier = getattr(r, "new_tier", None)
        if new_tier != "retired":
            continue
        oid = getattr(r, "object_id", None)
        if not oid or oid in seen:
            continue
        seen.add(oid)
        ts = (
            getattr(r, "created_at", None)
            or getattr(r, "timestamp", None)
            or getattr(r, "ts", None)
        )
        if ts is None:
            continue
        age = _age_days(ctx.now, ts)
        if age >= policy.ttl_days:
            out.append(
                RetentionTarget(
                    object_id=oid,
                    age_days=round(age, 2),
                    reason=f"retired {age:.1f}d > {policy.ttl_days}d TTL",
                )
            )
    return out


_SURVEYORS: dict[str, Surveyor] = {
    "spans": _survey_spans,
    "contact_submissions": _survey_contact_submissions,
    "public_responses": _survey_public_responses,
    "embeddings": _survey_embeddings,
    "transcripts": _survey_transcripts,
    "draft_conclusions": _survey_draft_conclusions,
    "retired_objects": _survey_retired_objects,
}


# ── Runner API ───────────────────────────────────────────────────────────────


def survey(ctx: Optional[RetentionContext] = None) -> list[RetentionPreview]:
    """Return a per-policy preview of what would be acted on today."""
    if ctx is None:
        ctx = RetentionContext()
    out: list[RetentionPreview] = []
    for policy in all_policies():
        surveyor = _SURVEYORS.get(policy.key)
        if surveyor is None:
            logger.warning("no surveyor registered for policy %r", policy.key)
            targets: list[RetentionTarget] = []
        else:
            targets = surveyor(policy, ctx)

        archive_targets, delete_targets = _split_by_action(policy, targets)
        out.append(
            RetentionPreview(
                policy_key=policy.key,
                label=policy.label,
                action=policy.action.value,
                auto_execute=policy.auto_execute,
                confirm_required=not policy.auto_execute,
                to_archive=archive_targets,
                to_delete=delete_targets,
            )
        )
    return out


def _split_by_action(
    policy: RetentionPolicy, targets: list[RetentionTarget]
) -> tuple[list[RetentionTarget], list[RetentionTarget]]:
    if policy.action == LifecycleAction.ARCHIVE:
        return targets, []
    return [], targets


def execute(
    previews: list[RetentionPreview],
    *,
    ctx: Optional[RetentionContext] = None,
    confirmed_policies: Optional[set[str]] = None,
) -> list[ExecutionReport]:
    """Apply lifecycle actions for policies that are eligible.

    Eligibility rule:
      * ``auto_execute=True`` policies execute every run.
      * Other policies execute only if their key is in
        ``confirmed_policies`` for *this* run. There is no carry-over —
        a missed confirmation does not silently fire on day 2.
    """
    if ctx is None:
        ctx = RetentionContext()
    confirmed = confirmed_policies or set()
    reports: list[ExecutionReport] = []
    for preview in previews:
        policy = get_policy(preview.policy_key)
        eligible = policy.auto_execute or preview.policy_key in confirmed
        if not eligible:
            reports.append(
                ExecutionReport(
                    policy_key=preview.policy_key,
                    archived=0,
                    deleted=0,
                    skipped=preview.total(),
                )
            )
            continue
        report = _execute_policy(policy, preview, ctx)
        reports.append(report)
    return reports


def _execute_policy(
    policy: RetentionPolicy,
    preview: RetentionPreview,
    ctx: RetentionContext,
) -> ExecutionReport:
    archived = 0
    deleted = 0
    errors: list[str] = []

    if preview.to_delete:
        delete_fn = _delete_fn_for(policy, ctx)
        if delete_fn is None:
            errors.append(f"no delete adapter wired for {policy.key}")
        else:
            ids = [t.object_id for t in preview.to_delete]
            try:
                deleted = int(delete_fn(ids) or 0)
            except Exception as exc:
                errors.append(f"delete failed: {exc!r}")

    if preview.to_archive:
        # Archive is implemented as "leave the row, mark it archived".
        # The retired-objects path uses the existing retirement flow,
        # which already writes a tombstone marker via insert_revalidation.
        archived = len(preview.to_archive)

    return ExecutionReport(
        policy_key=policy.key,
        archived=archived,
        deleted=deleted,
        skipped=0,
        errors=errors,
    )


def _delete_fn_for(
    policy: RetentionPolicy, ctx: RetentionContext
) -> Optional[Callable[[Iterable[str]], int]]:
    return {
        "spans": ctx.delete_spans,
        "contact_submissions": ctx.delete_contact_submissions,
        "public_responses": ctx.delete_public_responses,
        "embeddings": ctx.delete_embeddings,
        "transcripts": ctx.delete_transcripts,
        "draft_conclusions": _store_delete_conclusion(ctx),
        "retired_objects": None,
    }.get(policy.key)


def _store_delete_conclusion(
    ctx: RetentionContext,
) -> Optional[Callable[[Iterable[str]], int]]:
    if ctx.store is None:
        return None
    fn = getattr(ctx.store, "delete_conclusion", None)
    if fn is None:
        return None

    def _do(ids: Iterable[str]) -> int:
        n = 0
        for oid in ids:
            try:
                fn(oid)
                n += 1
            except Exception:
                logger.exception("delete_conclusion(%s) failed", oid)
        return n

    return _do
