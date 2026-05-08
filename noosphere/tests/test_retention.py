"""Tests for retention policies, runner, and DSR handler.

Builds a synthetic, in-memory dataset spanning every retention class
and asserts:

  * each policy reaches its expected target set,
  * the DSR report is comprehensive against the synthetic data,
  * confirmation-required policies do NOT silently auto-execute,
  * deletion really deletes (not just tombstones).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.decay import dsr as dsr_mod
from noosphere.decay.dsr import (
    DSRContext,
    DSRRecord,
    build_deletion_plan,
    build_report,
    email_hash,
    execute_deletion_plan,
)
from noosphere.decay.retention_policies import (
    FounderOverride,
    LifecycleAction,
    all_policies,
    get_policy,
    policy_keys,
)
from noosphere.decay.retention_runner import (
    RetentionContext,
    execute,
    survey,
)


NOW = datetime(2026, 5, 8, tzinfo=timezone.utc)


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


# ── Policy table sanity ──────────────────────────────────────────────────────


def test_policy_table_keys_are_unique_and_stable() -> None:
    keys = policy_keys()
    assert len(keys) == len(set(keys))
    # Stability check: these are the seven canonical classes the firm
    # has chosen to retain. Adding/removing a class is a deliberate act.
    assert set(keys) == {
        "spans",
        "contact_submissions",
        "public_responses",
        "embeddings",
        "transcripts",
        "draft_conclusions",
        "retired_objects",
    }


def test_locked_policy_cannot_auto_execute() -> None:
    p = get_policy("retired_objects")
    assert p.override == FounderOverride.LOCKED
    assert p.auto_execute is False


def test_rollup_policy_has_target() -> None:
    p = get_policy("spans")
    assert p.action == LifecycleAction.ROLLUP_AND_DELETE
    assert p.rollup_target == "MethodMetricRollup"


# ── Synthetic dataset + adapters ─────────────────────────────────────────────


@pytest.fixture()
def dataset():
    """Per-class rows, each tagged with whether they SHOULD be a target."""
    return {
        "spans": [
            ("span-old", _ago(45), True),
            ("span-mid", _ago(31), True),
            ("span-fresh", _ago(5), False),
        ],
        "contact_submissions": [
            ("cs-old", _ago(200), True),
            ("cs-fresh", _ago(10), False),
        ],
        "public_responses": [
            ("pr-old", _ago(365 * 7 + 5), True),
            ("pr-mid", _ago(365), False),
        ],
        # (id, source_id, created_at, expected_target)
        "embeddings": [
            ("emb-orphan-old", None, _ago(40), True),
            ("emb-orphan-fresh", None, _ago(5), False),
            ("emb-bound", "src-1", _ago(500), False),
        ],
        "transcripts": [
            ("t-1", _ago(2000), False),
        ],
    }


@pytest.fixture()
def deleted_log():
    return {
        "spans": [],
        "contact_submissions": [],
        "public_responses": [],
        "embeddings": [],
        "transcripts": [],
    }


@pytest.fixture()
def ctx(dataset, deleted_log) -> RetentionContext:
    def _list_pairs(key: str):
        return lambda: [(r[0], r[1]) for r in dataset[key]]

    def _list_embeddings():
        return [(r[0], r[1], r[2]) for r in dataset["embeddings"]]

    def _delete(key: str):
        def _do(ids):
            ids = list(ids)
            deleted_log[key].extend(ids)
            # Mutate dataset so a second survey returns nothing.
            if key == "embeddings":
                dataset[key] = [r for r in dataset[key] if r[0] not in ids]
            else:
                dataset[key] = [r for r in dataset[key] if r[0] not in ids]
            return len(ids)

        return _do

    return RetentionContext(
        now=NOW,
        list_spans=_list_pairs("spans"),
        delete_spans=_delete("spans"),
        list_contact_submissions=_list_pairs("contact_submissions"),
        delete_contact_submissions=_delete("contact_submissions"),
        list_public_responses=_list_pairs("public_responses"),
        delete_public_responses=_delete("public_responses"),
        list_embeddings=_list_embeddings,
        delete_embeddings=_delete("embeddings"),
        list_transcripts=_list_pairs("transcripts"),
        delete_transcripts=_delete("transcripts"),
    )


# ── Survey reaches expected targets ──────────────────────────────────────────


def test_survey_targets_per_policy(ctx, dataset) -> None:
    previews = {p.policy_key: p for p in survey(ctx)}

    expected: dict[str, set[str]] = {
        "spans": {r[0] for r in dataset["spans"] if r[2]},
        "contact_submissions": {r[0] for r in dataset["contact_submissions"] if r[2]},
        "public_responses": {r[0] for r in dataset["public_responses"] if r[2]},
        "embeddings": {r[0] for r in dataset["embeddings"] if r[3]},
        "transcripts": set(),  # never auto-targeted
    }

    for key, want in expected.items():
        targets = {t.object_id for t in previews[key].to_delete}
        archive = {t.object_id for t in previews[key].to_archive}
        got = targets | archive
        assert got == want, f"{key}: expected {want}, got {got}"


def test_survey_includes_every_policy(ctx) -> None:
    previews = survey(ctx)
    keys = {p.policy_key for p in previews}
    assert keys == set(policy_keys())


# ── Execute respects auto-execute / confirmation ─────────────────────────────


def test_auto_execute_runs_without_confirm(ctx, deleted_log) -> None:
    previews = survey(ctx)
    reports = execute(previews, ctx=ctx)
    by_key = {r.policy_key: r for r in reports}

    assert by_key["spans"].deleted == 2
    assert by_key["embeddings"].deleted == 1

    # Confirmation-required policies must NOT have run.
    assert by_key["contact_submissions"].deleted == 0
    assert by_key["contact_submissions"].skipped > 0
    assert by_key["public_responses"].deleted == 0


def test_confirmation_required_policies_run_only_with_confirm(ctx, deleted_log) -> None:
    previews = survey(ctx)
    reports = execute(
        previews,
        ctx=ctx,
        confirmed_policies={"contact_submissions"},
    )
    by_key = {r.policy_key: r for r in reports}
    assert by_key["contact_submissions"].deleted == 1
    assert by_key["public_responses"].deleted == 0


def test_missed_confirmation_does_not_carry_over(ctx) -> None:
    # Day 1: no confirmation passed → nothing runs for confirm-required.
    p1 = survey(ctx)
    r1 = execute(p1, ctx=ctx)
    by_key = {r.policy_key: r for r in r1}
    assert by_key["contact_submissions"].deleted == 0

    # Day 2 (re-survey): still nothing without explicit confirm.
    p2 = survey(ctx)
    r2 = execute(p2, ctx=ctx)
    by_key2 = {r.policy_key: r for r in r2}
    assert by_key2["contact_submissions"].deleted == 0


def test_deletion_actually_removes_rows(ctx, dataset) -> None:
    # Run survey, then auto-execute spans.
    previews = survey(ctx)
    execute(previews, ctx=ctx)
    # Re-survey — the deleted span should be gone (not tombstoned).
    previews2 = survey(ctx)
    spans_preview = next(p for p in previews2 if p.policy_key == "spans")
    assert spans_preview.to_delete == []
    remaining_ids = {r[0] for r in dataset["spans"]}
    assert "span-old" not in remaining_ids
    assert "span-fresh" in remaining_ids


# ── DSR report is comprehensive ──────────────────────────────────────────────


@pytest.fixture()
def dsr_ctx(dataset, deleted_log) -> DSRContext:
    """A subject identified by the email ``user@example.com`` is
    represented in: contact_submissions, public_responses, transcripts,
    embeddings — but NOT spans (sanitised) or retired_objects (none)."""
    subject_email = "user@example.com"
    sender_hash = email_hash(subject_email)

    subject_records = {
        "contact_submissions": [
            DSRRecord(
                object_id="cs-old",
                summary="contact form: 'Question' (2026-01-01)",
                created_at=_ago(200),
            ),
        ],
        "public_responses": [
            DSRRecord(
                object_id="pr-mid",
                summary="response on conclusion C-42",
                created_at=_ago(365),
            ),
        ],
        "transcripts": [
            DSRRecord(
                object_id="t-1",
                summary="upload: interview-2024-03",
                created_at=_ago(2000),
            ),
        ],
        "embeddings": [
            DSRRecord(
                object_id="emb-bound",
                summary="vector for src-1",
                created_at=_ago(500),
                extra={"source_id": "src-1"},
            ),
        ],
        "spans": [],
        "draft_conclusions": [],
        "retired_objects": [],
    }

    def make_finder(key: str):
        def _find(identifier: str):
            if identifier != subject_email and identifier != sender_hash:
                return []
            return list(subject_records[key])

        return _find

    def make_deleter(key: str):
        def _do(ids):
            for oid in ids:
                subject_records[key] = [
                    r for r in subject_records[key] if r.object_id != oid
                ]
                # Also remove from the dataset adapter so a follow-up
                # survey wouldn't see it either.
                if key in dataset:
                    if key == "embeddings":
                        dataset[key] = [r for r in dataset[key] if r[0] != oid]
                    else:
                        dataset[key] = [r for r in dataset[key] if r[0] != oid]
            return len(list(ids))

        return _do

    return DSRContext(
        find_contact_submissions=make_finder("contact_submissions"),
        delete_contact_submissions=make_deleter("contact_submissions"),
        find_public_responses=make_finder("public_responses"),
        delete_public_responses=make_deleter("public_responses"),
        find_transcripts=make_finder("transcripts"),
        delete_transcripts=make_deleter("transcripts"),
        find_embeddings=make_finder("embeddings"),
        delete_embeddings=make_deleter("embeddings"),
        find_spans=make_finder("spans"),
        delete_spans=make_deleter("spans"),
        find_draft_conclusions=make_finder("draft_conclusions"),
        delete_draft_conclusions=make_deleter("draft_conclusions"),
        find_retired_objects=make_finder("retired_objects"),
    )


def test_dsr_report_covers_every_policy_class(dsr_ctx) -> None:
    report = build_report("user@example.com", dsr_ctx)
    # Every policy class appears as a key — even when empty — so the
    # report is auditable as comprehensive.
    assert set(report.findings.keys()) == set(policy_keys())


def test_dsr_report_finds_subject_records(dsr_ctx) -> None:
    report = build_report("user@example.com", dsr_ctx)
    assert report.total() == 4
    found = {k: [r.object_id for r in v] for k, v in report.findings.items()}
    assert "cs-old" in found["contact_submissions"]
    assert "pr-mid" in found["public_responses"]
    assert "t-1" in found["transcripts"]
    assert "emb-bound" in found["embeddings"]


def test_dsr_deletion_plan_separates_held_from_deletable(dsr_ctx) -> None:
    report = build_report("user@example.com", dsr_ctx)
    plan = build_deletion_plan(report)
    # Nothing in retired_objects for this subject, so held is empty;
    # everything else is deletable.
    assert plan.held == {}
    assert set(plan.deletable.keys()) == {
        "contact_submissions",
        "public_responses",
        "transcripts",
        "embeddings",
    }


def test_dsr_executes_only_with_matching_confirm_token(dsr_ctx) -> None:
    report = build_report("user@example.com", dsr_ctx)
    plan = build_deletion_plan(report)
    with pytest.raises(ValueError):
        execute_deletion_plan(plan, dsr_ctx, confirm_token="wrong")
    result = execute_deletion_plan(
        plan, dsr_ctx, confirm_token="user@example.com"
    )
    assert result.total_deleted() == 4


def test_dsr_records_for_unknown_subject_are_empty(dsr_ctx) -> None:
    report = build_report("nobody@example.com", dsr_ctx)
    assert report.total() == 0


def test_email_hash_matches_response_triage_convention() -> None:
    # ResponseTriage stores SHA-256 of the lowercased email; the DSR
    # helper must produce the same bytes so a finder can join on it.
    assert email_hash("Foo@Example.com") == email_hash("foo@example.com")
    assert len(email_hash("a@b.c")) == 64


# ── Privacy page consistency ────────────────────────────────────────────────


def test_every_policy_has_privacy_summary() -> None:
    for p in all_policies():
        assert p.privacy_summary, f"{p.key} missing privacy_summary"
        # Must contain the TTL number when one exists, so prose can't
        # silently disagree with the policy.
        if p.ttl_days is not None:
            # Allow either raw days, "30 days", or "7 years" style.
            ttl_repr_options = [
                str(p.ttl_days),
                f"{p.ttl_days} days",
                f"{p.ttl_days // 365} year" if p.ttl_days >= 365 else "",
                f"{p.ttl_days // 365} years" if p.ttl_days >= 365 else "",
            ]
            assert any(
                opt and opt in p.privacy_summary for opt in ttl_repr_options
            ), f"{p.key}: TTL not visible in summary: {p.privacy_summary!r}"
