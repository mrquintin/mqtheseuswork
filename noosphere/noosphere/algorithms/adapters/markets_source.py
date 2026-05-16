"""Markets source adapter for the algorithm runtime.

Resolves observability sources of the form
``markets.<venue>.<external_id>.<field>``. Supported venues:

* ``polymarket`` — reads ``ForecastMarket`` rows where
  ``source == ForecastSource.POLYMARKET`` and ``external_id`` matches.
* ``kalshi`` — same shape, ``ForecastSource.KALSHI``.
* ``alpaca`` — reads ``EquityInstrument`` (and the most-recent
  ``EquityPriceTick``) where ``symbol`` matches.

The adapter is read-only and never blocks the calling tick on a network
roundtrip: every lookup hits the local DB the ingestor populates. If the
row is missing or the field is unset, the adapter returns ``None`` and
the runtime treats the input as unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlmodel import desc, select

from noosphere.algorithms.adapters import InputObservation


_VENUE_PREFIXES = ("polymarket", "kalshi", "alpaca")


@dataclass
class MarketsAdapter:
    """Resolve ``markets.<venue>.<id>.<field>`` against local market state."""

    store: Any
    organization_id: str
    prefix: str = "markets."

    async def resolve(self, source: str) -> Optional[InputObservation]:
        if not source.startswith(self.prefix):
            return None
        remainder = source[len(self.prefix):].strip(".")
        parts = remainder.split(".")
        if len(parts) < 3:
            return None
        venue, identifier, *field_parts = parts
        field = ".".join(field_parts)
        if venue not in _VENUE_PREFIXES:
            return None
        try:
            if venue == "alpaca":
                return self._resolve_equity(source, identifier, field)
            return self._resolve_forecast_market(source, venue, identifier, field)
        except Exception:
            return None

    # ── venue handlers ─────────────────────────────────────────────

    def _resolve_forecast_market(
        self, source: str, venue: str, external_id: str, field: str
    ) -> Optional[InputObservation]:
        from noosphere.models import ForecastMarket, ForecastSource

        venue_enum = (
            ForecastSource.POLYMARKET if venue == "polymarket" else ForecastSource.KALSHI
        )
        with self.store.session() as session:
            stmt = (
                select(ForecastMarket)
                .where(ForecastMarket.source == venue_enum.value)
                .where(ForecastMarket.external_id == external_id)
                .where(ForecastMarket.organization_id == self.organization_id)
                .order_by(desc(ForecastMarket.updated_at))
                .limit(1)
            )
            row = session.exec(stmt).first()
        if row is None:
            return None
        value = getattr(row, field, None)
        if value is None:
            return None
        return InputObservation(
            value=_unwrap_decimal(value),
            observed_at=row.updated_at or row.open_time or datetime.now(timezone.utc),
            source=source,
            source_url=None,
            source_artifact_id=row.id,
        )

    def _resolve_equity(
        self, source: str, symbol: str, field: str
    ) -> Optional[InputObservation]:
        from noosphere.models import EquityInstrument, EquityPriceTick

        with self.store.session() as session:
            instrument = session.exec(
                select(EquityInstrument)
                .where(EquityInstrument.symbol == symbol)
                .limit(1)
            ).first()
            if instrument is None:
                return None
            # Allow either an instrument-level column or a price-tick
            # column. Price-tick fields (open/high/low/close/volume) live
            # on the latest tick.
            value = getattr(instrument, field, None)
            observed_at = instrument.last_price_at
            artifact_id = instrument.id
            if value is None:
                tick = session.exec(
                    select(EquityPriceTick)
                    .where(EquityPriceTick.instrument_id == instrument.id)
                    .order_by(desc(EquityPriceTick.ts))
                    .limit(1)
                ).first()
                if tick is None:
                    return None
                value = getattr(tick, field, None)
                observed_at = tick.ts
                artifact_id = tick.id
        if value is None:
            return None
        return InputObservation(
            value=_unwrap_decimal(value),
            observed_at=observed_at or datetime.now(timezone.utc),
            source=source,
            source_url=None,
            source_artifact_id=artifact_id,
        )


def _unwrap_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


__all__ = ["MarketsAdapter"]
