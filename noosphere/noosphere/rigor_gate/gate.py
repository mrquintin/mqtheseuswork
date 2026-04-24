"""Gate: run all registered checks, aggregate, record to ledger and store."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from noosphere.models import (
    Actor,
    CheckResult,
    ContextMeta,
    RigorSubmission,
    RigorVerdict,
)
from noosphere.rigor_gate.checks import all_checks

if TYPE_CHECKING:
    from noosphere.ledger import Ledger


class GateBlocked(Exception):
    """Raised when a submission fails the rigor gate."""

    def __init__(self, verdict: RigorVerdict) -> None:
        self.verdict = verdict
        super().__init__(f"Gate blocked: {verdict.verdict}")


class Gate:
    def __init__(self, store: object, ledger: "Ledger | None" = None) -> None:
        self.store = store
        self._ledger = ledger

    def submit(self, submission: RigorSubmission) -> RigorVerdict:
        checks = all_checks()
        results = self._run_checks(checks, submission)
        verdict_str, conditions = self._aggregate(results)
        entry_id = self._record_ledger(submission, verdict_str)

        verdict = RigorVerdict(
            verdict=verdict_str,
            checks_run=results,
            conditions=conditions,
            reviewed_by=[submission.author],
            ledger_entry_id=entry_id,
        )

        self.store.insert_rigor_submission(submission)  # type: ignore[union-attr]
        self.store.insert_rigor_verdict(verdict)  # type: ignore[union-attr]
        return verdict

    # ------------------------------------------------------------------

    @staticmethod
    def _run_checks(
        checks: dict[str, object],
        submission: RigorSubmission,
    ) -> list[CheckResult]:
        if not checks:
            return []
        results: list[CheckResult] = []
        with ThreadPoolExecutor() as pool:
            futures = {
                pool.submit(fn, submission): name  # type: ignore[arg-type]
                for name, fn in checks.items()
            }
            for fut in as_completed(futures):
                results.append(fut.result())
        return results

    @staticmethod
    def _aggregate(
        results: list[CheckResult],
    ) -> tuple[str, list[str]]:
        conditions: list[str] = []
        has_blocker = False
        for r in results:
            if not r.pass_:
                has_blocker = True
            elif r.detail.startswith("CONDITION:"):
                conditions.append(r.detail[len("CONDITION:") :].strip())
        if has_blocker:
            return "fail", []
        if conditions:
            return "pass_with_conditions", conditions
        return "pass", []

    def _record_ledger(self, submission: RigorSubmission, verdict_str: str) -> str:
        if self._ledger is None:
            return f"rigor-{submission.submission_id}"

        return self._ledger.append(
            actor=submission.author,
            method_id=None,
            inputs_hash=hashlib.sha256(
                submission.model_dump_json().encode()
            ).hexdigest(),
            outputs_hash=hashlib.sha256(verdict_str.encode()).hexdigest(),
            inputs_ref=f"rigor_submission:{submission.submission_id}",
            outputs_ref=f"rigor_verdict:{verdict_str}",
            context=ContextMeta(
                tenant_id="rigor_gate",
                correlation_id=submission.submission_id,
            ),
        )
