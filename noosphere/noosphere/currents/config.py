"""Configuration for Currents ingestors."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from noosphere.currents._x_client import DISCOVERY_QUERY


# The default floor is calibrated to prompt 02's log-weighted score: it clears a
# post with roughly one default viral-search signal, such as 1,000 likes or 100
# retweets, while rejecting low-engagement keyword matches. Impressions carry a
# larger 0.4 weight, so genuinely broad reach clears the floor decisively even
# when likes lag; deployments can raise/lower this score or use the raw-count
# floors below when an X API tier withholds impressions or local calibration
# shows a different engagement baseline.
DEFAULT_MIN_SIGNIFICANCE_SCORE = 1.35


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    rows = csv.reader([value], skipinitialspace=True)
    return [item.strip() for item in next(rows, []) if item.strip()]


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float_env(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class IngestorConfig:
    bearer_token: str
    curated_accounts: list[str]
    search_queries: list[str]
    organization_id: str
    max_events_per_cycle: int = 40
    discovery_enabled: bool = True
    discovery_max_candidates: int = 100
    discovery_query: str = DISCOVERY_QUERY
    discovery_locale: str = "en"
    min_significance_score: float = DEFAULT_MIN_SIGNIFICANCE_SCORE
    min_likes: int = 1_000
    min_retweets: int = 100
    min_impressions: int = 25_000
    base_url: str = "https://api.x.com/2"
    request_timeout_s: float = 15.0
    x_ingestion_disabled: bool = False

    @property
    def disabled_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.x_ingestion_disabled:
            reasons.append("manual_kill_switch")
        if not self.bearer_token:
            reasons.append("missing_x_bearer_token")
        discovery_available = self.discovery_enabled and self.discovery_max_candidates > 0
        if (
            not discovery_available
            and not self.curated_accounts
            and not self.search_queries
        ):
            reasons.append("missing_x_sources")
        return reasons

    @property
    def ingestion_enabled(self) -> bool:
        return not self.disabled_reasons

    @classmethod
    def from_env(cls) -> IngestorConfig:
        max_events = _parse_int_env(
            os.getenv("CURRENTS_MAX_EVENTS_PER_CYCLE"),
            default=40,
        )
        timeout = _parse_float_env(
            os.getenv("CURRENTS_X_REQUEST_TIMEOUT_S"),
            default=15.0,
        )
        return cls(
            bearer_token=os.getenv("X_BEARER_TOKEN", "").strip(),
            curated_accounts=_parse_csv_env(os.getenv("CURRENTS_X_CURATED_ACCOUNTS")),
            search_queries=_parse_csv_env(os.getenv("CURRENTS_X_SEARCH_QUERIES")),
            organization_id=os.getenv("CURRENTS_INGEST_ORG_ID", "").strip(),
            max_events_per_cycle=max_events,
            discovery_enabled=_parse_bool_env(
                os.getenv("CURRENTS_X_DISCOVERY_ENABLED"),
                default=True,
            ),
            discovery_max_candidates=_parse_int_env(
                os.getenv("CURRENTS_X_DISCOVERY_MAX_CANDIDATES"),
                default=100,
            ),
            discovery_query=(
                os.getenv("CURRENTS_X_DISCOVERY_QUERY", "").strip()
                or DISCOVERY_QUERY
            ),
            discovery_locale=(
                os.getenv("CURRENTS_X_DISCOVERY_LOCALE", "").strip() or "en"
            ),
            min_significance_score=_parse_float_env(
                os.getenv("CURRENTS_MIN_SIGNIFICANCE_SCORE"),
                default=DEFAULT_MIN_SIGNIFICANCE_SCORE,
            ),
            min_likes=_parse_int_env(
                os.getenv("CURRENTS_X_MIN_LIKES"),
                default=1_000,
            ),
            min_retweets=_parse_int_env(
                os.getenv("CURRENTS_X_MIN_RETWEETS"),
                default=100,
            ),
            min_impressions=_parse_int_env(
                os.getenv("CURRENTS_X_MIN_IMPRESSIONS"),
                default=25_000,
            ),
            base_url=os.getenv("CURRENTS_X_BASE_URL", "https://api.x.com/2").rstrip("/"),
            request_timeout_s=timeout,
            x_ingestion_disabled=_parse_bool_env(
                os.getenv("CURRENTS_X_INGESTION_DISABLED"),
                default=False,
            ),
        )
