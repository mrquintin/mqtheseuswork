"""Live Kalshi order adapter for Forecasts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from noosphere.forecasts._kalshi_client import KalshiAPIError, KalshiClient


@dataclass(frozen=True)
class KalshiLiveOrder:
    external_order_id: str
    status: str
    filled_size: Decimal = Decimal("0")
    average_price: Decimal | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class KalshiLiveClient(KalshiClient):
    @classmethod
    def from_env(cls) -> KalshiLiveClient:
        private_key = (
            os.getenv("KALSHI_API_PRIVATE_KEY", "").replace("\\n", "\n").strip()
            or os.getenv("KALSHI_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
        )
        return cls(
            base=os.getenv(
                "KALSHI_API_BASE",
                "https://api.elections.kalshi.com/trade-api/v2",
            ),
            key_id=os.getenv("KALSHI_API_KEY_ID", "").strip(),
            private_key_pem=private_key,
        )

    async def place_order(
        self,
        ticker: str,
        side: Literal["YES", "NO", "yes", "no"],
        count: int,
        price: Decimal | float | str,
        order_type: str,
        client_order_id: str,
    ) -> KalshiLiveOrder:
        side_value = side.lower()
        if side_value not in {"yes", "no"}:
            raise ValueError("Kalshi side must be yes or no")
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side_value,
            "action": "buy",
            "client_order_id": client_order_id,
            "count": int(count),
            f"{side_value}_price": _price_cents(price),
            "time_in_force": _time_in_force(order_type),
        }
        payload = await self._request_json("POST", "/portfolio/orders", json_body=body)
        return _order_from_payload(payload)

    async def cancel_order(self, order_id: str) -> KalshiLiveOrder:
        payload = await self._request_json("DELETE", f"/portfolio/orders/{order_id}")
        return _order_from_payload(
            payload,
            fallback_order_id=order_id,
            fallback_status="CANCELLED",
        )

    async def get_order(self, order_id: str) -> KalshiLiveOrder:
        payload = await self._request_json("GET", f"/portfolio/orders/{order_id}")
        return _order_from_payload(payload, fallback_order_id=order_id)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        client = self._ensure_client()
        headers = self._signed_headers(method, path)
        headers["Content-Type"] = "application/json"
        content = (
            json.dumps(json_body).encode("utf-8")
            if json_body is not None
            else None
        )
        response = await client.request(
            method,
            f"{self._base}{path}",
            headers=headers,
            content=content,
        )
        if response.status_code == 404:
            raise KalshiAPIError(404, response.text)
        if 400 <= response.status_code:
            raise KalshiAPIError(response.status_code, response.text)
        if not response.content:
            return {}
        return response.json()


def _order_from_payload(
    payload: Any,
    *,
    fallback_order_id: str | None = None,
    fallback_status: str | None = None,
) -> KalshiLiveOrder:
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected Kalshi order payload shape")
    order = payload.get("order")
    if isinstance(order, dict):
        payload = order
    order_id = (
        _str_first(payload, "external_order_id", "order_id", "id")
        or fallback_order_id
    )
    if not order_id:
        raise RuntimeError("Kalshi order response missing order_id")
    status = _str_first(payload, "status", "state") or fallback_status or "SUBMITTED"
    filled_size = _decimal_first(
        payload,
        "filled_size",
        "filledSize",
        "fill_count_fp",
        "filled_count",
    )
    return KalshiLiveOrder(
        external_order_id=order_id,
        status=str(status),
        filled_size=filled_size,
        average_price=_average_price(payload, filled_size),
        raw_payload=payload,
    )


def _average_price(payload: dict[str, Any], filled_size: Decimal) -> Decimal | None:
    for key in (
        "average_price",
        "averagePrice",
        "yes_price_dollars",
        "no_price_dollars",
    ):
        value = payload.get(key)
        if value is not None:
            try:
                return _decimal(value)
            except ValueError:
                continue
    cost = _decimal_first_or_none(
        payload,
        "taker_fill_cost_dollars",
        "maker_fill_cost_dollars",
    )
    if cost is None or filled_size <= Decimal("0"):
        return None
    return (cost / filled_size).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _time_in_force(order_type: str) -> str:
    normalized = order_type.strip().upper()
    return {
        "FOK": "fill_or_kill",
        "FAK": "immediate_or_cancel",
        "IOC": "immediate_or_cancel",
        "GTC": "good_till_canceled",
        "GOOD_TILL_CANCELED": "good_till_canceled",
    }.get(normalized, order_type.strip().lower())


def _price_cents(value: Decimal | float | str) -> int:
    cents = (_decimal(value) * Decimal("100")).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    if not Decimal("1") <= cents <= Decimal("99"):
        raise ValueError("Kalshi order price must be between 0.01 and 0.99")
    return int(cents)


def _str_first(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _decimal_first(payload: dict[str, Any], *keys: str) -> Decimal:
    return _decimal_first_or_none(payload, *keys) or Decimal("0")


def _decimal_first_or_none(payload: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return _decimal(value)
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a decimal value: {value!r}") from exc
