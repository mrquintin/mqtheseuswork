from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class _Outcome:
    predicted_severity: str
    was_confirmed: bool


class ReviewerCalibration:
    def __init__(self) -> None:
        self._history: dict[str, list[_Outcome]] = {}

    def track_outcome(
        self,
        reviewer_name: str,
        finding_severity: str,
        subsequent_outcome: str,
    ) -> None:
        confirmed = subsequent_outcome == "confirmed"
        entry = _Outcome(
            predicted_severity=finding_severity,
            was_confirmed=confirmed,
        )
        self._history.setdefault(reviewer_name, []).append(entry)

    def discount_factor(self, reviewer_name: str) -> float:
        outcomes = self._history.get(reviewer_name)
        if not outcomes:
            return 1.0
        confirmed = sum(1 for o in outcomes if o.was_confirmed)
        total = len(outcomes)
        accuracy = confirmed / total
        return max(0.1, accuracy)
