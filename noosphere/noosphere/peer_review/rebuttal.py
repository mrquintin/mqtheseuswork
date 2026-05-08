from __future__ import annotations

from noosphere.models import Finding, Rebuttal, SwarmReport
from noosphere.store import Store


def _finding_severity_label(finding: Finding) -> str | None:
    """Read the severity-rubric label off a Finding, if present.

    Findings emitted by the multi-provider swarm carry an
    ``severity=<label>:<value>`` token in ``evidence`` (see
    :mod:`noosphere.peer_review.severity`). Returns the label if the
    token is present, else ``None`` so callers can fall back to the
    coarser :attr:`Finding.severity` field.
    """

    for ev in finding.evidence or []:
        if ev.startswith("severity=") and ":" in ev:
            label = ev.split("=", 1)[1].split(":", 1)[0].strip()
            if label in {"low", "medium", "high"}:
                return label
    return None


class RebuttalRegistry:
    def __init__(self, store: Store) -> None:
        self._store = store

    def required_rebuttals(self, swarm_report: SwarmReport) -> list[Finding]:
        """Findings the firm must respond to before publishing.

        Severity {high} (blocker) findings are required; severity
        {medium} (major) are encouraged. {low} are optional and not
        listed here.
        """

        out: list[Finding] = []
        for report in swarm_report.reviews:
            for finding in report.findings:
                if finding.severity in ("major", "blocker"):
                    out.append(finding)
        return out

    def response_required(self, finding: Finding) -> bool:
        """True iff publication is gated on a response to this finding.

        High-severity (blocker) objections always require a response;
        the existing ``advance_to_publication`` enforces it.
        """

        if finding.severity == "blocker":
            return True
        label = _finding_severity_label(finding)
        return label == "high"

    def response_encouraged(self, finding: Finding) -> bool:
        """True for medium-severity findings.

        Not gating; surfaced so the UI can prompt the reviewer to
        respond without blocking publication.
        """

        if finding.severity == "major":
            return True
        label = _finding_severity_label(finding)
        return label == "medium"

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
