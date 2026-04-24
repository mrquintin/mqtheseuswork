from __future__ import annotations

from noosphere.models import Finding, Rebuttal, SwarmReport
from noosphere.store import Store


class RebuttalRegistry:
    def __init__(self, store: Store) -> None:
        self._store = store

    def required_rebuttals(self, swarm_report: SwarmReport) -> list[Finding]:
        out: list[Finding] = []
        for report in swarm_report.reviews:
            for finding in report.findings:
                if finding.severity in ("major", "blocker"):
                    out.append(finding)
        return out

    def submit_rebuttal(
        self, finding_id: str, rebuttal: Rebuttal, *, report_id: str
    ) -> None:
        if (
            rebuttal.form == "reject_with_reason"
            and rebuttal.by_actor.kind != "human"
        ):
            raise PermissionError(
                "reject_with_reason requires a human actor"
            )
        self._store.insert_rebuttal(rebuttal, report_id=report_id)

    def advance_to_publication(self, conclusion_id: str) -> None:
        reports = self._store.list_review_reports(conclusion_id)
        unresolved = self._unresolved_blockers(conclusion_id, reports)
        if unresolved:
            raise BlockedPublicationError(
                f"{len(unresolved)} unresolved major/blocker finding(s) "
                f"block publication of {conclusion_id}"
            )

    def _unresolved_blockers(
        self, conclusion_id: str, reports: list
    ) -> list[Finding]:
        unresolved: list[Finding] = []
        for report in reports:
            rebutted_ids = {
                r.finding_id
                for r in self._store.list_rebuttals(report.report_id)
            }
            for idx, finding in enumerate(report.findings):
                if finding.severity in ("major", "blocker"):
                    fid = f"{report.report_id}:{idx}"
                    if fid not in rebutted_ids:
                        unresolved.append(finding)
        return unresolved


class BlockedPublicationError(Exception):
    pass
