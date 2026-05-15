"""Tests for the formal method-retirement workflow.

The constraints the prompt pins, and where each is exercised:

1. **A method cannot move ACTIVE → RETIRED (or ACTIVE → DEPRECATED)
   directly.** The UNDER_REVIEW step is mandatory and RETIRED is
   terminal — see ``TestStateMachine``.
2. **The registry refuses calls to RETIRED methods** with a typed error
   that points to the replacement, and **warns on DEPRECATED** — see
   ``TestRegistryGate``. Retired methods stay importable for historical
   re-analysis via ``include_retired=True``.
3. **Deprecating a method flags every conclusion it produced with a
   sunset banner**, and **schedules reanalysis under the replacement** —
   see ``TestMigration``.
4. The four retirement criteria, including the rule that an
   *inconclusive* ablation is not grounds for retirement — see
   ``TestCriteria``.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.models import Method, MethodImplRef, MethodType
from noosphere.methods._registry import MethodRegistry
from noosphere.methods.retirement import (
    DORMANCY_DAYS,
    SUSTAINED_DRIFT_DAYS,
    DeprecatedMethodWarning,
    MigrationPlan,
    RetiredMethodError,
    RetirementCriterion,
    RetirementRecord,
    RetirementSignals,
    RetirementState,
    RetirementTransitionError,
    assert_can_transition,
    can_transition,
    load_retirement_records,
    memo_path,
    parse_memo,
    plan_migration,
    qualifies_for_review,
    render_memo,
    update_memo,
    write_memo,
)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_method(name: str, version: str = "1.0.0", status: str = "active") -> Method:
    return Method(
        method_id=f"{name}_{version}_{status}",
        name=name,
        version=version,
        method_type=MethodType.EXTRACTION,
        input_schema={},
        output_schema={},
        description="test method",
        rationale="test",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module="test", fn_name="test_fn", git_sha="abc123"
        ),
        owner="test",
        status=status,
        nondeterministic=False,
        created_at=datetime.now(timezone.utc),
    )


def _under_review(method: str = "old_method", replacement: str = "new_method") -> RetirementRecord:
    """A record that has passed through the mandatory UNDER_REVIEW step."""
    rec = RetirementRecord(method=method)
    rec.open_review(
        replacement=replacement,
        rationale="ablation recommends REMOVE",
        actor="founder",
        at=_utc(2026, 1, 1),
        sunset_at=_utc(2026, 3, 1),
    )
    return rec


# ── Constraint 1: state-machine transitions ───────────────────────────────


class TestStateMachine:
    def test_happy_path_active_to_retired(self) -> None:
        rec = RetirementRecord(method="m")
        assert rec.state == RetirementState.ACTIVE

        rec.open_review(
            replacement="m2", rationale="dormant", actor="founder",
            at=_utc(2026, 1, 1),
        )
        assert rec.state == RetirementState.UNDER_REVIEW

        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        assert rec.state == RetirementState.DEPRECATED

        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        assert rec.state == RetirementState.RETIRED

        # The ledger is the permanent record: every transition is kept.
        assert [t.to_state for t in rec.transitions] == [
            RetirementState.UNDER_REVIEW,
            RetirementState.DEPRECATED,
            RetirementState.RETIRED,
        ]

    def test_active_cannot_jump_straight_to_retired(self) -> None:
        """The UNDER_REVIEW step is mandatory — no ACTIVE → RETIRED edge."""
        assert not can_transition(
            RetirementState.ACTIVE, RetirementState.RETIRED
        )
        rec = RetirementRecord(method="m")
        with pytest.raises(RetirementTransitionError, match="mandatory"):
            rec.retire(actor="founder", at=_utc(2026, 1, 1))
        assert rec.state == RetirementState.ACTIVE
        assert rec.transitions == []

    def test_active_cannot_jump_straight_to_deprecated(self) -> None:
        assert not can_transition(
            RetirementState.ACTIVE, RetirementState.DEPRECATED
        )
        rec = RetirementRecord(method="m")
        with pytest.raises(RetirementTransitionError, match="mandatory"):
            rec.accept(actor="founder", at=_utc(2026, 1, 1))

    def test_retired_is_terminal(self) -> None:
        assert _ALLOWED_FROM_RETIRED() == frozenset()
        rec = _under_review()
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        # No outgoing edge from RETIRED — not even back to ACTIVE.
        with pytest.raises(RetirementTransitionError, match="terminal"):
            rec.revive(actor="founder", at=_utc(2026, 4, 1), reason="oops")

    def test_under_review_can_be_rejected_back_to_active(self) -> None:
        rec = _under_review()
        rec.reject(actor="founder", at=_utc(2026, 1, 10))
        assert rec.state == RetirementState.ACTIVE
        # The memo / record survives the rejection — it is the permanent
        # record that the review happened.
        assert len(rec.transitions) == 2
        assert rec.transitions[-1].reason

    def test_deprecated_can_be_revived(self) -> None:
        rec = _under_review()
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.revive(actor="founder", at=_utc(2026, 1, 20), reason="false alarm")
        assert rec.state == RetirementState.ACTIVE

    def test_assert_can_transition_messages(self) -> None:
        # ACTIVE → RETIRED is rejected for the mandatory-review reason.
        with pytest.raises(RetirementTransitionError, match="mandatory"):
            assert_can_transition(
                RetirementState.ACTIVE, RetirementState.RETIRED
            )
        # A legal transition does not raise.
        assert_can_transition(
            RetirementState.ACTIVE, RetirementState.UNDER_REVIEW
        )


def _ALLOWED_FROM_RETIRED() -> frozenset:
    from noosphere.methods.retirement import _ALLOWED_TRANSITIONS

    return _ALLOWED_TRANSITIONS[RetirementState.RETIRED]


# ── Constraint 2: registry refuses RETIRED, warns DEPRECATED ──────────────


class TestRegistryGate:
    def test_retired_method_call_is_refused_with_typed_error(self) -> None:
        reg = MethodRegistry()
        reg.register(_make_method("old_method"), lambda x: x)

        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        reg.set_retirement(rec)

        with pytest.raises(RetiredMethodError) as exc:
            reg.get("old_method")
        # The typed error points to the replacement.
        assert exc.value.replacement == "new_method"
        assert exc.value.method == "old_method"
        assert "new_method" in str(exc.value)

    def test_retired_method_still_importable_for_reanalysis(self) -> None:
        """Retired methods are not deleted — include_retired resolves them."""
        reg = MethodRegistry()
        fn = lambda x: x  # noqa: E731
        reg.register(_make_method("old_method"), fn)
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        reg.set_retirement(rec)

        spec, resolved = reg.get("old_method", include_retired=True)
        assert spec.name == "old_method"
        assert resolved is fn

    def test_retired_pinned_version_is_also_refused(self) -> None:
        reg = MethodRegistry()
        reg.register(_make_method("old_method", "1.0.0"), lambda x: x)
        reg.register(_make_method("old_method", "2.0.0"), lambda x: x)
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        reg.set_retirement(rec)

        # Retirement is keyed on identity — every version is refused.
        with pytest.raises(RetiredMethodError):
            reg.get("old_method", version="1.0.0")
        with pytest.raises(RetiredMethodError):
            reg.get("old_method", version="2.0.0")

    def test_deprecated_method_warns_but_still_resolves(self) -> None:
        reg = MethodRegistry()
        fn = lambda x: x  # noqa: E731
        reg.register(_make_method("old_method"), fn)
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        reg.set_retirement(rec)

        with pytest.warns(DeprecatedMethodWarning, match="new_method"):
            spec, resolved = reg.get("old_method")
        assert resolved is fn
        assert spec.name == "old_method"

    def test_active_and_under_review_methods_resolve_silently(self) -> None:
        reg = MethodRegistry()
        reg.register(_make_method("m"), lambda x: x)

        # No record at all → silent.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            reg.get("m")

        # UNDER_REVIEW → still in service, still silent.
        rec = _under_review("m", "m2")
        reg.set_retirement(rec)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            spec, _ = reg.get("m")
        assert spec.name == "m"

    def test_retirement_state_helper(self) -> None:
        reg = MethodRegistry()
        reg.register(_make_method("m"), lambda x: x)
        assert reg.retirement_state("m") == RetirementState.ACTIVE
        rec = _under_review("m", "m2")
        reg.set_retirement(rec)
        assert reg.retirement_state("m") == RetirementState.UNDER_REVIEW


# ── Constraint 3: migration — sunset banners + scheduled reanalysis ───────


class TestMigration:
    def test_deprecating_flags_every_conclusion_with_a_banner(self) -> None:
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))

        conclusion_ids = ["c1", "c2", "c3"]
        plan = plan_migration(
            rec, conclusion_ids=conclusion_ids, as_of=_utc(2026, 1, 5)
        )
        assert isinstance(plan, MigrationPlan)
        # One sunset banner per conclusion the method produced.
        assert plan.conclusion_count == 3
        assert {b.conclusion_id for b in plan.banners} == set(conclusion_ids)
        for banner in plan.banners:
            assert banner.method == "old_method"
            assert banner.replacement == "new_method"
            assert banner.state == RetirementState.DEPRECATED
            assert "new_method" in banner.headline

    def test_migration_schedules_reanalysis_under_the_replacement(self) -> None:
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))

        plan = plan_migration(
            rec, conclusion_ids=["c1", "c2"], as_of=_utc(2026, 1, 5)
        )
        assert plan.schedules_reanalysis
        assert len(plan.reanalysis_tasks) == 2
        for task in plan.reanalysis_tasks:
            assert task.retired_method == "old_method"
            assert task.replacement_method == "new_method"
            assert task.scheduled_at == _utc(2026, 1, 5)

    def test_no_replacement_means_banners_but_no_reanalysis(self) -> None:
        """A method may be retired with no replacement — its conclusions
        still get a banner, but there is nothing to reanalyze them with."""
        rec = RetirementRecord(method="old_method")
        rec.open_review(
            replacement=None, rationale="all conclusions revised away",
            actor="founder", at=_utc(2026, 1, 1),
        )
        rec.accept(actor="founder", at=_utc(2026, 1, 5))

        plan = plan_migration(rec, conclusion_ids=["c1"], as_of=_utc(2026, 1, 5))
        assert plan.conclusion_count == 1
        assert not plan.schedules_reanalysis
        assert plan.reanalysis_tasks == ()

    def test_migration_refused_before_the_founder_accepts(self) -> None:
        """A method's conclusions are not flagged until the review is
        accepted — ACTIVE and UNDER_REVIEW cannot produce a plan."""
        active = RetirementRecord(method="m")
        with pytest.raises(RetirementTransitionError, match="DEPRECATED"):
            plan_migration(active, conclusion_ids=["c1"])

        under_review = _under_review("m", "m2")
        with pytest.raises(RetirementTransitionError, match="DEPRECATED"):
            plan_migration(under_review, conclusion_ids=["c1"])

    def test_retired_method_can_still_produce_a_migration_plan(self) -> None:
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        rec.retire(actor="founder", at=_utc(2026, 3, 1))
        plan = plan_migration(rec, conclusion_ids=["c1"], as_of=_utc(2026, 3, 1))
        assert plan.state == RetirementState.RETIRED
        assert plan.conclusion_count == 1


# ── Constraint 4: retirement criteria ─────────────────────────────────────


class TestCriteria:
    def test_sustained_drift_over_60_days_qualifies(self) -> None:
        as_of = _utc(2026, 5, 1)
        signals = RetirementSignals(
            drift_alert_active_since=as_of - timedelta(days=SUSTAINED_DRIFT_DAYS + 5)
        )
        verdict = qualifies_for_review(signals, method="m", as_of=as_of)
        assert verdict.qualifies
        assert RetirementCriterion.SUSTAINED_DRIFT in verdict.triggered

    def test_brief_drift_does_not_qualify(self) -> None:
        as_of = _utc(2026, 5, 1)
        signals = RetirementSignals(
            drift_alert_active_since=as_of - timedelta(days=10)
        )
        verdict = qualifies_for_review(signals, method="m", as_of=as_of)
        assert not verdict.qualifies

    def test_ablation_remove_qualifies(self) -> None:
        signals = RetirementSignals(ablation_recommendation="REMOVE")
        verdict = qualifies_for_review(signals, method="m")
        assert verdict.qualifies
        assert (
            RetirementCriterion.ZERO_ABLATION_CONTRIBUTION in verdict.triggered
        )

    def test_inconclusive_ablation_does_not_qualify(self) -> None:
        """The Householder-ablation rule: a zero-*power* ablation result
        (KEEP-WITH-FURTHER-WORK) is not grounds for retirement. Only a
        REMOVE recommendation counts."""
        for rec in ("KEEP", "KEEP-WITH-FURTHER-WORK", None):
            signals = RetirementSignals(ablation_recommendation=rec)
            verdict = qualifies_for_review(signals, method="contradiction_geometry")
            assert not verdict.qualifies, rec

    def test_dormancy_qualifies_only_on_explicit_zero(self) -> None:
        # Zero invocations in the window → qualifies.
        v_zero = qualifies_for_review(
            RetirementSignals(invocations_last_90d=0), method="m"
        )
        assert v_zero.qualifies
        assert RetirementCriterion.DORMANT in v_zero.triggered
        assert str(DORMANCY_DAYS) in v_zero.rationale[RetirementCriterion.DORMANT]

        # Unknown count (None) → does not qualify; a missing count is
        # never treated as zero.
        v_none = qualifies_for_review(
            RetirementSignals(invocations_last_90d=None), method="m"
        )
        assert not v_none.qualifies

        # Some invocations → does not qualify.
        v_some = qualifies_for_review(
            RetirementSignals(invocations_last_90d=4), method="m"
        )
        assert not v_some.qualifies

    def test_all_conclusions_revised_qualifies(self) -> None:
        v = qualifies_for_review(
            RetirementSignals(conclusions_total=12, conclusions_revised_away=12),
            method="m",
        )
        assert v.qualifies
        assert RetirementCriterion.ALL_CONCLUSIONS_REVISED in v.triggered

        # Partial revision does not qualify.
        v_partial = qualifies_for_review(
            RetirementSignals(conclusions_total=12, conclusions_revised_away=11),
            method="m",
        )
        assert not v_partial.qualifies

        # A method with zero conclusions does not trip this criterion.
        v_empty = qualifies_for_review(
            RetirementSignals(conclusions_total=0, conclusions_revised_away=0),
            method="m",
        )
        assert not v_empty.qualifies

    def test_multiple_criteria_can_fire_together(self) -> None:
        as_of = _utc(2026, 5, 1)
        signals = RetirementSignals(
            drift_alert_active_since=as_of - timedelta(days=120),
            ablation_recommendation="REMOVE",
            invocations_last_90d=0,
        )
        verdict = qualifies_for_review(signals, method="m", as_of=as_of)
        assert verdict.qualifies
        assert len(verdict.triggered) == 3
        # The rationale carries one line per fired criterion.
        assert set(verdict.rationale.keys()) == set(verdict.triggered)


# ── Memo rendering + round-trip ───────────────────────────────────────────


class TestMemo:
    def test_open_review_writes_a_memo(self, tmp_path) -> None:
        rec = _under_review("old_method", "new_method")
        path = write_memo(
            rec,
            rationale="ablation recommends REMOVE",
            conclusions_affected=["c1", "c2"],
            docs_dir=tmp_path,
        )
        assert path == memo_path("old_method", tmp_path)
        text = path.read_text(encoding="utf-8")
        # The body carries the human review document...
        assert "Retirement review" in text
        assert "old_method" in text
        assert "`c1`" in text and "`c2`" in text
        # ...and the frontmatter carries the machine-readable state.
        assert "state: under_review" in text

    def test_memo_frontmatter_round_trips(self, tmp_path) -> None:
        rec = _under_review("old_method", "new_method")
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        write_memo(rec, docs_dir=tmp_path)
        update_memo(rec, docs_dir=tmp_path)

        reloaded = parse_memo(memo_path("old_method", tmp_path))
        assert reloaded.method == "old_method"
        assert reloaded.state == RetirementState.DEPRECATED
        assert reloaded.replacement == "new_method"
        assert reloaded.review_opened_at == _utc(2026, 1, 1)
        assert reloaded.deprecated_at == _utc(2026, 1, 5)
        # The transition ledger survives the round-trip.
        assert [t.to_state for t in reloaded.transitions] == [
            RetirementState.UNDER_REVIEW,
            RetirementState.DEPRECATED,
        ]

    def test_write_memo_refuses_to_clobber(self, tmp_path) -> None:
        rec = _under_review("old_method", "new_method")
        write_memo(rec, docs_dir=tmp_path)
        with pytest.raises(FileExistsError):
            write_memo(rec, docs_dir=tmp_path)

    def test_update_memo_preserves_human_body(self, tmp_path) -> None:
        rec = _under_review("old_method", "new_method")
        path = write_memo(rec, docs_dir=tmp_path)
        # A reviewer edits the body.
        text = path.read_text(encoding="utf-8")
        edited = text + "\n\n## Reviewer note\n\nHand-written content.\n"
        path.write_text(edited, encoding="utf-8")
        # A transition rewrites only the frontmatter.
        rec.accept(actor="founder", at=_utc(2026, 1, 5))
        update_memo(rec, docs_dir=tmp_path)
        after = path.read_text(encoding="utf-8")
        assert "Hand-written content." in after
        assert "state: deprecated" in after

    def test_load_retirement_records_scans_the_dir(self, tmp_path) -> None:
        write_memo(_under_review("a", "a2"), docs_dir=tmp_path)
        write_memo(_under_review("b", "b2"), docs_dir=tmp_path)
        records = load_retirement_records(tmp_path)
        assert set(records) == {"a", "b"}
        assert records["a"].state == RetirementState.UNDER_REVIEW

    def test_render_memo_substitutes_placeholders(self) -> None:
        rec = _under_review("old_method", "new_method")
        rendered = render_memo(rec, rationale="dormant: zero invocations")
        # No unresolved placeholders left in the body.
        assert "{{" not in rendered
        assert "dormant: zero invocations" in rendered
        assert "new_method" in rendered
