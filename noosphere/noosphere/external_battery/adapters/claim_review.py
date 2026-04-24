"""ClaimReview fact-check corpus adapter."""

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

_DEFAULT_SNAPSHOT_DIR = Path.home() / ".theseus" / "external_snapshots" / "claim_review"


class ClaimReviewAdapter:
    """Adapter for ClaimReview schema fact-check corpus."""

    name = "claim_review"
    license = LicenseTag.CLAIM_REVIEW

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR

    def fetch(self, cache_dir: Path) -> CorpusBundle:
        if not self._snapshot_dir.exists():
            raise SnapshotMissingError(
                f"Snapshot not found at {self._snapshot_dir}. "
                "Request a snapshot from https://schema.org/ClaimReview"
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
                source_id=rec["claim_id"],
                question_text=rec["claim_text"],
                as_of=datetime.fromisoformat(rec["review_date"]),
                resolved_at=datetime.fromisoformat(rec["review_date"]),
                outcome_type=OutcomeKind.BINARY,
                metadata={
                    "fact_checker": rec["fact_checker"],
                    "rating": rec["rating"],
                    "url": rec.get("url"),
                },
            )

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]:
        for rec in self._load(bundle):
            if rec["claim_id"] != item.source_id:
                continue
            value = rec["rating"].lower() == "true"
            return Outcome(
                outcome_id=f"claim_review:{item.source_id}",
                kind=OutcomeKind.BINARY,
                event_ref=f"claim_review:{item.source_id}",
                resolution_source=rec["fact_checker"],
                resolved_at=datetime.fromisoformat(rec["review_date"]),
                value=value,
            )
        return None

    def _load(self, bundle: CorpusBundle) -> list[dict]:
        base = Path(bundle.local_path)
        jsonl_path = base / "snapshot.jsonl"
        json_path = base / "snapshot.json"
        if jsonl_path.exists():
            records: list[dict] = []
            with open(jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records
        if json_path.exists():
            with open(json_path) as f:
                return json.load(f)
        raise SnapshotMissingError(
            f"No snapshot file found in {base}. Expected snapshot.jsonl or snapshot.json."
        )
