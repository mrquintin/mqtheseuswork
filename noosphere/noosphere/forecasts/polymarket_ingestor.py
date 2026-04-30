"""Read-only Polymarket Gamma market ingestor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlmodel import select

from noosphere.forecasts._polymarket_client import PolymarketGammaClient
from noosphere.forecasts.config import PolymarketConfig
from noosphere.forecasts.resolution_tracker import poll_market
from noosphere.models import ForecastMarket, ForecastMarketStatus, ForecastSource
from noosphere.observability import get_logger
from noosphere.store import Store


PRICE_UPDATE_THRESHOLD = Decimal("0.005")
DEFAULT_PAGE_SIZE = 100
SOURCE = ForecastSource.POLYMARKET
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
    config: PolymarketConfig,
    now: datetime | None = None,
) -> IngestResult:
    """
    Pull active+open markets in batches and upsert each into ForecastMarket.

    Dedupe key: (source=POLYMARKET, externalId=conditionId). Existing rows are
    rewritten only when a price moves by at least 0.005, or title/closeTime/status
    changes, so downstream change detection is not churned by raw metadata noise.
    """

    effective_now = _aware_utc(now or datetime.now(UTC))
    accepted = _accepted_category_map(config.accepted_categories)
    client = PolymarketGammaClient(
        base=config.gamma_base,
        timeout_s=config.request_timeout_s,
    )
    result = IngestResult(fetched=0, inserted=0, updated=0, skipped=0, errors=[])
    resolution_tasks: list[asyncio.Task[Any]] = []

    try:
        offset = 0
        max_markets = max(0, int(config.max_markets_per_cycle))
        while result.fetched < max_markets:
            limit = min(DEFAULT_PAGE_SIZE, max_markets - result.fetched)
            if limit <= 0:
                break
            page = await client.list_markets(
                active=True,
                closed=False,
                limit=limit,
                offset=offset,
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
                                    polymarket_client=client,
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
                        f"market:{_condition_id(payload) or '<missing>'}:"
                        f"{type(exc).__name__}: {exc}"
                    )

            offset += len(page)
        await _collect_resolution_tasks(resolution_tasks, result)
    finally:
        await client.aclose()

    return result


def _persist_payload(
    store: Store,
    payload: dict[str, Any],
    *,
    config: PolymarketConfig,
    accepted_categories: dict[str, str],
    now: datetime,
) -> tuple[str, str | None]:
    close_time = _parse_datetime_first(
        payload,
        ("closeTime", "endDate", "endDateIso", "closedTime"),
    )
    external_id = _condition_id(payload)
    existing = _find_existing_market(store, external_id) if external_id else None
    if _payload_terminal(payload) or (close_time is not None and _aware_utc(close_time) < now):
        return "skipped", existing.id if existing is not None else None

    tags = _extract_tags(payload)
    category = _select_category(tags, accepted_categories)
    if accepted_categories and category is None:
        return "skipped", None

    if not external_id:
        raise ValueError("Polymarket market missing conditionId")

    yes_price, no_price = _extract_prices(payload)
    market = ForecastMarket(
        organization_id=config.organization_id,
        source=SOURCE,
        external_id=external_id,
        title=_market_title(payload),
        description=_optional_str(payload.get("description")),
        resolution_criteria=_optional_str(
            payload.get("resolutionCriteria") or payload.get("resolution_criteria")
        ),
        category=category,
        current_yes_price=yes_price,
        current_no_price=no_price,
        volume=_decimal_or_none(payload.get("volumeNum") or payload.get("volume")),
        open_time=_parse_datetime_first(
            payload,
            ("openTime", "startDate", "startDateIso"),
        ),
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


def _extract_prices(payload: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    outcomes = _parse_payload_array(payload.get("outcomes") or payload.get("outcome"))
    prices = _parse_payload_array(payload.get("outcomePrices") or payload.get("prices"))

    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    if outcomes and prices:
        for outcome, price in zip(outcomes, prices, strict=False):
            label = _outcome_label(outcome).lower()
            if label == "yes":
                yes_price = _decimal_or_none(price)
            elif label == "no":
                no_price = _decimal_or_none(price)

    for item in outcomes:
        if isinstance(item, dict):
            label = _outcome_label(item).lower()
            price = _decimal_or_none(item.get("price"))
            if label == "yes" and price is not None:
                yes_price = price
            elif label == "no" and price is not None:
                no_price = price

    if yes_price is None:
        yes_price = _decimal_or_none(
            payload.get("currentYesPrice")
            or payload.get("yesPrice")
            or payload.get("lastTradePrice")
        )
    if no_price is None:
        no_price = _decimal_or_none(
            payload.get("currentNoPrice") or payload.get("noPrice")
        )
    return yes_price, no_price


def _parse_payload_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return [stripped]
    return []


def _extract_tags(payload: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    _extend_tags(tags, payload.get("tags"))
    _extend_tags(tags, payload.get("category"))
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        _extend_tags(tags, event.get("tags"))
        _extend_tags(tags, event.get("category"))
        _extend_tags(tags, event.get("categories"))
    return list(dict.fromkeys(tag for tag in tags if tag))


def _extend_tags(out: list[str], raw: Any) -> None:
    if raw is None:
        return
    if isinstance(raw, str):
        parsed = _parse_payload_array(raw)
        if parsed and parsed != [raw.strip()]:
            _extend_tags(out, parsed)
            return
        value = raw.strip()
        if value:
            out.append(value)
        return
    if isinstance(raw, dict):
        value = (
            raw.get("slug")
            or raw.get("label")
            or raw.get("name")
            or raw.get("title")
        )
        if value:
            out.append(str(value).strip())
        return
    if isinstance(raw, (list, tuple)):
        for item in raw:
            _extend_tags(out, item)


def _select_category(tags: list[str], accepted: dict[str, str]) -> str | None:
    if accepted:
        for tag in tags:
            configured = accepted.get(_category_key(tag))
            if configured is not None:
                return configured
        return None
    return tags[0] if tags else None


def _accepted_category_map(categories: list[str]) -> dict[str, str]:
    return {
        _category_key(category): category.strip()
        for category in categories
        if category and category.strip()
    }


def _category_key(value: str) -> str:
    return value.strip().lower()


def _condition_id(payload: dict[str, Any]) -> str:
    return str(payload.get("conditionId") or payload.get("condition_id") or "").strip()


def _market_title(payload: dict[str, Any]) -> str:
    title = str(payload.get("title") or payload.get("question") or "").strip()
    if not title:
        raise ValueError("Polymarket market missing title/question")
    return title[:280]


def _outcome_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("label")
            or value.get("outcome")
            or ""
        )
    return str(value)


def _parse_datetime_first(
    payload: dict[str, Any],
    keys: tuple[str, ...],
) -> datetime | None:
    for key in keys:
        parsed = _parse_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _payload_terminal(payload: dict[str, Any]) -> bool:
    if _as_bool(payload.get("closed")) or _as_bool(payload.get("resolved")):
        return True
    status = _optional_str(payload.get("status") or payload.get("marketStatus"))
    return status is not None and status.lower() in {
        "closed",
        "resolved",
        "settled",
        "cancelled",
        "canceled",
    }


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
        "polymarket_forecast_market_upsert",
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
