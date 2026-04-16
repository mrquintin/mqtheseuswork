"""Metaculus corpus adapter."""

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

_DEFAULT_SNAPSHOT_DIR = Path.home() / ".theseus" / "external_snapshots" / "metaculus"


class MetaculusAdapter:
    """Adapter for Metaculus resolved community forecasts."""

    name = "metaculus"
    license = LicenseTag.METACULUS_PUBLIC

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR

    def fetch(self, cache_dir: Path) -> CorpusBundle:
        if not self._snapshot_dir.exists():
            raise SnapshotMissingError(
                f"Snapshot not found at {self._snapshot_dir}. "
                "Request a snapshot from https://www.metaculus.com/api/"
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
            if rec.get("status") != "resolved":
                continue
            qtype = rec.get("type", "binary")
            otype = OutcomeKind.BINARY if qtype == "binary" else OutcomeKind.INTERVAL
            yield ExternalItem(
                source=self.name,
                source_id=str(rec["id"]),
                question_text=rec["title"],
                as_of=datetime.fromisoformat(rec["created_time"]),
                resolved_at=datetime.fromisoformat(rec["resolve_time"]),
                outcome_type=otype,
                metadata={
                    "community_prediction": rec.get("community_prediction"),
                    "metaculus_type": qtype,
                },
            )

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]:
        for rec in self._load(bundle):
            if str(rec["id"]) != item.source_id:
                continue
            if rec.get("status") != "resolved" or rec.get("resolution") is None:
                return None
            qtype = rec.get("type", "binary")
            if qtype == "binary":
                kind = OutcomeKind.BINARY
                value: object = rec["resolution"] >= 0.5
            else:
                kind = OutcomeKind.INTERVAL
                value = float(rec["resolution"])
            return Outcome(
                outcome_id=f"metaculus:{item.source_id}",
                kind=kind,
                event_ref=f"metaculus:{item.source_id}",
                resolution_source="Metaculus public resolution",
                resolved_at=datetime.fromisoformat(rec["resolve_time"]),
                value=value,
            )
        return None

    def _load(self, bundle: CorpusBundle) -> list[dict]:
        path = Path(bundle.local_path) / "snapshot.json"
        with open(path) as f:
            return json.load(f)
