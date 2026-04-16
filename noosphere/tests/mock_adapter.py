"""Mock adapter for external-battery tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from noosphere.models import (
    CorpusBundle,
    ExternalItem,
    LicenseTag,
    Outcome,
    OutcomeKind,
)


class MockAdapter:
    """Minimal adapter satisfying the CorpusAdapter protocol for tests."""

    name = "mock"
    license = LicenseTag.CUSTOM

    def fetch(self, cache_dir: Path) -> CorpusBundle:
        return CorpusBundle(
            source="mock",
            content_hash="abc123",
            local_path=str(cache_dir / "mock"),
            license=LicenseTag.CUSTOM,
            fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    def iter_items(self, bundle: CorpusBundle) -> Iterator[ExternalItem]:
        yield ExternalItem(
            source="mock",
            source_id="q1",
            question_text="Will it rain tomorrow?",
            as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
            resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            outcome_type=OutcomeKind.BINARY,
            metadata={"domain": "weather"},
        )
        yield ExternalItem(
            source="mock",
            source_id="q2",
            question_text="What will the temperature be?",
            as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
            resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            outcome_type=OutcomeKind.INTERVAL,
            metadata={"domain": "weather", "unit": "celsius"},
        )
        yield ExternalItem(
            source="mock",
            source_id="q3",
            question_text="Which team will win?",
            as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
            resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            outcome_type=OutcomeKind.PREFERENCE,
            metadata={"domain": "sports"},
        )

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]:
        resolutions = {
            "q1": Outcome(
                outcome_id="r1",
                kind=OutcomeKind.BINARY,
                event_ref="mock:q1",
                resolution_source="mock_ground_truth",
                resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                value=True,
            ),
            "q2": Outcome(
                outcome_id="r2",
                kind=OutcomeKind.INTERVAL,
                event_ref="mock:q2",
                resolution_source="mock_ground_truth",
                resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                value=22.5,
            ),
            "q3": Outcome(
                outcome_id="r3",
                kind=OutcomeKind.PREFERENCE,
                event_ref="mock:q3",
                resolution_source="mock_ground_truth",
                resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                value="team_a",
            ),
        }
        return resolutions.get(item.source_id)
