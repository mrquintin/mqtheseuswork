"""Data accessors for the public refusal dashboard (UI is wave_9)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session, select

from noosphere.models import FounderOverride, RigorVerdict
from noosphere.store import StoredFounderOverride, StoredRigorVerdict


@dataclass(frozen=True)
class DashboardData:
    year_month: str
    total: int
    passed: int
    failed: int
    pass_with_conditions: int
    top_failure_categories: dict[str, int] = field(default_factory=dict)


def _list_verdicts(store: object) -> list[RigorVerdict]:
    with store.session() as s:  # type: ignore[union-attr]
        rows = s.exec(select(StoredRigorVerdict)).all()
        return [RigorVerdict.model_validate_json(r.payload_json) for r in rows]


def _list_overrides(store: object) -> list[FounderOverride]:
    with store.session() as s:  # type: ignore[union-attr]
        rows = s.exec(select(StoredFounderOverride)).all()
        return [FounderOverride.model_validate_json(r.payload_json) for r in rows]


def monthly_stats(store: object, year_month: str) -> DashboardData:
    verdicts = _list_verdicts(store)

    # Filter by year_month using the ledger_entry_id's linked ledger entry
    # timestamp. When no ledger is configured, entry IDs are prefixed with
    # "rigor-", so we include all verdicts (the caller can filter further).
    # With a real ledger we'd join on ledger entries for the timestamp.
    # For now, include all verdicts — monthly filtering refines in wave_9 UI.
    passed = sum(1 for v in verdicts if v.verdict == "pass")
    failed = sum(1 for v in verdicts if v.verdict == "fail")
    pwc = sum(1 for v in verdicts if v.verdict == "pass_with_conditions")

    failure_categories: Counter[str] = Counter()
    for v in verdicts:
        if v.verdict == "fail":
            for cr in v.checks_run:
                if not cr.pass_:
                    failure_categories[cr.check_name] += 1

    return DashboardData(
        year_month=year_month,
        total=len(verdicts),
        passed=passed,
        failed=failed,
        pass_with_conditions=pwc,
        top_failure_categories=dict(failure_categories.most_common(10)),
    )


def overrides_for_display(store: object) -> list[FounderOverride]:
    return _list_overrides(store)
