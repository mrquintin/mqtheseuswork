"""Replication studies corpus adapter."""

from __future__ import annotations

import csv
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

_DEFAULT_SNAPSHOT_DIR = Path.home() / ".theseus" / "external_snapshots" / "replication"


class ReplicationAdapter:
    """Adapter for replication studies corpus."""

    name = "replication"
    license = LicenseTag.REPLICATION_PUBLIC

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR

    def fetch(self, cache_dir: Path) -> CorpusBundle:
        if not self._snapshot_dir.exists():
            raise SnapshotMissingError(
                f"Snapshot not found at {self._snapshot_dir}. "
                "Request a snapshot from https://replicationmarkets.com/"
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
            yield ExternalItem(
                source=self.name,
                source_id=rec["study_id"],
                question_text=f"Replication of {rec['study_id']} (original d={rec['original_effect']})",
                as_of=_parse_date(rec["replication_date"]),
                resolved_at=_parse_date(rec["replication_date"]),
                outcome_type=OutcomeKind.INTERVAL,
                metadata={
                    "original_effect": float(rec["original_effect"]),
                    "replication_source": rec["replication_source"],
                },
            )

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]:
        for rec in self._load(bundle):
            if rec["study_id"] != item.source_id:
                continue
            return Outcome(
                outcome_id=f"replication:{item.source_id}",
                kind=OutcomeKind.INTERVAL,
                event_ref=f"replication:{item.source_id}",
                resolution_source=rec["replication_source"],
                resolved_at=_parse_date(rec["replication_date"]),
                value=float(rec["replication_effect"]),
            )
        return None

    def _load(self, bundle: CorpusBundle) -> list[dict]:
        base = Path(bundle.local_path)
        csv_path = base / "snapshot.csv"
        json_path = base / "snapshot.json"
        if csv_path.exists():
            with open(csv_path, newline="") as f:
                return list(csv.DictReader(f))
        if json_path.exists():
            with open(json_path) as f:
                return json.load(f)
        raise SnapshotMissingError(
            f"No snapshot file found in {base}. Expected snapshot.csv or snapshot.json."
        )


def _parse_date(s: str) -> datetime:
    if "T" in s:
        return datetime.fromisoformat(s)
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
