"""Read-only Kalshi market ingestor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlmodel import select

from noosphere.forecasts._kalshi_client import KalshiClient
from noosphere.forecasts.config import KalshiConfig
from noosphere.forecasts.resolution_tracker import poll_market
from noosphere.models import ForecastMarket, ForecastMarketStatus, ForecastSource
from noosphere.observability import get_logger
from noosphere.store import Store


PRICE_UPDATE_THRESHOLD = Decimal("0.005")
DEFAULT_PAGE_SIZE = 100
SOURCE = ForecastSource.KALSHI
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
    config: KalshiConfig,
    now: datetime | None = None,
) -> IngestResult:
    """
    Pull open Kalshi markets in batches and upsert each into ForecastMarket.

    Dedupe key: (source=KALSHI, externalId=ticker). Existing rows are rewritten
    only when a price moves by at least 0.005, or title/closeTime/status
    changes, matching the Polymarket ingestor's change-detection threshold.
    """

    if not config.is_configured:
        log.warning(
            "kalshi_forecasts_not_configured",
            source=SOURCE.value,
            error="KALSHI_NOT_CONFIGURED",
        )
        return IngestResult(
            fetched=0,
            inserted=0,
            updated=0,
            skipped=0,
            errors=["KALSHI_NOT_CONFIGURED"],
        )

    effective_now = _aware_utc(now or datetime.now(UTC))
    accepted = _accepted_category_map(config.accepted_categories)
    client = KalshiClient(
        base=config.api_base,
        key_id=config.api_key_id,
        private_key_pem=config.api_private_key_pem,
        timeout_s=config.request_timeout_s,
    )
    result = IngestResult(fetched=0, inserted=0, updated=0, skipped=0, errors=[])
    resolution_tasks: list[asyncio.Task[Any]] = []

    try:
        cursor: str | None = None
        max_markets = max(0, int(config.max_markets_per_cycle))
        while result.fetched < max_markets:
            limit = min(DEFAULT_PAGE_SIZE, max_markets - result.fetched)
            if limit <= 0:
                break
            page, next_cursor = await client.list_markets(
                status="open",
                limit=limit,
                cursor=cursor,
            )
            if not page:
                break

            for payload in page[:limit]:
                if result.fetched >= max_markets:
                    break
                result.fetched += 1
                try:
                    action = _persist_payload(
                        store,
                        payload,
                        config=config,
                        accepted_categories=accepted,
                        now=effective_now,
                    )
                    if isinstance(action, tuple):
                        action, poll_market_id = action
                    else:
                        poll_market_id = None
                    if poll_market_id:
                        resolution_tasks.append(
                            asyncio.create_task(
                                poll_market(
                                    store,
                                    poll_market_id,
                                    kalshi_client=client,
                                )
                            )
                        )
                    if action == "inserted":
                        result.inserted += 1
                    elif action == "updated":
                        result.updated += 1
                    else:
                        result.skipped += 1
                except Exception as exc:
                    result.errors.append(
                        f"market:{_ticker(payload) or '<missing>'}:"
                        f"{type(exc).__name__}: {exc}"
                    )

            if not next_cursor:
                break
            cursor = next_cursor
        await _collect_resolution_tasks(resolution_tasks, result)
    finally:
        await client.aclose()

    return result


def _persist_payload(
    store: Store,
    payload: dict[str, Any],
    *,
    config: KalshiConfig,
    accepted_categories: dict[str, str],
    now: datetime,
) -> tuple[str, str | None]:
    status = _optional_str(payload.get("status"))
    close_time = _parse_datetime(payload.get("close_time"))
    external_id = _ticker(payload)
    existing = _find_existing_market(store, external_id) if external_id else None
    if (status is not None and status.lower() != "open") or (
        close_time is not None and _aware_utc(close_time) < now
    ):
        return "skipped", existing.id if existing is not None else None

    category = _optional_str(payload.get("category"))
    if accepted_categories and not _category_is_accepted(
        category,
        accepted_categories,
    ):
        return "skipped", None

    if not external_id:
        raise ValueError("Kalshi market missing ticker")

    market = ForecastMarket(
        organization_id=config.organization_id,
        source=SOURCE,
        external_id=external_id,
        title=_market_title(payload),
        description=_optional_str(payload.get("subtitle")),
        resolution_criteria=_resolution_criteria(payload),
        category=category,
        current_yes_price=_price_from_cents(payload.get("yes_bid")),
        current_no_price=_price_from_cents(payload.get("no_bid")),
        volume=_decimal_or_none(payload.get("volume_24h")),
        open_time=_parse_datetime(payload.get("open_time")),
        close_time=close_time,
        raw_payload=_json_safe(payload),
        status=ForecastMarketStatus.OPEN,
    )

    if existing is None:
        store.put_forecast_market(market)
        _log_upsert("inserted", market)
        return "inserted", None

    market.id = existing.id
    if not _should_update(existing, market):
        return "skipped", None

    store.put_forecast_market(market)
    _log_upsert("updated", market)
    return "updated", None


async def _collect_resolution_tasks(
    tasks: list[asyncio.Task[Any]],
    result: IngestResult,
) -> None:
    if not tasks:
        return
    for item in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(item, Exception):
            result.errors.append(f"resolution:{type(item).__name__}: {item}")
            continue
        result.errors.extend(f"resolution:{error}" for error in item.errors)


def _find_existing_market(store: Store, external_id: str) -> ForecastMarket | None:
    source_value = SOURCE.value
    with store.session() as session:
        existing = session.exec(
            select(ForecastMarket)
            .where(ForecastMarket.source == source_value)
            .where(ForecastMarket.external_id == external_id)
        ).first()
        return existing.model_copy() if existing is not None else None


def _should_update(existing: ForecastMarket, candidate: ForecastMarket) -> bool:
    if _price_changed(existing.current_yes_price, candidate.current_yes_price):
        return True
    if _price_changed(existing.current_no_price, candidate.current_no_price):
        return True
    if existing.title != candidate.title:
        return True
    if not _same_datetime(existing.close_time, candidate.close_time):
        return True
    return _enum_value(existing.status) != _enum_value(candidate.status)


def _price_changed(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None and right is None:
        return False
    if left is None or right is None:
        return True
    return abs(Decimal(left) - Decimal(right)) >= PRICE_UPDATE_THRESHOLD


def _price_from_cents(value: Any) -> Decimal | None:
    cents = _decimal_or_none(value)
    if cents is None:
        return None
    return cents / Decimal("100")


def _resolution_criteria(payload: dict[str, Any]) -> str | None:
    primary = _optional_str(payload.get("rules_primary"))
    secondary = _optional_str(payload.get("rules_secondary"))
    if primary and secondary:
        return f"{primary}\n\n{secondary}"
    return primary or secondary


def _accepted_category_map(categories: list[str]) -> dict[str, str]:
    return {
        _category_key(category): category.strip()
        for category in categories
        if category and category.strip()
    }


def _category_is_accepted(category: str | None, accepted: dict[str, str]) -> bool:
    if category is None:
        return False
    return _category_key(category) in accepted


def _category_key(value: str) -> str:
    return value.strip().lower()


def _ticker(payload: dict[str, Any]) -> str:
    return str(payload.get("ticker") or "").strip()


def _market_title(payload: dict[str, Any]) -> str:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("Kalshi market missing title")
    return title[:280]


def _parse_datetime(value: Any) -> datetime | None:
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


def _same_datetime(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    return _aware_utc(left) == _aware_utc(right)


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


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=str))


def _log_upsert(action: str, market: ForecastMarket) -> None:
    log.info(
        "kalshi_forecast_market_upsert",
        action=action,
        source=SOURCE.value,
        external_id=market.external_id,
        market_id=market.id,
        yes_price=(
            str(market.current_yes_price)
            if market.current_yes_price is not None
            else None
        ),
        no_price=(
            str(market.current_no_price)
            if market.current_no_price is not None
            else None
        ),
    )
