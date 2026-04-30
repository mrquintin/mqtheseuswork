"""Live Polymarket CLOB adapter for Forecasts.

The Polymarket CLOB currently signs orders as EIP-712 payloads and uses L2
HMAC credentials for authenticated trading requests. This wrapper intentionally
delegates those moving parts to Polymarket's SDK when live trading is actually
enabled; importing this module never constructs a wallet or contacts the CLOB.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field

from noosphere.forecasts._polymarket_client import PolymarketGammaClient


class PolymarketLiveOrder(BaseModel):
    external_order_id: str
    status: str
    filled_size: Decimal = Decimal("0")
    average_price: Decimal | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PolymarketLiveClient(PolymarketGammaClient):
    """Async live-trading facade over the Polymarket CLOB SDK."""

    def __init__(
        self,
        *,
        base: str = "https://clob.polymarket.com",
        private_key: str | None = None,
        chain_id: int = 137,
        signature_type: int = 0,
        funder: str | None = None,
        tick_size: str = "0.01",
        neg_risk: bool = False,
        timeout_s: float = 15.0,
    ) -> None:
        super().__init__(base=base, timeout_s=timeout_s)
        self._private_key = (
            private_key or os.getenv("POLYMARKET_PRIVATE_KEY", "")
        ).strip()
        self._chain_id = chain_id
        self._signature_type = signature_type
        self._funder = funder
        self._tick_size = tick_size
        self._neg_risk = neg_risk
        self._sdk_client: Any | None = None
        self.wallet_address = _wallet_address_or_none(self._private_key)

    @classmethod
    def from_env(cls) -> PolymarketLiveClient:
        return cls(
            base=os.getenv("POLYMARKET_CLOB_BASE", "https://clob.polymarket.com"),
            private_key=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
            chain_id=int(os.getenv("POLYMARKET_CHAIN_ID", "137")),
            signature_type=int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0")),
            funder=os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None,
            tick_size=os.getenv("POLYMARKET_DEFAULT_TICK_SIZE", "0.01"),
            neg_risk=os.getenv("POLYMARKET_DEFAULT_NEG_RISK", "").strip().lower()
            in {"1", "true", "yes", "y"},
        )

    async def place_order(
        self,
        condition_id: str,
        outcome_index: int,
        side: Literal["BUY", "SELL"],
        size: Decimal | float | str,
        price: Decimal | float | str,
        order_type: str,
    ) -> PolymarketLiveOrder:
        """Create, EIP-712 sign, and post an order through the CLOB SDK.

        Polymarket's current docs describe `createAndPostOrder` /
        `createOrder` + `postOrder` over `tokenID`. The local market mirror
        stores `conditionId`; callers should pass the resolved CLOB token id
        when it is available and fall back to the condition id only for mocks.
        """

        payload = await asyncio.to_thread(
            self._sdk_place_order,
            condition_id,
            outcome_index,
            side,
            size,
            price,
            order_type,
        )
        return _order_from_payload(payload)

    async def cancel_order(self, order_id: str) -> PolymarketLiveOrder:
        payload = await asyncio.to_thread(self._sdk_cancel_order, order_id)
        return _order_from_payload(
            payload,
            fallback_order_id=order_id,
            fallback_status="CANCELLED",
        )

    async def get_order(self, order_id: str) -> PolymarketLiveOrder:
        payload = await asyncio.to_thread(self._sdk_get_order, order_id)
        return _order_from_payload(payload, fallback_order_id=order_id)

    def _sdk_place_order(
        self,
        token_id: str,
        _outcome_index: int,
        side: str,
        size: Decimal | float | str,
        price: Decimal | float | str,
        order_type: str,
    ) -> dict[str, Any]:
        client = self._ensure_sdk_client()
        sdk_side = _sdk_side(side)
        sdk_order_type = _sdk_order_type(order_type)
        order_args = _sdk_order_args(
            token_id=token_id,
            price=float(_decimal(price)),
            size=float(_decimal(size)),
            side=sdk_side,
        )
        options = {"tickSize": self._tick_size, "negRisk": self._neg_risk}

        method = getattr(client, "createAndPostOrder", None) or getattr(
            client,
            "create_and_post_order",
            None,
        )
        if method is not None:
            return _payload_dict(method(order_args, options, sdk_order_type))

        create_order = getattr(client, "createOrder", None) or getattr(
            client,
            "create_order",
            None,
        )
        post_order = getattr(client, "postOrder", None) or getattr(
            client,
            "post_order",
            None,
        )
        if create_order is None or post_order is None:
            raise RuntimeError(
                "Polymarket SDK does not expose create/post order methods expected "
                "by the CLOB docs"
            )
        signed_order = create_order(order_args, options)
        return _payload_dict(post_order(signed_order, sdk_order_type))

    def _sdk_cancel_order(self, order_id: str) -> dict[str, Any]:
        client = self._ensure_sdk_client()
        method = getattr(client, "cancelOrder", None) or getattr(client, "cancel", None)
        if method is None:
            raise RuntimeError("Polymarket SDK does not expose cancelOrder/cancel")
        return _payload_dict(method(order_id))

    def _sdk_get_order(self, order_id: str) -> dict[str, Any]:
        client = self._ensure_sdk_client()
        method = getattr(client, "getOrder", None) or getattr(client, "get_order", None)
        if method is None:
            raise RuntimeError("Polymarket SDK does not expose getOrder/get_order")
        return _payload_dict(method(order_id))

    def _ensure_sdk_client(self) -> Any:
        if not self._private_key:
            raise RuntimeError("POLYMARKET_PRIVATE_KEY is required for live trading")
        if self._sdk_client is not None:
            return self._sdk_client

        try:
            from py_clob_client.client import ClobClient
        except ImportError as exc:  # pragma: no cover - depends on optional live SDK.
            raise RuntimeError(
                "py-clob-client is required for Polymarket live trading"
            ) from exc

        kwargs: dict[str, Any] = {
            "host": self._base,
            "key": self._private_key,
            "chain_id": self._chain_id,
        }
        if self._signature_type is not None:
            kwargs["signature_type"] = self._signature_type
        if self._funder:
            kwargs["funder"] = self._funder
        client = ClobClient(**kwargs)

        derive = getattr(client, "create_or_derive_api_creds", None) or getattr(
            client,
            "createOrDeriveApiKey",
            None,
        )
        set_creds = getattr(client, "set_api_creds", None) or getattr(
            client,
            "setApiCreds",
            None,
        )
        if derive is not None and set_creds is not None:
            set_creds(derive())

        self._sdk_client = client
        return client


def _wallet_address_or_none(private_key: str) -> str | None:
    if not private_key:
        return None
    try:
        from eth_account import Account
    except ImportError:  # pragma: no cover - optional live dependency.
        return None
    return str(Account.from_key(private_key).address)


def _sdk_order_args(*, token_id: str, price: float, size: float, side: Any) -> Any:
    try:
        from py_clob_client.clob_types import OrderArgs
    except ImportError:  # pragma: no cover - handled before live use.
        return {
            "tokenID": token_id,
            "token_id": token_id,
            "price": price,
            "size": size,
            "side": side,
        }
    try:
        return OrderArgs(price=price, size=size, side=side, token_id=token_id)
    except TypeError:
        return OrderArgs(price=price, size=size, side=side, tokenID=token_id)


def _sdk_side(side: str) -> Any:
    normalized = side.upper()
    try:
        from py_clob_client.order_builder.constants import BUY, SELL

        return BUY if normalized == "BUY" else SELL
    except ImportError:  # pragma: no cover - handled before live use.
        return normalized


def _sdk_order_type(order_type: str) -> Any:
    normalized = order_type.upper()
    try:
        from py_clob_client.clob_types import OrderType
    except ImportError:  # pragma: no cover - handled before live use.
        return normalized
    return getattr(OrderType, normalized, normalized)


def _order_from_payload(
    payload: dict[str, Any],
    *,
    fallback_order_id: str | None = None,
    fallback_status: str | None = None,
) -> PolymarketLiveOrder:
    order_id = _str_first(
        payload,
        "external_order_id",
        "orderID",
        "order_id",
        "id",
    ) or fallback_order_id
    if not order_id:
        raise RuntimeError("Polymarket order response missing order id")
    status = _str_first(payload, "status", "state") or fallback_status or "SUBMITTED"
    return PolymarketLiveOrder(
        external_order_id=order_id,
        status=str(status),
        filled_size=_decimal_first(
            payload,
            "filled_size",
            "filledSize",
            "filledAmount",
            "filled_amount",
            "matchedAmount",
        ),
        average_price=_decimal_first_or_none(
            payload,
            "average_price",
            "averagePrice",
            "avgPrice",
            "price",
        ),
        raw_payload=payload,
    )


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise RuntimeError(
        f"unexpected Polymarket SDK payload type: {type(value).__name__}"
    )


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
