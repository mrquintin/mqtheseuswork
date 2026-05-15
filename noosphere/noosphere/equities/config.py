"""Configuration for the Alpaca broker integration."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    rows = csv.reader([value], skipinitialspace=True)
    return [item.strip() for item in next(rows, []) if item.strip()]


def _parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    raw = value.strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _parse_float_env(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    return float(value.strip())


@dataclass(frozen=True)
class AlpacaConfig:
    """Connection + behaviour parameters for the Alpaca broker.

    Paper-trading is the default; live trading is gated by the eight-gate
    safety contract in a subsequent prompt and toggled via ALPACA_IS_PAPER.
    """

    api_base: str = "https://paper-api.alpaca.markets"
    data_base: str = "https://data.alpaca.markets"
    api_key_id: str = ""
    api_secret_key: str = ""
    organization_id: str = ""
    is_paper: bool = True
    request_timeout_s: float = 15.0
    accepted_symbols: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "AlpacaConfig":
        return cls(
            api_base=os.getenv(
                "ALPACA_API_BASE",
                "https://paper-api.alpaca.markets",
            ).rstrip("/"),
            data_base=os.getenv(
                "ALPACA_DATA_BASE",
                "https://data.alpaca.markets",
            ).rstrip("/"),
            api_key_id=os.getenv("ALPACA_API_KEY_ID", "").strip(),
            api_secret_key=os.getenv("ALPACA_API_SECRET_KEY", "").strip(),
            organization_id=os.getenv("FORECASTS_INGEST_ORG_ID", "").strip(),
            is_paper=_parse_bool_env(os.getenv("ALPACA_IS_PAPER"), True),
            request_timeout_s=_parse_float_env(
                os.getenv("ALPACA_REQUEST_TIMEOUT_S"),
                15.0,
            ),
            accepted_symbols=_parse_csv_env(os.getenv("EQUITIES_ACCEPTED_SYMBOLS")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key_id and self.api_secret_key)


# Default pinned version of the unofficial robin_stocks library used by the
# Robinhood adapter. Robinhood periodically breaks compatibility with the
# upstream app, so the operator may pin a different known-good release.
ROBINHOOD_DEFAULT_PIP_CHOICE = "robin_stocks==3.4.0"


@dataclass(frozen=True)
class RobinhoodConfig:
    """Credentials for the unofficial Robinhood adapter.

    Robinhood does not publish a supported retail trading API; this adapter
    relies on the reverse-engineered ``robin_stocks`` library. It is OFF by
    default and is gated behind both ``ROBINHOOD_ENABLED`` and the eight-gate
    safety contract in :mod:`noosphere.forecasts.safety`.
    """

    username: str = ""
    password: str = ""
    mfa_seed: str = ""
    device_token: str = ""
    organization_id: str = ""
    request_timeout_s: float = 20.0
    pip_choice: str = ROBINHOOD_DEFAULT_PIP_CHOICE

    @classmethod
    def from_env(cls) -> "RobinhoodConfig":
        return cls(
            username=os.getenv("ROBINHOOD_USERNAME", "").strip(),
            password=os.getenv("ROBINHOOD_PASSWORD", "").strip(),
            mfa_seed=os.getenv("ROBINHOOD_MFA_SEED", "").strip(),
            device_token=os.getenv("ROBINHOOD_DEVICE_TOKEN", "").strip(),
            organization_id=os.getenv("FORECASTS_INGEST_ORG_ID", "").strip(),
            request_timeout_s=_parse_float_env(
                os.getenv("ROBINHOOD_REQUEST_TIMEOUT_S"),
                20.0,
            ),
            pip_choice=(
                os.getenv("ROBINHOOD_PIP_CHOICE", "").strip()
                or ROBINHOOD_DEFAULT_PIP_CHOICE
            ),
        )

    @property
    def is_configured(self) -> bool:
        return all(
            (
                self.username,
                self.password,
                self.mfa_seed,
                self.device_token,
                self.organization_id,
                self.request_timeout_s > 0,
                self.pip_choice,
            )
        )
