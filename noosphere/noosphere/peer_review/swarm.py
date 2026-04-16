from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from noosphere.models import Conclusion, ReviewReport, SwarmReport
from noosphere.peer_review.reviewer import Reviewer
from noosphere.peer_review.reviewers import all_reviewers
from noosphere.store import Store

logger = logging.getLogger(__name__)


class SwarmOrchestrator:
    def __init__(self, store: Store) -> None:
        self._store = store

    def run(
        self,
        conclusion_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> SwarmReport:
        conclusion = self._store.get_conclusion(conclusion_id)
        if conclusion is None:
            raise ValueError(f"Conclusion {conclusion_id} not found")

        reviewers: list[Reviewer] = [cls() for cls in all_reviewers()]
        ctx = context or {}
        reports = self._run_reviews(reviewers, conclusion, ctx)

        for report in reports:
            self._store.insert_review_report(report)

        return SwarmReport(
            conclusion_id=conclusion_id,
            reviews=reports,
            rebuttals=[],
        )

    def _run_reviews(
        self,
        reviewers: list[Reviewer],
        conclusion: Conclusion,
        context: dict[str, Any],
    ) -> list[ReviewReport]:
        reports: list[ReviewReport] = []
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(r.review, conclusion, context): r
                for r in reviewers
            }
            for future in as_completed(futures):
                reviewer = futures[future]
                try:
                    reports.append(future.result())
                except Exception:
                    logger.exception("Reviewer %s failed", reviewer.name)
        return reports
