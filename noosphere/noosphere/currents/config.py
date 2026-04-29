"""Configuration for Currents ingestors."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    rows = csv.reader([value], skipinitialspace=True)
    return [item.strip() for item in next(rows, []) if item.strip()]


@dataclass(frozen=True)
class IngestorConfig:
    bearer_token: str
    curated_accounts: list[str]
    search_queries: list[str]
    organization_id: str
    max_events_per_cycle: int = 40
    base_url: str = "https://api.x.com/2"
    request_timeout_s: float = 15.0

    @classmethod
    def from_env(cls) -> IngestorConfig:
        max_events_raw = os.getenv("CURRENTS_MAX_EVENTS_PER_CYCLE", "").strip()
        max_events = int(max_events_raw) if max_events_raw else 40
        timeout_raw = os.getenv("CURRENTS_X_REQUEST_TIMEOUT_S", "").strip()
        timeout = float(timeout_raw) if timeout_raw else 15.0
        return cls(
            bearer_token=os.getenv("X_BEARER_TOKEN", "").strip(),
            curated_accounts=_parse_csv_env(os.getenv("CURRENTS_X_CURATED_ACCOUNTS")),
            search_queries=_parse_csv_env(os.getenv("CURRENTS_X_SEARCH_QUERIES")),
            organization_id=os.getenv("CURRENTS_INGEST_ORG_ID", "").strip(),
            max_events_per_cycle=max_events,
            base_url=os.getenv("CURRENTS_X_BASE_URL", "https://api.x.com/2").rstrip("/"),
            request_timeout_s=timeout,
        )

