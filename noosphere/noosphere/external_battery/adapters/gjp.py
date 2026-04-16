"""Good Judgment Project corpus adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from noosphere.external_battery.adapters import SnapshotMissingError, _compute_snapshot_hash
from noosphere.models import (
    CorpusBundle,
    ExternalItem,
    LicenseTag,
    Outcome,
    OutcomeKind,
)

_DEFAULT_SNAPSHOT_DIR = Path.home() / ".theseus" / "external_snapshots" / "gjp"


class GJPAdapter:
    """Adapter for Good Judgment Project public forecasting data."""

    name = "gjp"
    license = LicenseTag.GJP_PUBLIC

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR

    def fetch(self, cache_dir: Path) -> CorpusBundle:
        if not self._snapshot_dir.exists():
            raise SnapshotMissingError(
                f"Snapshot not found at {self._snapshot_dir}. "
                "Request a snapshot from https://goodjudgment.com/resources/"
            )
        return CorpusBundle(
            source=self.name,
            content_hash=_compute_snapshot_hash(self._snapshot_dir),
            local_path=str(self._snapshot_dir),
            license=self.license,
            fetched_at=datetime.now(timezone.utc),
        )

    def iter_items(self, bundle: CorpusBundle) -> Iterator[ExternalItem]:
        for rec in self._load(bundle):
            outcome_raw = rec["outcome"]
            otype = OutcomeKind.BINARY if outcome_raw in ("yes", "no") else OutcomeKind.INTERVAL
            yield ExternalItem(
                source=self.name,
                source_id=rec["question_id"],
                question_text=rec["question_text"],
                as_of=datetime.fromisoformat(rec["opened_at"]),
                resolved_at=datetime.fromisoformat(rec["closed_at"]),
                outcome_type=otype,
                metadata={
                    "gjp_baseline": rec.get("gjp_baseline"),
                    "superforecaster_baseline": rec.get("superforecaster_baseline"),
                },
            )

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]:
        for rec in self._load(bundle):
            if rec["question_id"] != item.source_id:
                continue
            outcome_raw = rec["outcome"]
            if outcome_raw in ("yes", "no"):
                kind = OutcomeKind.BINARY
                value: object = outcome_raw == "yes"
            else:
                kind = OutcomeKind.INTERVAL
                value = float(outcome_raw)
            return Outcome(
                outcome_id=f"gjp:{item.source_id}",
                kind=kind,
                event_ref=f"gjp:{item.source_id}",
                resolution_source="Good Judgment Project",
                resolved_at=datetime.fromisoformat(rec["closed_at"]),
                value=value,
            )
        return None

    def _load(self, bundle: CorpusBundle) -> list[dict]:
        path = Path(bundle.local_path) / "snapshot.json"
        with open(path) as f:
            return json.load(f)
