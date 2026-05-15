"""Tests for the Methodology Review Week module.

The prompt pins four families of invariants:

* **Schedule generation.** A quarter produces a 5-working-day window;
  the days are consecutive weekdays starting on a Monday; the focus
  sequence is fixed (drift, failure modes, domain bounds, retirement
  candidates, methodology section); ``next_review_week_after`` lands on
  the soonest week whose start is on or after today.
* **Queue filtering per day.** ``filter_attention_for_day`` returns
  exactly the queues spec'd for that focus; day 5 returns an empty list.
* **Summary persistence + signed round-trip.** A signed summary loads
  back with the signature intact; mutation of the body invalidates it;
  attempting to overwrite a signed summary with a different body raises.
* **Opt-in policy.** ``mark_postponed`` and ``mark_skipped`` log the
  decision without raising; the public hint reflects the change and
  does not punish a skipped week.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.inquiry.methodology_review_week import (
    DAY_FOCUS,
    DAY_LABELS,
    DRAFT_BANNER,
    QUEUES_BY_FOCUS,
    SCHEMA,
    STATUS_COMPLETED,
    STATUS_POSTPONED,
    STATUS_SCHEDULED,
    STATUS_SKIPPED,
    DaySummary,
    ReviewWeek,
    ReviewWeekKeyring,
    collect_methodology_section_inputs,
    default_start_for_quarter,
    draft_summary_from_queue,
    filter_attention_for_day,
    iter_history,
    load_summary,
    mark_postponed,
    mark_skipped,
    next_review_week_after,
    public_hint,
    save_summary,
    schedule_for_quarter,
    schedule_for_year,
    sign_summary,
    summary_path,
    verify_summary,
)


# ── Schedule generation ──────────────────────────────────────────────


class TestScheduleGeneration:
    def test_quarter_window_is_five_weekdays_starting_monday(self) -> None:
        week = schedule_for_quarter(2026, 2)
        assert len(week.days) == 5
        # First day is a Monday and days are consecutive weekdays.
        assert week.days[0].on.weekday() == 0
        for prev, nxt in zip(week.days, week.days[1:]):
            assert nxt.on == prev.on + timedelta(days=1)
        # All five days are weekdays (Mon..Fri).
        assert {d.on.weekday() for d in week.days} == {0, 1, 2, 3, 4}

    def test_day_focus_sequence_is_fixed(self) -> None:
        week = schedule_for_quarter(2026, 2)
        assert tuple(d.focus for d in week.days) == DAY_FOCUS
        assert week.days[0].focus == "drift_events"
        assert week.days[1].focus == "failure_modes"
        assert week.days[2].focus == "domain_bounds"
        assert week.days[3].focus == "retirement_candidates"
        assert week.days[4].focus == "methodology_section"

    def test_default_start_is_first_monday_of_mid_quarter_month(self) -> None:
        # Q1 → first Monday in February; Q2 → first Monday in May, etc.
        cases = {
            (2026, 1): date(2026, 2, 1).weekday(),
            (2026, 2): date(2026, 5, 1).weekday(),
            (2026, 3): date(2026, 8, 1).weekday(),
            (2026, 4): date(2026, 11, 1).weekday(),
        }
        for (year, quarter), _ in cases.items():
            start = default_start_for_quarter(year, quarter)
            assert start.weekday() == 0
            # Start is in the second month of the quarter.
            expected_month = (quarter - 1) * 3 + 2
            assert start.month == expected_month

    def test_schedule_for_year_emits_four_weeks(self) -> None:
        weeks = schedule_for_year(2026)
        assert len(weeks) == 4
        assert [w.quarter for w in weeks] == [1, 2, 3, 4]
        # Each week's start strictly precedes the next.
        for prev, nxt in zip(weeks, weeks[1:]):
            assert prev.start < nxt.start

    def test_next_review_week_lands_on_or_after_today(self) -> None:
        today = date(2026, 6, 1)  # mid-Q2
        nxt = next_review_week_after(today)
        assert nxt.start >= today
        # Should land in Q3 since Q2's mid-quarter Monday is in May.
        assert nxt.quarter == 3

    def test_explicit_start_override_must_be_a_monday(self) -> None:
        with pytest.raises(ValueError):
            schedule_for_quarter(2026, 2, start=date(2026, 5, 5))  # Tuesday


# ── Queue filtering per day ──────────────────────────────────────────


def _row(queue: str, item_id: str, severity: str = "medium") -> dict:
    return {
        "queue": queue,
        "itemId": item_id,
        "severity": severity,
        "preview": f"row {item_id} on {queue}",
        "createdAt": "2026-05-04T12:00:00Z",
    }


class TestQueueFiltering:
    def test_drift_day_keeps_drift_and_calibration_only(self) -> None:
        items = [
            _row("drift", "d1"),
            _row("calibration_breach", "c1"),
            _row("peer_review", "p1"),
            _row("open_question", "o1"),
        ]
        out = filter_attention_for_day(items, focus="drift_events")
        assert {r["queue"] for r in out} == {"drift", "calibration_breach"}

    def test_failure_modes_day_keeps_peer_review_and_citation_verdict(self) -> None:
        items = [
            _row("peer_review", "p1"),
            _row("citation_verdict", "v1"),
            _row("drift", "d1"),
        ]
        out = filter_attention_for_day(items, focus="failure_modes")
        assert {r["queue"] for r in out} == {"peer_review", "citation_verdict"}

    def test_domain_bound_day_keeps_source_triage_and_retractions(self) -> None:
        items = [
            _row("source_triage", "s1"),
            _row("retraction_propagation", "r1"),
            _row("drift", "d1"),
        ]
        out = filter_attention_for_day(items, focus="domain_bounds")
        assert {r["queue"] for r in out} == {
            "source_triage",
            "retraction_propagation",
        }

    def test_retirement_day_keeps_calibration_and_drift(self) -> None:
        items = [
            _row("drift", "d1"),
            _row("calibration_breach", "c1"),
            _row("peer_review", "p1"),
        ]
        out = filter_attention_for_day(items, focus="retirement_candidates")
        assert {r["queue"] for r in out} == {"drift", "calibration_breach"}

    def test_methodology_section_day_filters_to_empty(self) -> None:
        items = [_row("drift", "d1"), _row("peer_review", "p1")]
        assert filter_attention_for_day(items, focus="methodology_section") == []

    def test_unknown_focus_raises(self) -> None:
        with pytest.raises(ValueError):
            filter_attention_for_day([], focus="not_a_focus")

    def test_unknown_queue_rows_are_dropped(self) -> None:
        items = [_row("nonsense_queue", "x1"), _row("drift", "d1")]
        out = filter_attention_for_day(items, focus="drift_events")
        assert [r["itemId"] for r in out] == ["d1"]


# ── Drafting ─────────────────────────────────────────────────────────


class TestDraftSummary:
    def test_draft_carries_the_draft_banner_and_is_clearly_a_draft(self) -> None:
        week = schedule_for_quarter(2026, 2)
        draft = draft_summary_from_queue(
            week,
            day_index=1,
            queue_items=[_row("drift", "d1", "high")],
        )
        assert draft.draft_body.startswith(DRAFT_BANNER)
        # Founder's body is empty — the draft is never the final.
        assert draft.body == ""

    def test_draft_includes_queue_counts_by_severity(self) -> None:
        week = schedule_for_quarter(2026, 2)
        items = [
            _row("drift", "d1", "high"),
            _row("drift", "d2", "medium"),
            _row("calibration_breach", "c1", "low"),
        ]
        draft = draft_summary_from_queue(week, day_index=1, queue_items=items)
        assert "1 high" in draft.draft_body
        assert "1 medium" in draft.draft_body
        assert "1 low" in draft.draft_body

    def test_methodology_section_day_does_not_draft_prose(self) -> None:
        week = schedule_for_quarter(2026, 2)
        draft = draft_summary_from_queue(week, day_index=5, queue_items=[])
        assert "writeup" in draft.draft_body.lower()


# ── Summary persistence + signed round-trip ──────────────────────────


@pytest.fixture
def keyring(tmp_path: Path) -> ReviewWeekKeyring:
    pytest.importorskip("nacl.signing")
    return ReviewWeekKeyring(root=tmp_path / "keys")


def _written_summary(week: ReviewWeek, day: int = 1, body: str = "x") -> DaySummary:
    return DaySummary(
        week_slug=week.slug,
        day_index=day,
        focus=DAY_FOCUS[day - 1],
        body=body,
        written_at=datetime(2026, 5, 4, 17, 0, tzinfo=timezone.utc),
    )


class TestSummaryPersistence:
    def test_save_then_load_round_trips_unsigned(self, tmp_path: Path) -> None:
        week = schedule_for_quarter(2026, 2)
        summary = _written_summary(week, body="The drift on m_geometry warrants a review.")
        path = save_summary(summary, root=tmp_path)
        assert path == summary_path(week.slug, 1, root=tmp_path)
        loaded = load_summary(week.slug, 1, root=tmp_path)
        assert loaded is not None
        assert loaded.body == summary.body
        assert loaded.focus == "drift_events"

    def test_unsigned_summary_can_be_edited_freely(self, tmp_path: Path) -> None:
        week = schedule_for_quarter(2026, 2)
        s1 = _written_summary(week, body="first take")
        save_summary(s1, root=tmp_path)
        s2 = _written_summary(week, body="revised take")
        # Unsigned overwrite is allowed.
        save_summary(s2, root=tmp_path)
        loaded = load_summary(week.slug, 1, root=tmp_path)
        assert loaded is not None
        assert loaded.body == "revised take"

    def test_signed_summary_round_trip_verifies(
        self, tmp_path: Path, keyring: ReviewWeekKeyring
    ) -> None:
        week = schedule_for_quarter(2026, 2)
        summary = _written_summary(week, body="The drift on m_geometry warrants a review.")
        sign_summary(summary, keyring=keyring)
        assert summary.signature_hex
        assert summary.signing_key_fingerprint
        assert verify_summary(summary, keyring=keyring) is True

        save_summary(summary, root=tmp_path)
        loaded = load_summary(week.slug, 1, root=tmp_path)
        assert loaded is not None
        assert loaded.signature_hex == summary.signature_hex
        assert verify_summary(loaded, keyring=keyring) is True

    def test_signature_invalidates_on_body_mutation(
        self, tmp_path: Path, keyring: ReviewWeekKeyring
    ) -> None:
        week = schedule_for_quarter(2026, 2)
        summary = _written_summary(week, body="original body")
        sign_summary(summary, keyring=keyring)
        # Forge a tampered version with the same signature/fingerprint
        # but a different body — verify must reject.
        tampered = DaySummary(
            week_slug=summary.week_slug,
            day_index=summary.day_index,
            focus=summary.focus,
            body="forged body",
            signature_hex=summary.signature_hex,
            signing_key_fingerprint=summary.signing_key_fingerprint,
            signed_at=summary.signed_at,
        )
        assert verify_summary(tampered, keyring=keyring) is False

    def test_signed_summary_cannot_be_overwritten_with_different_body(
        self, tmp_path: Path, keyring: ReviewWeekKeyring
    ) -> None:
        week = schedule_for_quarter(2026, 2)
        s1 = _written_summary(week, body="signed and immutable")
        sign_summary(s1, keyring=keyring)
        save_summary(s1, root=tmp_path)

        # Re-saving the SAME body is idempotent.
        save_summary(s1, root=tmp_path)

        # Attempting to overwrite with a different body must raise.
        s2 = _written_summary(week, body="trying to rewrite history")
        sign_summary(s2, keyring=keyring)
        with pytest.raises(RuntimeError):
            save_summary(s2, root=tmp_path)

    def test_founder_edits_are_tracked_and_drop_the_signature(
        self, keyring: ReviewWeekKeyring
    ) -> None:
        week = schedule_for_quarter(2026, 2)
        summary = _written_summary(week, body="first draft")
        sign_summary(summary, keyring=keyring)
        prior_sig = summary.signature_hex
        assert prior_sig

        summary.apply_founder_edit(
            "revised text", at=datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)
        )
        assert summary.body == "revised text"
        assert summary.signature_hex == ""
        assert summary.signed_at is None
        assert len(summary.edits) == 1
        assert summary.edits[0].prior_body == "first draft"

        # Re-signing after the edit succeeds and produces a *different*
        # signature.
        sign_summary(summary, keyring=keyring)
        assert summary.signature_hex != prior_sig
        assert verify_summary(summary, keyring=keyring) is True

    def test_iter_history_lists_directories_with_summary_state(
        self, tmp_path: Path
    ) -> None:
        for quarter in (1, 2):
            week = schedule_for_quarter(2026, quarter)
            s = _written_summary(week, body=f"q{quarter} day1")
            save_summary(s, root=tmp_path)
        rows = iter_history(root=tmp_path)
        assert len(rows) == 2
        # Latest first.
        assert rows[0]["quarter"] == 2
        assert rows[1]["quarter"] == 1
        # Day 1 has a summary; days 2..5 do not.
        for row in rows:
            d1 = next(d for d in row["days"] if d["day_index"] == 1)
            d2 = next(d for d in row["days"] if d["day_index"] == 2)
            assert d1["has_summary"] is True
            assert d2["has_summary"] is False


# ── Opt-in policy ────────────────────────────────────────────────────


class TestOptInPolicy:
    def test_mark_postponed_keeps_quarter_identity_and_logs_new_date(self) -> None:
        original = schedule_for_quarter(2026, 2)
        new_start = date(2026, 6, 1)  # Monday
        rescheduled = mark_postponed(
            original, new_start=new_start, reason="founder travelling"
        )
        assert rescheduled.year == original.year
        assert rescheduled.quarter == original.quarter
        assert rescheduled.status == STATUS_POSTPONED
        assert rescheduled.postponed_to == new_start
        assert rescheduled.start == new_start
        assert rescheduled.postpone_reason == "founder travelling"

    def test_mark_skipped_logs_status_without_changing_dates(self) -> None:
        original = schedule_for_quarter(2026, 2)
        skipped = mark_skipped(original, reason="merge freeze")
        assert skipped.status == STATUS_SKIPPED
        assert skipped.start == original.start
        assert skipped.postpone_reason == "merge freeze"

    def test_public_hint_reflects_postponed_start(self) -> None:
        completed = ReviewWeek(
            year=2026,
            quarter=1,
            days=schedule_for_quarter(2026, 1).days,
            status=STATUS_COMPLETED,
        )
        postponed = mark_postponed(
            schedule_for_quarter(2026, 2),
            new_start=date(2026, 6, 1),
            reason="travel",
        )
        hint = public_hint([completed, postponed], today=date(2026, 5, 20))
        assert hint.last_on == completed.end
        assert hint.next_on == date(2026, 6, 1)
        text = hint.to_string()
        assert "Last review week:" in text
        assert "next review week:" in text
        assert "2026-06-01" in text

    def test_public_hint_skips_skipped_weeks(self) -> None:
        skipped = mark_skipped(schedule_for_quarter(2026, 2))
        # No completed week yet; next must fall through to the
        # scheduler default (Q3) rather than the skipped Q2.
        hint = public_hint([skipped], today=date(2026, 5, 20))
        assert hint.last_on is None
        assert hint.next_on is not None
        assert hint.next_on != skipped.start


# ── Seasonal-review handoff ──────────────────────────────────────────


class TestSeasonalReviewHandoff:
    def test_collect_inputs_records_missing_days_explicitly(
        self, tmp_path: Path
    ) -> None:
        week = schedule_for_quarter(2026, 2)
        # Write day 1 and day 3 only.
        save_summary(_written_summary(week, day=1, body="drift notes"), root=tmp_path)
        save_summary(
            _written_summary(week, day=3, body="domain notes"), root=tmp_path
        )
        bundle = collect_methodology_section_inputs(week, root=tmp_path)
        assert bundle["schema"] == SCHEMA
        days = {d["day_index"]: d for d in bundle["days"]}
        assert days[1]["data_available"] is True
        assert days[2]["data_available"] is False
        assert days[3]["data_available"] is True
        assert days[4]["data_available"] is False
        # Day 5 (the writeup) is not part of the inputs bundle.
        assert 5 not in days
