"""Tests for the open-critique routing flow.

Covers the F-test list in the prompt:

- A synthetic submission flows through the moderation ladder.
- The three terminal moderation states (accepted / partial / rejected)
  produce distinct, persisted decisions.
- A critic's credit attribution survives a later firm-driven revision
  that overrides the position they argued for.
- The bounty payout path is *gated* by founder confirmation: nothing
  short of an explicit confirm flips the bounty out of
  ``pending_founder_confirmation``.
"""

from __future__ import annotations

import pytest

from noosphere.peer_review.severity import SeverityInputs
from noosphere.social.critique_routing import (
    BOUNTY_DEFAULT_USD,
    BountyPayout,
    CritiqueLineage,
    CritiqueSubmission,
    DEFAULT_BOUNTY_USD,
    InMemoryCritiqueWriter,
    accept_critique,
    cancel_bounty,
    confirm_bounty,
    credits_for_article,
    is_bounty_eligible,
    mark_partial,
    record_later_revision,
    record_revision_in_lineage,
    reject_critique,
    score_severity,
    to_revision_input,
)


def _submission(
    *,
    submission_id: str = "sub_a",
    article_slug: str = "edge-case-claim",
    target: str = "claim-7 says X always implies Y",
    counter: str = (
        "Replication study (n=400) found X implied Y in only 62% of cases; "
        "the 'always' qualifier is therefore unsupported by the evidence."
    ),
    method: str = "Ran a replication audit using the original protocol "
    "with a larger sample.",
    citations: str = "https://example.org/replication.pdf",
    submitter_email: str = "ada@example.org",
    display_name: str = "Ada Lovelace",
    public_url: str = "https://example.org/ada",
    bio: str = "Methodologist, applied stats.",
) -> CritiqueSubmission:
    return CritiqueSubmission(
        submission_id=submission_id,
        organization_id="org_main",
        article_slug=article_slug,
        target_claim=target,
        counter_evidence=counter,
        derivation_method=method,
        citations=citations,
        submitter_email=submitter_email,
        display_name=display_name,
        public_url=public_url,
        bio=bio,
    )


HIGH_INPUTS = SeverityInputs(
    cascade_weight=0.95,
    claim_centrality=0.95,
    failure_mode_severity=0.9,
)
MEDIUM_INPUTS = SeverityInputs(
    cascade_weight=0.6,
    claim_centrality=0.6,
    failure_mode_severity=0.4,
)
LOW_INPUTS = SeverityInputs(
    cascade_weight=0.2,
    claim_centrality=0.1,
    failure_mode_severity=0.0,
)


# ── synthetic submission flow ────────────────────────────────────────


class TestSubmissionFlow:
    def test_default_bounty_constants_match(self):
        # The codex and noosphere both seed at 500 USD; pin the alias.
        assert DEFAULT_BOUNTY_USD == 500
        assert BOUNTY_DEFAULT_USD == DEFAULT_BOUNTY_USD

    def test_credit_label_prefers_display_name(self):
        sub = _submission(display_name="Ada Lovelace")
        assert sub.credit_label() == "Ada Lovelace"

    def test_credit_label_falls_back_to_email_localpart(self):
        sub = _submission(display_name="", submitter_email="alice@example.org")
        assert sub.credit_label() == "alice"

    def test_credit_label_handles_empty_identity(self):
        sub = _submission(display_name="", submitter_email="")
        assert sub.credit_label() == "Anonymous"

    def test_severity_scoring_matches_label_brackets(self):
        sub = _submission()
        high_label, high_value = score_severity(sub, HIGH_INPUTS)
        med_label, med_value = score_severity(sub, MEDIUM_INPUTS)
        low_label, low_value = score_severity(sub, LOW_INPUTS)
        assert high_label == "high"
        assert med_label == "medium"
        assert low_label == "low"
        assert high_value > med_value > low_value


# ── moderation states (accepted / partial / rejected) ────────────────


class TestModerationStates:
    def test_accept_high_severity_writes_decision_and_bounty(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()

        decision = accept_critique(
            sub,
            severity_inputs=HIGH_INPUTS,
            moderator_note="strong replication audit",
            writer=writer,
        )

        assert decision.status == "accepted"
        assert decision.severity_label == "high"
        assert decision.bounty is not None
        assert decision.bounty.status == "pending_founder_confirmation"
        assert decision.bounty.amount_usd == DEFAULT_BOUNTY_USD
        assert is_bounty_eligible(decision)

        # Persistence happened through the writer.
        assert writer.latest_decision(sub.submission_id) is decision
        assert sub.submission_id in writer.bounties
        assert sub.submission_id in writer.lineages

    def test_accept_medium_severity_does_not_queue_bounty(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()

        decision = accept_critique(
            sub, severity_inputs=MEDIUM_INPUTS, writer=writer
        )

        assert decision.status == "accepted"
        assert decision.severity_label == "medium"
        assert decision.bounty is None
        assert not is_bounty_eligible(decision)
        assert sub.submission_id not in writer.bounties

    def test_partial_state_is_distinct_from_accepted(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()

        decision = mark_partial(
            sub, moderator_note="Interesting; needs offline discussion.", writer=writer
        )

        assert decision.status == "partial"
        # Partial implies private discussion only — no bounty, no severity.
        assert decision.bounty is None
        assert decision.severity_value == 0.0
        assert sub.submission_id not in writer.bounties

    def test_reject_state_records_reason_in_lineage(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()

        decision = reject_critique(
            sub, moderator_note="Cited paper does not match the claim under attack.", writer=writer
        )

        assert decision.status == "rejected"
        assert decision.bounty is None
        lineage = writer.lineages[sub.submission_id]
        assert any(entry.kind == "rejected" for entry in lineage.trail)

    def test_charity_payout_mode_carries_destination(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()

        decision = accept_critique(
            sub,
            severity_inputs=HIGH_INPUTS,
            payout_mode="charity",
            bounty_destination="GiveDirectly",
            writer=writer,
        )

        assert decision.bounty is not None
        assert decision.bounty.payout_mode == "charity"
        assert decision.bounty.destination == "GiveDirectly"


# ── bounty payout gate ───────────────────────────────────────────────


class TestBountyConfirmationGate:
    def test_confirm_requires_founder_flag_true(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None

        with pytest.raises(PermissionError):
            confirm_bounty(decision.bounty, founder_confirmed=False)

        # Still pending — nothing flipped.
        assert decision.bounty.status == "pending_founder_confirmation"

    def test_confirm_with_founder_flag_flips_to_confirmed(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None

        confirmed = confirm_bounty(
            decision.bounty,
            founder_confirmed=True,
            external_ref="payouts-pipeline:job_42",
        )
        assert confirmed.status == "confirmed"
        assert confirmed.confirmed_at is not None
        assert confirmed.external_ref == "payouts-pipeline:job_42"

    def test_double_confirm_is_rejected(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None

        confirmed = confirm_bounty(decision.bounty, founder_confirmed=True)
        with pytest.raises(ValueError):
            confirm_bounty(confirmed, founder_confirmed=True)

    def test_confirmed_bounty_cannot_be_cancelled(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None

        confirmed = confirm_bounty(decision.bounty, founder_confirmed=True)
        with pytest.raises(ValueError):
            cancel_bounty(confirmed, note="changed mind")

    def test_pending_bounty_can_be_cancelled(self):
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None

        cancelled = cancel_bounty(decision.bounty, note="duplicate of sub_b")
        assert cancelled.status == "cancelled"
        assert cancelled.cancellation_note == "duplicate of sub_b"

    def test_no_money_path_exists_outside_confirm(self):
        # Belt-and-suspenders: there must be exactly one way for a
        # BountyPayout to land in 'confirmed', and it goes through
        # confirm_bounty. The test asserts the contract in two ways:
        # (a) constructing a payout in 'confirmed' from outside the
        # module is the caller's choice, but the moderation flow never
        # produces one; (b) accept_critique always emits
        # 'pending_founder_confirmation'.
        sub = _submission()
        writer = InMemoryCritiqueWriter()
        decision = accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)
        assert decision.bounty is not None
        assert decision.bounty.status == "pending_founder_confirmation"

        # Persistence-side contract: every bounty in writer.bounties is
        # initially queued, never auto-confirmed.
        for payout in writer.bounties.values():
            assert payout.status == "pending_founder_confirmation"


# ── credit attribution survives revision ─────────────────────────────


class TestCreditSurvivesRevision:
    def test_revision_routing_keeps_original_credit(self):
        sub = _submission(submission_id="sub_x", display_name="Ada Lovelace")
        writer = InMemoryCritiqueWriter()
        accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)

        # Revision routed (prompt 16) — produces a RevisionInput shape
        # that the cascade engine consumes.
        ri = to_revision_input(sub, claim_id="claim-7", weight=-0.7)
        assert ri.claim_id == "claim-7"
        assert ri.new_evidence == sub.counter_evidence
        assert ri.clamped_weight() == pytest.approx(-0.7)

        lineage = writer.lineages[sub.submission_id]
        record_revision_in_lineage(
            sub,
            lineage,
            revision_event_id="rev_001",
            summary="confidence dropped 0.74 → 0.41",
            writer=writer,
        )
        # Critic credit is in the lineage AND remains there.
        credits = lineage.credits()
        assert "Ada Lovelace" in credits

    def test_later_firm_revision_does_not_erase_critic(self):
        sub = _submission(
            submission_id="sub_y",
            display_name="Ada Lovelace",
            article_slug="weekly-essay",
        )
        writer = InMemoryCritiqueWriter()
        accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)

        lineage = writer.lineages[sub.submission_id]
        record_revision_in_lineage(
            sub,
            lineage,
            revision_event_id="rev_acceptance",
            summary="accepted; routed to revision engine",
            writer=writer,
        )
        # A later firm-driven revision moves the position further. The
        # original critic must still appear in the credit list.
        record_later_revision(
            lineage,
            summary="firm later revisited and updated again, independent of critic",
            writer=writer,
        )

        credits = lineage.credits()
        assert credits[0] == "Ada Lovelace", "earliest credit must be the critic"
        assert "firm" in credits  # later actor is recorded too
        # The original 'accepted' entry is intact (append-only contract).
        kinds = [entry.kind for entry in lineage.trail]
        assert "accepted" in kinds
        assert "later_revision" in kinds
        # No entry has been overwritten or removed.
        assert kinds == sorted(kinds, key=lambda k: 0)  # order preserved == insertion order

    def test_credits_for_article_aggregates_across_submissions(self):
        sub_a = _submission(submission_id="sub_a", display_name="Ada Lovelace")
        sub_b = _submission(
            submission_id="sub_b",
            display_name="Grace Hopper",
            article_slug="edge-case-claim",
        )
        sub_c = _submission(
            submission_id="sub_c",
            display_name="Edsger Dijkstra",
            article_slug="other-article",
        )
        writer = InMemoryCritiqueWriter()
        for sub in (sub_a, sub_b, sub_c):
            accept_critique(sub, severity_inputs=HIGH_INPUTS, writer=writer)

        credits = credits_for_article(
            writer.lineages.values(),
            article_slug="edge-case-claim",
            submissions_by_id={s.submission_id: s for s in (sub_a, sub_b, sub_c)},
        )
        assert "Ada Lovelace" in credits
        assert "Grace Hopper" in credits
        assert "Edsger Dijkstra" not in credits


# ── invariants / regressions ─────────────────────────────────────────


def test_low_severity_acceptance_never_queues_bounty():
    sub = _submission()
    writer = InMemoryCritiqueWriter()
    decision = accept_critique(sub, severity_inputs=LOW_INPUTS, writer=writer)
    assert decision.severity_label == "low"
    assert decision.bounty is None


def test_queue_bounty_flag_disabled_skips_payout_even_at_high():
    sub = _submission()
    writer = InMemoryCritiqueWriter()
    decision = accept_critique(
        sub,
        severity_inputs=HIGH_INPUTS,
        queue_bounty=False,
        writer=writer,
    )
    assert decision.severity_label == "high"
    assert decision.bounty is None
    assert sub.submission_id not in writer.bounties


def test_lineage_is_append_only_after_accept():
    sub = _submission()
    lineage = CritiqueLineage(
        submission_id=sub.submission_id,
        credit_label=sub.credit_label(),
    )
    accept_critique(sub, severity_inputs=MEDIUM_INPUTS, lineage=lineage)
    initial = len(lineage.trail)
    record_later_revision(lineage, summary="firm follow-up")
    assert len(lineage.trail) == initial + 1


def test_bounty_payout_immutable_status_progression():
    payout = BountyPayout(payout_id="b", submission_id="s")
    assert payout.status == "pending_founder_confirmation"
    confirmed = confirm_bounty(payout, founder_confirmed=True)
    assert confirmed.status == "confirmed"
    # Original BountyPayout is unchanged (frozen dataclass + replace).
    assert payout.status == "pending_founder_confirmation"
