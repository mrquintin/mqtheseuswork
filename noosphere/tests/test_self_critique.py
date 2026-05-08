"""Tests for the quarterly self-critique pass (prompt 43).

Three layers under test:

1. The :class:`SelfCritiqueReviewer` produces strict findings whose
   shape matches the spec (claim / was_supported_by / now_supported_by
   / verdict / recommended_action).
2. The scheduler picks articles whose latest review is older than 90
   days, queues findings as high-severity review items, and refuses
   to use evidence the firm could not have seen at publish time.
3. The addendum lifecycle: a finding with ``recommended_action="addend"``
   becomes a pending :class:`Addendum`, which can transition to
   ``published`` (visible publicly) or ``dismissed`` (with a reason on
   record). Original article text is never mutated by this path.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.peer_review.self_critique import (
    Addendum,
    AddendumStatus,
    DEFAULT_REVIEWER_CONFIG,
    EvidenceItem,
    SelfCritiqueAction,
    SelfCritiqueFinding,
    SelfCritiqueReviewer,
    SelfCritiqueVerdict,
    addendum_from_finding,
    coerce_finding,
    dismiss_addendum,
    finding_to_dict,
    publish_addendum,
)
from noosphere.peer_review.scheduler_self_critique import (
    DEFAULT_FRESHNESS_THRESHOLD_DAYS,
    PublishedArticle,
    SelfCritiquePlan,
    review_items_from_report,
    run_quarterly_self_critique,
    select_articles_for_self_critique,
)
from noosphere.store import Store


# ── Fixtures / helpers ─────────────────────────────────────────────


def _ev(source_id: str, summary: str, *, days_ago: int = 0) -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        summary=summary,
        observed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _article(
    *,
    article_id: str = "art-1",
    title: str = "On founder-led firms",
    body: str = "Founder-led firms outperform on five-year ROIC.",
    slug: str = "founder-led-firms",
    published_days_ago: int = 200,
    last_reviewed_days_ago: int | None = None,
) -> PublishedArticle:
    now = datetime.now(timezone.utc)
    return PublishedArticle(
        article_id=article_id,
        title=title,
        body=body,
        slug=slug,
        published_at=now - timedelta(days=published_days_ago),
        last_reviewed_at=(
            now - timedelta(days=last_reviewed_days_ago)
            if last_reviewed_days_ago is not None
            else None
        ),
    )


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


# ── Reviewer shape ─────────────────────────────────────────────────


def test_reviewer_emits_strict_finding_shape():
    """The reviewer must round-trip findings through the strict
    Pydantic schema, dropping anything that does not conform.
    """

    def judge_fn(article_id, body, config, then, now):
        assert article_id == "art-1"
        assert config != ""  # reviewer_config must be set
        # One finding per spec verdict to confirm enum coercion works.
        return [
            {
                "claim": "Founder-led firms outperform.",
                "was_supported_by": ["src:hbr-2014"],
                "now_supported_by": ["src:nber-2025"],
                "verdict": "weakened",
                "recommended_action": "addend",
                "rationale": "New cohort study halves the effect size.",
            },
            {
                "claim": "Five-year ROIC is the right horizon.",
                "was_supported_by": ["src:internal-memo"],
                "now_supported_by": ["src:internal-memo"],
                "verdict": "still holds",
                # action omitted on purpose — the coercer should fall
                # back to the verdict's default action (dismiss).
            },
        ]

    reviewer = SelfCritiqueReviewer(
        judge_fn=judge_fn, reviewer_config="self-critique:test-v1"
    )
    report = reviewer.review(
        article_id="art-1",
        article_text="Founder-led firms outperform on five-year ROIC.",
        original_evidence_at_publish_time=[_ev("src:hbr-2014", "old", days_ago=400)],
        evidence_now=[_ev("src:nber-2025", "new", days_ago=10)],
        published_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    assert report.reviewer == "self_critique"
    assert report.reviewer_config == "self-critique:test-v1"
    assert len(report.findings) == 2

    weakened, still_holds = report.findings
    assert weakened.verdict is SelfCritiqueVerdict.WEAKENED
    assert weakened.recommended_action is SelfCritiqueAction.ADDEND
    assert weakened.was_supported_by == ["src:hbr-2014"]
    assert weakened.now_supported_by == ["src:nber-2025"]

    assert still_holds.verdict is SelfCritiqueVerdict.STILL_HOLDS
    # Default action for "still holds" is dismiss.
    assert still_holds.recommended_action is SelfCritiqueAction.DISMISS


def test_reviewer_filters_pre_publication_evidence_from_now():
    """Evidence-now items observed before publication must not reach
    the judge — that would let the reviewer claim "you should have
    known", which the spec forbids.
    """

    captured: dict[str, list[EvidenceItem]] = {}

    def judge_fn(article_id, body, config, then, now):
        captured["then"] = then
        captured["now"] = now
        return []

    published_at = datetime.now(timezone.utc) - timedelta(days=180)
    reviewer = SelfCritiqueReviewer(
        judge_fn=judge_fn, reviewer_config="self-critique:test-v1"
    )
    reviewer.review(
        article_id="art-1",
        article_text="body",
        original_evidence_at_publish_time=[],
        evidence_now=[
            EvidenceItem(
                source_id="too-old",
                summary="known at publish time",
                observed_at=published_at - timedelta(days=30),
            ),
            EvidenceItem(
                source_id="fresh",
                summary="legitimately new",
                observed_at=published_at + timedelta(days=30),
            ),
        ],
        published_at=published_at,
    )
    sources = [e.source_id for e in captured["now"]]
    assert "fresh" in sources
    assert "too-old" not in sources


def test_default_judge_refuses_to_run():
    """A reviewer constructed without a judge_fn must not silently
    return an empty report — operators have to wire in a judge.
    """

    reviewer = SelfCritiqueReviewer(reviewer_config="self-critique:test-v1")
    with pytest.raises(RuntimeError):
        reviewer.review(
            article_id="art-1",
            article_text="body",
            original_evidence_at_publish_time=[],
            evidence_now=[],
        )


def test_coerce_finding_handles_action_synonyms():
    """The coercer must accept the spec's exact verdict labels and
    emit the strict enums.
    """

    f = coerce_finding(
        {
            "claim": "x",
            "was_supported_by": [],
            "now_supported_by": [],
            "verdict": "contradicted by new evidence",
            "recommended_action": "revise",
            "rationale": "",
        }
    )
    assert f.verdict is SelfCritiqueVerdict.CONTRADICTED
    assert f.recommended_action is SelfCritiqueAction.REVISE


# ── Scheduler selection ────────────────────────────────────────────


def test_scheduler_selects_articles_older_than_threshold():
    young = _article(article_id="young", published_days_ago=30)
    old = _article(article_id="old", published_days_ago=200)
    very_old = _article(article_id="very-old", published_days_ago=400)
    plans = select_articles_for_self_critique([young, old, very_old])
    ids = [p.article.article_id for p in plans]
    assert "young" not in ids
    assert ids == ["very-old", "old"]  # sorted by age desc


def test_scheduler_uses_last_reviewed_when_present():
    """An article that was published a year ago but reviewed last
    week must NOT be re-queued."""

    art = _article(
        article_id="recent-review",
        published_days_ago=400,
        last_reviewed_days_ago=7,
    )
    plans = select_articles_for_self_critique([art])
    assert plans == []


def test_scheduler_threshold_is_90_days_by_default():
    assert DEFAULT_FRESHNESS_THRESHOLD_DAYS == 90


# ── Scheduler runs the reviewer + queues into ReviewItem ──────────


def test_run_quarterly_queues_high_severity_review_items(store: Store):
    """End-to-end: the quarterly scheduler runs the reviewer, lands
    findings as high-severity review items in the founder queue.
    """

    art = _article(article_id="art-1", published_days_ago=200)

    def judge_fn(article_id, body, config, then, now):
        return [
            {
                "claim": "Effect size has halved.",
                "was_supported_by": ["src:old"],
                "now_supported_by": ["src:new"],
                "verdict": "weakened",
                "recommended_action": "addend",
                "rationale": "Replication shrunk the effect.",
            }
        ]

    reviewer = SelfCritiqueReviewer(
        judge_fn=judge_fn, reviewer_config="self-critique:test-v1"
    )
    results = run_quarterly_self_critique(
        [art],
        reviewer=reviewer,
        store=store,
    )
    assert len(results) == 1
    assert results[0].queued_review_item_ids
    items = store.list_open_review_items()
    assert len(items) == 1
    item = items[0]
    assert item.claim_a_id == "art-1"
    assert item.status == "open"
    assert "weakened" in item.reason
    assert "addend" in item.reason


def test_quarterly_skips_young_articles(store: Store):
    young = _article(article_id="young", published_days_ago=10)

    def judge_fn(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("reviewer should not run on young articles")

    reviewer = SelfCritiqueReviewer(
        judge_fn=judge_fn, reviewer_config="self-critique:test-v1"
    )
    results = run_quarterly_self_critique(
        [young],
        reviewer=reviewer,
        store=store,
    )
    assert results == []
    assert store.list_open_review_items() == []


def test_review_items_have_high_severity_reason_strings():
    """The queue preview string must encode severity in a way the
    operator UI can render without a second lookup.
    """

    art = _article(article_id="art-x")
    finding = SelfCritiqueFinding(
        claim="A claim.",
        verdict=SelfCritiqueVerdict.CONTRADICTED,
        recommended_action=SelfCritiqueAction.REVISE,
        rationale="Counter-evidence.",
    )
    report = SelfCritiqueReviewer(
        judge_fn=lambda *a, **k: [finding_to_dict(finding)],
        reviewer_config="self-critique:test-v1",
    ).review(
        article_id=art.article_id,
        article_text=art.body,
        original_evidence_at_publish_time=[],
        evidence_now=[],
    )
    items = list(review_items_from_report(art, report))
    assert len(items) == 1
    assert "contradicted" in items[0].reason
    assert "revise" in items[0].reason


# ── Addendum lifecycle ─────────────────────────────────────────────


def test_addendum_lifecycle_pending_to_published():
    finding = SelfCritiqueFinding(
        claim="Effect halved.",
        was_supported_by=["src:old"],
        now_supported_by=["src:new"],
        verdict=SelfCritiqueVerdict.WEAKENED,
        recommended_action=SelfCritiqueAction.ADDEND,
        rationale="Replication shrunk the effect.",
    )
    pending = addendum_from_finding(
        finding,
        article_id="art-1",
        article_slug="founder-led-firms",
        finding_id="f-1",
        reviewer_config="self-critique:test-v1",
    )
    assert pending.status is AddendumStatus.PENDING
    assert pending.published_at is None

    now = datetime(2026, 5, 8, tzinfo=timezone.utc)
    published = publish_addendum(pending, now=now)
    assert published.status is AddendumStatus.PUBLISHED
    assert published.published_at == now

    # Original pending instance is untouched — model_copy is immutable.
    assert pending.status is AddendumStatus.PENDING


def test_addendum_lifecycle_pending_to_dismissed_with_reason():
    finding = SelfCritiqueFinding(
        claim="Tangential point.",
        verdict=SelfCritiqueVerdict.WEAKENED,
        recommended_action=SelfCritiqueAction.ADDEND,
        rationale="Minor.",
    )
    pending = addendum_from_finding(finding, article_id="art-1")
    dismissed = dismiss_addendum(
        pending, reason="Tangential to the article's thesis."
    )
    assert dismissed.status is AddendumStatus.DISMISSED
    assert dismissed.dismissed_reason == "Tangential to the article's thesis."
    assert dismissed.dismissed_at is not None


def test_addendum_dismissal_requires_reason():
    finding = SelfCritiqueFinding(
        claim="x",
        verdict=SelfCritiqueVerdict.WEAKENED,
        recommended_action=SelfCritiqueAction.ADDEND,
    )
    pending = addendum_from_finding(finding, article_id="art-1")
    with pytest.raises(ValueError):
        dismiss_addendum(pending, reason="   ")


def test_addendum_refuses_non_addend_findings():
    """A "revise" finding must go through the revision engine, not
    the addendum path — addendum_from_finding refuses it.
    """

    finding = SelfCritiqueFinding(
        claim="x",
        verdict=SelfCritiqueVerdict.CONTRADICTED,
        recommended_action=SelfCritiqueAction.REVISE,
    )
    with pytest.raises(ValueError):
        addendum_from_finding(finding, article_id="art-1")


def test_publish_refuses_non_pending():
    finding = SelfCritiqueFinding(
        claim="x",
        verdict=SelfCritiqueVerdict.WEAKENED,
        recommended_action=SelfCritiqueAction.ADDEND,
    )
    pending = addendum_from_finding(finding, article_id="art-1")
    published = publish_addendum(pending)
    with pytest.raises(ValueError):
        publish_addendum(published)


def test_addendum_does_not_mutate_article_body():
    """The original article body is the immutability invariant of
    this whole prompt. The addendum produced from a finding records
    its own body but never references the original article body.
    """

    article = _article(
        article_id="art-1",
        body="Original article text — must remain unchanged.",
    )
    finding = SelfCritiqueFinding(
        claim="A claim.",
        verdict=SelfCritiqueVerdict.WEAKENED,
        recommended_action=SelfCritiqueAction.ADDEND,
        rationale="Some new context.",
    )
    addendum = addendum_from_finding(
        finding,
        article_id=article.article_id,
        article_slug=article.slug,
    )
    assert article.body == "Original article text — must remain unchanged."
    assert article.body not in addendum.body
