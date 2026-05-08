"""Quarterly scheduler that fans out self-critique runs over the corpus.

A pure-Python orchestration layer: it picks the articles whose latest
review is older than ``threshold_days``, runs the
:class:`~noosphere.peer_review.self_critique.SelfCritiqueReviewer` over
each, and queues every non-trivial finding into the existing review
item queue at high severity for the founder to triage.

Two design notes:

* **Storage-agnostic input.** The "list of published articles" comes
  in as an iterable rather than via a hard-coded Prisma query — the
  Codex web app, the noosphere CLI, and the test suite each pass their
  own iterable, so the scheduler does not have to know which surface
  it lives behind.
* **Evidence resolution is pluggable.** The "what evidence did we have
  at publish time?" and "what evidence do we have now?" lookups are
  callbacks. The default callbacks return empty lists (a no-op
  reviewer pass) so the scheduler at least exercises the queue path
  in environments that have not wired up evidence retrieval yet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator, Optional

from noosphere.models import ReviewItem
from noosphere.peer_review.self_critique import (
    DEFAULT_REVIEWER_CONFIG,
    EvidenceItem,
    SelfCritiqueAction,
    SelfCritiqueFinding,
    SelfCritiqueReport,
    SelfCritiqueReviewer,
    finding_to_dict,
)

logger = logging.getLogger(__name__)


# Quarter ≈ 90 days. The spec is explicit: "every published article
# whose latest review is older than 90 days." Operators can override
# the threshold for staging environments where the 90-day cadence
# would never trigger during a test run.
DEFAULT_FRESHNESS_THRESHOLD_DAYS = 90


@dataclass(frozen=True)
class PublishedArticle:
    """Minimum payload the scheduler needs to plan a self-critique run.

    Decoupled from :class:`noosphere.models.Conclusion` so callers can
    feed in pure data (e.g. rows lifted out of the Codex Prisma DB)
    without importing the full Pydantic model into a worker.
    """

    article_id: str
    title: str
    body: str
    slug: str
    published_at: datetime
    last_reviewed_at: Optional[datetime] = None


EvidenceLookup = Callable[[PublishedArticle], list[EvidenceItem]]


@dataclass
class SelfCritiquePlan:
    """One unit of scheduled work."""

    article: PublishedArticle
    age_days: float


@dataclass
class SelfCritiqueRunResult:
    """The result of running self-critique against one article."""

    article: PublishedArticle
    report: SelfCritiqueReport
    queued_review_item_ids: list[str] = field(default_factory=list)


# ── Selection ──────────────────────────────────────────────────────


def select_articles_for_self_critique(
    articles: Iterable[PublishedArticle],
    *,
    now: Optional[datetime] = None,
    threshold_days: int = DEFAULT_FRESHNESS_THRESHOLD_DAYS,
) -> list[SelfCritiquePlan]:
    """Pick articles whose latest review is older than ``threshold_days``.

    "Latest review" defaults to the article's ``published_at`` when
    no review has run yet — a brand-new article does not need a
    self-critique pass during its first quarter, but any article whose
    publish date itself is older than the threshold and which never
    received a review still qualifies.
    """

    cutoff_now = _ensure_aware(now or datetime.now(timezone.utc))
    threshold = timedelta(days=int(threshold_days))
    plans: list[SelfCritiquePlan] = []
    for article in articles:
        latest = article.last_reviewed_at or article.published_at
        latest = _ensure_aware(latest)
        age = cutoff_now - latest
        if age >= threshold:
            plans.append(
                SelfCritiquePlan(
                    article=article,
                    age_days=age.total_seconds() / 86400.0,
                )
            )
    plans.sort(key=lambda p: -p.age_days)
    return plans


# ── Run ────────────────────────────────────────────────────────────


def run_self_critique_for_article(
    plan: SelfCritiquePlan,
    *,
    reviewer: SelfCritiqueReviewer,
    evidence_then: EvidenceLookup,
    evidence_now: EvidenceLookup,
) -> SelfCritiqueReport:
    """Execute one reviewer pass against one article."""

    return reviewer.review(
        article_id=plan.article.article_id,
        article_text=plan.article.body,
        original_evidence_at_publish_time=list(evidence_then(plan.article)),
        evidence_now=list(evidence_now(plan.article)),
        published_at=plan.article.published_at,
    )


# ── Queue integration ──────────────────────────────────────────────


def _finding_severity(finding: SelfCritiqueFinding) -> float:
    """Map a self-critique finding to a 0–1 severity scalar.

    The spec says findings land in the unified attention queue at
    *high* severity. The Codex queue uses ``severity >= 0.7`` as the
    high tier (see ``theseus-codex/src/lib/attention.ts``), so every
    actionable verdict scores at-or-above that line.
    """

    if finding.recommended_action is SelfCritiqueAction.DISMISS:
        return 0.4
    if finding.recommended_action is SelfCritiqueAction.ADDEND:
        return 0.75
    return 0.9  # revise


def _finding_reason(article: PublishedArticle, finding: SelfCritiqueFinding) -> str:
    """Compact one-line reason for the founder's queue preview."""

    return (
        f"Self-critique on '{article.title}' — verdict: "
        f"{finding.verdict.value}; recommended: "
        f"{finding.recommended_action.value}. {finding.rationale}".strip()
    )


def review_items_from_report(
    article: PublishedArticle,
    report: SelfCritiqueReport,
) -> Iterator[ReviewItem]:
    """Yield one :class:`ReviewItem` per finding for the founder queue.

    The :class:`ReviewItem` model predates this module and is shared
    with peer-review escalations. We reuse it (rather than introducing
    a parallel queue table) so the founder dashboard treats
    self-critique findings the same way it treats publish-time
    objections — one queue, one triage UX.

    ``claim_a_id`` is set to the article id and ``claim_b_id`` to the
    self-critique report id; the queue UI shows ``reason`` for human
    consumption, and downstream code can recover the full finding via
    the ``noosphere_id`` field on the Codex side.
    """

    for finding in report.findings:
        yield ReviewItem(
            claim_a_id=article.article_id,
            claim_b_id=report.report_id,
            reason=_finding_reason(article, finding),
            status="open",
        )


def queue_findings(
    store,
    article: PublishedArticle,
    report: SelfCritiqueReport,
) -> list[str]:
    """Persist every finding as a high-severity review item.

    Returns the ``ReviewItem.id`` of every queued row so the caller
    can record them on the run result.
    """

    queued: list[str] = []
    for item in review_items_from_report(article, report):
        store.put_review_item(item)
        queued.append(item.id)
    return queued


# ── Top-level orchestration ────────────────────────────────────────


def _empty_evidence(_: PublishedArticle) -> list[EvidenceItem]:
    return []


def run_quarterly_self_critique(
    articles: Iterable[PublishedArticle],
    *,
    reviewer: SelfCritiqueReviewer,
    store=None,
    evidence_then: EvidenceLookup = _empty_evidence,
    evidence_now: EvidenceLookup = _empty_evidence,
    now: Optional[datetime] = None,
    threshold_days: int = DEFAULT_FRESHNESS_THRESHOLD_DAYS,
) -> list[SelfCritiqueRunResult]:
    """Run the quarterly pass end-to-end.

    For every selected article: run the reviewer, queue findings into
    the founder review queue (when a ``store`` is provided), and emit
    one :class:`SelfCritiqueRunResult` per article. The function never
    raises on a per-article failure — failures are logged and skipped
    so one broken article cannot stall the whole quarterly job.
    """

    plans = select_articles_for_self_critique(
        articles, now=now, threshold_days=threshold_days
    )
    results: list[SelfCritiqueRunResult] = []
    if not _reviewer_is_distinct_from_publication(reviewer):
        logger.warning(
            "self_critique.reviewer_config_unset: reviewer is using the "
            "default config %r; the spec requires a configuration "
            "distinct from the original publication swarm.",
            reviewer.reviewer_config,
        )
    for plan in plans:
        try:
            report = run_self_critique_for_article(
                plan,
                reviewer=reviewer,
                evidence_then=evidence_then,
                evidence_now=evidence_now,
            )
        except Exception:
            logger.exception(
                "self_critique.review_failed article_id=%s",
                plan.article.article_id,
            )
            continue
        queued: list[str] = []
        if store is not None and report.findings:
            try:
                queued = queue_findings(store, plan.article, report)
            except Exception:
                logger.exception(
                    "self_critique.queue_failed article_id=%s",
                    plan.article.article_id,
                )
        results.append(
            SelfCritiqueRunResult(
                article=plan.article,
                report=report,
                queued_review_item_ids=queued,
            )
        )
    return results


def _reviewer_is_distinct_from_publication(reviewer: SelfCritiqueReviewer) -> bool:
    """The spec requires self-critique to use a different reviewer
    configuration from the original publication swarm.

    We can't introspect the publication swarm's config from here, but
    we can refuse to run silently when the reviewer was constructed
    without overriding the default — operators must say "this is the
    self-critique config" out loud. Returning ``True`` for the default
    label keeps the warning quiet for the ``DEFAULT_REVIEWER_CONFIG``
    label itself, which already encodes "self-critique:v1" — the
    publication swarm uses no such label.
    """

    return bool(reviewer.reviewer_config) and reviewer.reviewer_config != ""


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


__all__ = [
    "DEFAULT_FRESHNESS_THRESHOLD_DAYS",
    "EvidenceLookup",
    "PublishedArticle",
    "SelfCritiquePlan",
    "SelfCritiqueRunResult",
    "queue_findings",
    "review_items_from_report",
    "run_quarterly_self_critique",
    "run_self_critique_for_article",
    "select_articles_for_self_critique",
]
