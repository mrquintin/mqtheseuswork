"""Read-only equity instrument + intraday-bar ingestor (Alpaca-backed)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from noosphere.equities._alpaca_client import AlpacaClient
from noosphere.equities.config import AlpacaConfig
from noosphere.models import (
    EquityAssetClass,
    EquityInstrument,
    EquityPriceSource,
    EquityPriceTick,
    EquitySignal,
    EquitySignalStatus,
)
from noosphere.observability import get_logger
from noosphere.store import Store

# Updates below this fractional move (0.5%) within the freshness window
# are skipped to avoid churning EquityInstrument.lastPrice on noise.
PRICE_UPDATE_THRESHOLD = Decimal("0.005")
PRICE_STALENESS_S = 5 * 60

log = get_logger(__name__)


@dataclass
class IngestResult:
    fetched: int
    inserted: int
    updated: int
    skipped: int
    errors: list[str]


async def ingest_once(
    store: Store,
    *,
    config: AlpacaConfig,
    now: datetime | None = None,
) -> IngestResult:
    """Pull tradeable US equities + ETFs, upsert instruments, refresh prices.

    When credentials are absent, returns immediately with a single
    structured-log line (``ALPACA_NOT_CONFIGURED``) so the scheduler can
    safely call this every cycle on dev machines without ever issuing
    an outbound HTTP request.
    """

    result = IngestResult(fetched=0, inserted=0, updated=0, skipped=0, errors=[])
    if not config.is_configured:
        log.info("ALPACA_NOT_CONFIGURED", is_paper=config.is_paper)
        return result

    effective_now = _aware_utc(now or datetime.now(UTC))
    accepted = {sym.strip().upper() for sym in config.accepted_symbols if sym.strip()}
    held_instrument_ids = _held_instrument_ids(store, config.organization_id)

    client = AlpacaClient(
        api_base=config.api_base,
        data_base=config.data_base,
        api_key_id=config.api_key_id,
        api_secret_key=config.api_secret_key,
        timeout_s=config.request_timeout_s,
    )

    try:
        assets = await client.list_assets(
            asset_class="us_equity",
            tradable_only=True,
        )
        for raw in assets:
            symbol = str(raw.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if accepted and symbol not in accepted:
                continue
            result.fetched += 1
            try:
                instrument, action = _persist_instrument(
                    store,
                    raw,
                    config=config,
                    now=effective_now,
                )
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(
                    f"asset:{symbol}:{type(exc).__name__}: {exc}"
                )
                continue
            if action == "inserted":
                result.inserted += 1
            elif action == "updated":
                result.updated += 1
            else:
                result.skipped += 1

            if instrument.id in held_instrument_ids:
                try:
                    await _ingest_intraday_bars(
                        store,
                        client,
                        instrument=instrument,
                        now=effective_now,
                    )
                except Exception as exc:
                    result.errors.append(
                        f"bars:{symbol}:{type(exc).__name__}: {exc}"
                    )
    finally:
        await client.aclose()

    return result


def _persist_instrument(
    store: Store,
    raw: dict[str, Any],
    *,
    config: AlpacaConfig,
    now: datetime,
) -> tuple[EquityInstrument, str]:
    symbol = str(raw.get("symbol") or "").strip().upper()
    exchange = str(raw.get("exchange") or "").strip().upper() or "UNKNOWN"
    asset_class = _map_asset_class(raw)
    name = str(raw.get("name") or symbol).strip()[:280]

    existing = store.get_equity_instrument_by_symbol(symbol, exchange)
    if existing is not None:
        existing_id = existing.id
        existing_last_price = existing.last_price
        existing_last_price_at = existing.last_price_at
    else:
        existing_id = None
        existing_last_price = None
        existing_last_price_at = None

    candidate_price = _extract_price(raw)
    new_last_price = existing_last_price
    new_last_price_at = existing_last_price_at
    price_changed = _should_update_price(
        existing_last_price,
        existing_last_price_at,
        candidate_price,
        now=now,
    )
    if candidate_price is not None and price_changed:
        new_last_price = candidate_price
        new_last_price_at = now

    instrument = EquityInstrument(
        symbol=symbol,
        exchange=exchange,
        asset_class=asset_class,
        name=name,
        is_tradable=bool(raw.get("tradable", True)),
        last_price=new_last_price,
        last_price_at=new_last_price_at,
        currency=str(raw.get("currency") or "USD"),
    )
    if existing_id is not None:
        instrument.id = existing_id

    store.put_equity_instrument(instrument)

    if existing_id is None:
        action = "inserted"
    elif price_changed and candidate_price is not None:
        action = "updated"
    else:
        action = "skipped"
    log.info(
        "alpaca_equity_instrument_upsert",
        action=action,
        symbol=symbol,
        exchange=exchange,
        last_price=str(new_last_price) if new_last_price is not None else None,
    )
    # Refresh instrument id after upsert in case Alembic returned the existing row.
    loaded = store.get_equity_instrument_by_symbol(symbol, exchange)
    if loaded is not None:
        instrument = loaded
    return instrument, action


async def _ingest_intraday_bars(
    store: Store,
    client: AlpacaClient,
    *,
    instrument: EquityInstrument,
    now: datetime,
) -> None:
    start = now - timedelta(hours=4)
    bars = await client.get_bars(
        instrument.symbol,
        timeframe="1Min",
        start=start,
        end=now,
        limit=240,
    )
    for bar in bars:
        ts = _parse_dt(bar.get("t"))
        if ts is None:
            continue
        open_ = _decimal_or_none(bar.get("o"))
        high = _decimal_or_none(bar.get("h"))
        low = _decimal_or_none(bar.get("l"))
        close = _decimal_or_none(bar.get("c"))
        volume = _decimal_or_none(bar.get("v")) or Decimal("0")
        if open_ is None or high is None or low is None or close is None:
            continue
        tick = EquityPriceTick(
            instrument_id=instrument.id,
            ts=ts,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            source=EquityPriceSource.ALPACA,
        )
        store.put_equity_price_tick(tick)


def _held_instrument_ids(store: Store, organization_id: str) -> set[str]:
    org = organization_id or None
    signals = store.list_open_signals(organization_id=org, limit=500)
    return {sig.instrument_id for sig in signals if isinstance(sig, EquitySignal)
            and _enum_value(sig.status) == EquitySignalStatus.PUBLISHED.value}


def _should_update_price(
    existing_price: Decimal | None,
    existing_at: datetime | None,
    candidate: Decimal | None,
    *,
    now: datetime,
) -> bool:
    if candidate is None:
        return False
    if existing_price is None:
        return True
    move = abs(Decimal(candidate) - Decimal(existing_price))
    base = abs(Decimal(existing_price))
    if base == 0:
        return move > 0
    if move / base >= PRICE_UPDATE_THRESHOLD:
        return True
    if existing_at is None:
        return True
    seconds = (now - _aware_utc(existing_at)).total_seconds()
    return seconds > PRICE_STALENESS_S


def _extract_price(raw: dict[str, Any]) -> Decimal | None:
    for key in ("last_price", "lastPrice", "price", "close"):
        value = _decimal_or_none(raw.get(key))
        if value is not None:
            return value
    return None


def _map_asset_class(raw: dict[str, Any]) -> EquityAssetClass:
    flag = str(raw.get("class") or raw.get("asset_class") or "").lower()
    if flag in {"us_equity", "equity", "stock", "us_stock"}:
        kind = str(raw.get("subtype") or raw.get("type") or "").lower()
        if "etf" in kind:
            return EquityAssetClass.ETF
        if "adr" in kind:
            return EquityAssetClass.ADR
    name = str(raw.get("name") or "").lower()
    if "etf" in name or "trust" in name or "fund" in name:
        return EquityAssetClass.ETF
    return EquityAssetClass.STOCK


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)
