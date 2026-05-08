"""Data retention & lifecycle policies.

This module defines the canonical retention table for the firm. Every
class of data the firm stores has exactly one row here, and the row is
the source of truth for:

  * how long the data lives (TTL),
  * what happens at the end of life (archive vs. delete vs. roll-up),
  * whether the founder can override the lifecycle action without an
    extra confirmation step (auto_execute), and
  * the public-facing prose summary that appears on /privacy.

The runner (``retention_runner.py``) consumes this table; the public
privacy page is generated from it; the ``check_privacy_page_consistency``
script enforces that prose and behavior cannot drift.

Adding or removing a class of data here is the *only* sanctioned way to
change retention behavior. The build fails if /privacy lists a class
that does not exist in this table, or vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LifecycleAction(str, Enum):
    """What happens to a row when its TTL expires."""

    DELETE = "delete"
    ROLLUP_AND_DELETE = "rollup_and_delete"
    ARCHIVE = "archive"
    DELETE_WITH_CONFIRMATION = "delete_with_confirmation"
    KEEP_WHILE_SOURCE_EXISTS = "keep_while_source_exists"


class FounderOverride(str, Enum):
    """Constraint on the founder's ability to short-circuit a policy."""

    # Founder can flip auto_execute on/off freely.
    UNRESTRICTED = "unrestricted"
    # Founder can flip auto_execute on, but a per-row confirmation is
    # always required before deletion.
    CONFIRM_REQUIRED = "confirm_required"
    # Founder cannot enable auto_execute (legal hold / regulated data).
    LOCKED = "locked"


@dataclass(frozen=True)
class RetentionPolicy:
    """A single class of data and how it is retained."""

    key: str
    """Stable machine identifier (e.g. ``spans``)."""

    label: str
    """Human label for ops UI (e.g. ``"Observability spans"``)."""

    ttl_days: Optional[int]
    """Days until lifecycle action runs. ``None`` = indefinite."""

    action: LifecycleAction
    """What to do at end of life."""

    override: FounderOverride
    """Founder's authority to change auto-execute on this policy."""

    auto_execute: bool = False
    """If True, the runner applies the action without a daily confirm."""

    privacy_summary: str = ""
    """Plain-prose summary rendered on /privacy. Concrete numbers only —
    no template language."""

    legal_basis: str = ""
    """Why this TTL was chosen (e.g. ``"GDPR Art. 17"``, ``"firm policy"``)."""

    rollup_target: Optional[str] = None
    """For rollup_and_delete: the metric/aggregate that survives
    deletion (e.g. ``"MethodMetricRollup"``)."""

    tombstone: bool = False
    """If True, deletion leaves a content-free marker row. Default False
    — the constraint is that tombstones are explicit, not the default."""

    def __post_init__(self) -> None:
        if self.action == LifecycleAction.ROLLUP_AND_DELETE and not self.rollup_target:
            raise ValueError(
                f"policy {self.key!r}: rollup_and_delete requires rollup_target"
            )
        if (
            self.override == FounderOverride.LOCKED
            and self.auto_execute
        ):
            raise ValueError(
                f"policy {self.key!r}: LOCKED override forbids auto_execute=True"
            )


# ── Canonical retention table ────────────────────────────────────────────────
#
# Order is preserved when rendering the /privacy page so the prose reads
# in a deliberate sequence (most-volatile → most-permanent).

POLICIES: tuple[RetentionPolicy, ...] = (
    RetentionPolicy(
        key="spans",
        label="Observability spans",
        ttl_days=30,
        action=LifecycleAction.ROLLUP_AND_DELETE,
        override=FounderOverride.UNRESTRICTED,
        auto_execute=True,
        rollup_target="MethodMetricRollup",
        privacy_summary=(
            "Internal trace/span records — used to debug pipelines and "
            "track latency — are kept for 30 days. After 30 days the "
            "raw rows are deleted; only aggregate per-method timing "
            "rollups survive."
        ),
        legal_basis="firm policy: bounded observability cost",
    ),
    RetentionPolicy(
        key="contact_submissions",
        label="Public contact-form submissions",
        ttl_days=180,
        action=LifecycleAction.DELETE,
        override=FounderOverride.UNRESTRICTED,
        auto_execute=False,
        privacy_summary=(
            "Messages sent through the public contact form are kept for "
            "180 days so the firm can follow up on a thread, then "
            "deleted. You can request earlier deletion; see the data "
            "subject request section below."
        ),
        legal_basis="firm policy: bounded inbox surface",
    ),
    RetentionPolicy(
        key="public_responses",
        label="Public responses to published conclusions",
        ttl_days=365 * 7,
        action=LifecycleAction.DELETE_WITH_CONFIRMATION,
        override=FounderOverride.CONFIRM_REQUIRED,
        auto_execute=False,
        privacy_summary=(
            "When you submit a response to a published conclusion, the "
            "firm retains your submission for 7 years so the public "
            "record of dialogue around that conclusion stays intact. "
            "After 7 years, the firm reviews and deletes the raw row "
            "with founder confirmation; aggregate counts may persist."
        ),
        legal_basis="legal: reasonable record of public dialogue",
    ),
    RetentionPolicy(
        key="embeddings",
        label="Vector embeddings",
        ttl_days=None,
        action=LifecycleAction.KEEP_WHILE_SOURCE_EXISTS,
        override=FounderOverride.UNRESTRICTED,
        auto_execute=True,
        privacy_summary=(
            "Vector embeddings exist for as long as the underlying "
            "source document exists. When a source is deleted, its "
            "embeddings are deleted within 30 days."
        ),
        legal_basis="firm policy: derivative of source",
    ),
    RetentionPolicy(
        key="transcripts",
        label="Interview transcripts",
        ttl_days=None,
        action=LifecycleAction.DELETE_WITH_CONFIRMATION,
        override=FounderOverride.CONFIRM_REQUIRED,
        auto_execute=False,
        privacy_summary=(
            "Interview transcripts (uploads) are retained indefinitely "
            "as part of the firm's working corpus. Deletion requires "
            "founder confirmation per record; you can also request "
            "deletion via the data subject request channel."
        ),
        legal_basis="firm policy: research corpus",
    ),
    RetentionPolicy(
        key="draft_conclusions",
        label="Draft (unpublished) conclusions",
        ttl_days=90,
        action=LifecycleAction.DELETE,
        override=FounderOverride.UNRESTRICTED,
        auto_execute=False,
        privacy_summary=(
            "Internal draft conclusions that are never published are "
            "deleted 90 days after they go stale. Published conclusions "
            "are retained as part of the public record."
        ),
        legal_basis="firm policy: bounded draft surface",
    ),
    RetentionPolicy(
        key="retired_objects",
        label="Retired claims and conclusions",
        ttl_days=365,
        action=LifecycleAction.ARCHIVE,
        override=FounderOverride.LOCKED,
        auto_execute=False,
        tombstone=True,
        privacy_summary=(
            "When a claim or conclusion is retired (refuted or "
            "withdrawn), the firm archives it for 1 year with a "
            "tombstone marker so the audit trail of what was retracted "
            "and why remains visible. After 1 year the archive may be "
            "compressed but the tombstone remains permanently."
        ),
        legal_basis="firm policy: retraction transparency",
    ),
)


# ── Lookup helpers ───────────────────────────────────────────────────────────


_POLICIES_BY_KEY: dict[str, RetentionPolicy] = {p.key: p for p in POLICIES}


def get_policy(key: str) -> RetentionPolicy:
    """Look up a policy by its stable key."""
    try:
        return _POLICIES_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"unknown retention policy: {key!r}") from exc


def all_policies() -> tuple[RetentionPolicy, ...]:
    """Canonical, ordered list of every retention policy."""
    return POLICIES


def policy_keys() -> tuple[str, ...]:
    return tuple(p.key for p in POLICIES)
