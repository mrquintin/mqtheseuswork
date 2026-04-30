"""Configuration for Forecasts ingestors."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    rows = csv.reader([value], skipinitialspace=True)
    return [item.strip() for item in next(rows, []) if item.strip()]


def _parse_int_env(value: str | None, default: int) -> int:
    if not value or not value.strip():
        return default
    return int(value.strip())


@dataclass(frozen=True)
class PolymarketConfig:
    gamma_base: str = "https://gamma-api.polymarket.com"
    accepted_categories: list[str] = field(default_factory=list)
    organization_id: str = ""
    max_markets_per_cycle: int = 200
    request_timeout_s: float = 15.0

    @classmethod
    def from_env(cls) -> "PolymarketConfig":
        return cls(
            gamma_base=os.getenv(
                "POLYMARKET_GAMMA_BASE",
                "https://gamma-api.polymarket.com",
            ).rstrip("/"),
            accepted_categories=_parse_csv_env(
                os.getenv("FORECASTS_POLYMARKET_CATEGORIES")
            ),
            organization_id=os.getenv("FORECASTS_INGEST_ORG_ID", "").strip(),
            max_markets_per_cycle=_parse_int_env(
                os.getenv("FORECASTS_POLYMARKET_MAX_PER_CYCLE"),
                200,
            ),
        )


@dataclass(frozen=True)
class KalshiConfig:
    api_base: str = "https://api.elections.kalshi.com/trade-api/v2"
    api_key_id: str = ""
    api_private_key_pem: str = ""
    accepted_categories: list[str] = field(default_factory=list)
    organization_id: str = ""
    max_markets_per_cycle: int = 200
    request_timeout_s: float = 15.0

    @classmethod
    def from_env(cls) -> "KalshiConfig":
        """Build config from env.

        KALSHI_API_PRIVATE_KEY is the full PEM blob. For one-line env files,
        store embedded newlines as literal "\n" escapes.
        """

        # KALSHI_API_PRIVATE_KEY may be exported as one line with literal
        # "\n" escapes; convert those back to PEM line breaks before parsing.
        raw_private_key = os.getenv("KALSHI_API_PRIVATE_KEY", "")
        return cls(
            api_base=os.getenv(
                "KALSHI_API_BASE",
                "https://api.elections.kalshi.com/trade-api/v2",
            ).rstrip("/"),
            api_key_id=os.getenv("KALSHI_API_KEY_ID", "").strip(),
            api_private_key_pem=raw_private_key.replace("\\n", "\n").strip(),
            accepted_categories=_parse_csv_env(
                os.getenv("FORECASTS_KALSHI_CATEGORIES")
            ),
            organization_id=os.getenv("FORECASTS_INGEST_ORG_ID", "").strip(),
            max_markets_per_cycle=_parse_int_env(
                os.getenv("FORECASTS_KALSHI_MAX_PER_CYCLE"),
                200,
            ),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key_id and self.api_private_key_pem)
