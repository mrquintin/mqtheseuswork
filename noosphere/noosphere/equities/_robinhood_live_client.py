"""Unofficial Robinhood live-trading adapter.

Robinhood does not publish a supported retail trading API. This wrapper
delegates to the reverse-engineered ``robin_stocks`` library, which the
upstream Robinhood iOS/Android releases periodically break. The adapter is
OFF by default; the eight-gate safety contract in
:mod:`noosphere.forecasts.safety` still applies before any order leaves the
process.

Importing this module never authenticates, never calls Robinhood, and never
imports ``robin_stocks`` — the SDK import is lazy and only happens when
:meth:`RobinhoodLiveClient.authenticate` is invoked.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from noosphere.equities.config import RobinhoodConfig
from noosphere.observability import get_logger

log = get_logger(__name__)


class LiveBrokerError(RuntimeError):
    """Typed error raised when a live broker call fails.

    Carries the broker name (``"ALPACA"`` / ``"ROBINHOOD"``) and a short
    machine-readable ``code`` so the kill-switch streak tracker can decide
    whether to auto-engage.
    """

    def __init__(
        self,
        *,
        broker: str,
        code: str,
        detail: str = "",
        cause: BaseException | None = None,
    ) -> None:
        self.broker = broker
        self.code = code
        self.detail = detail
        message = f"{broker} {code}: {detail}" if detail else f"{broker} {code}"
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


def _lazy_robin_stocks() -> Any:
    """Import ``robin_stocks.robinhood`` lazily; raise LiveBrokerError if missing."""

    try:
        import robin_stocks.robinhood as rh  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - dep is optional.
        raise LiveBrokerError(
            broker="ROBINHOOD",
            code="DEPENDENCY_MISSING",
            detail=(
                "The optional 'robin_stocks' library is not installed. "
                "Install the 'robinhood' extra to enable this adapter."
            ),
            cause=exc,
        ) from exc
    return rh


class RobinhoodLiveClient:
    """Async live-trading facade over ``robin_stocks``.

    The interface mirrors :class:`noosphere.equities._alpaca_client.AlpacaClient`
    for the methods the live equity engine uses: ``get_account``,
    ``place_order``, ``cancel_order``, ``get_order``, ``list_positions``. Each
    call returns the same dict shape the Alpaca client returns so that
    downstream code is broker-agnostic.

    Authentication is performed on construction by default; callers that need
    to defer login (tests, dry-run smoke checks) can pass ``authenticate=False``
    and invoke :meth:`authenticate` later.
    """

    broker_name = "ROBINHOOD"

    def __init__(
        self,
        config: RobinhoodConfig,
        *,
        authenticate: bool = True,
        _sdk: Any | None = None,
    ) -> None:
        if not config.is_configured:
            raise LiveBrokerError(
                broker="ROBINHOOD",
                code="NOT_CONFIGURED",
                detail="RobinhoodConfig is missing one or more required fields",
            )
        self._config = config
        # Allow tests to inject a fake module without touching robin_stocks.
        self._sdk: Any | None = _sdk
        self._authenticated = False
        if authenticate:
            self.authenticate()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        sdk = self._ensure_sdk()
        try:
            sdk.login(
                username=self._config.username,
                password=self._config.password,
                mfa_code=_totp_now(self._config.mfa_seed),
                expiresIn=86400,
                store_session=False,
                pickle_name=self._config.device_token,
            )
        except Exception as exc:  # pragma: no cover - SDK raises ad-hoc shapes.
            raise LiveBrokerError(
                broker="ROBINHOOD",
                code="AUTH_FAILED",
                detail=str(exc),
                cause=exc,
            ) from exc
        self._authenticated = True

    async def aclose(self) -> None:
        if not self._authenticated:
            return
        sdk = self._sdk
        if sdk is None:
            return
        try:
            await asyncio.to_thread(sdk.logout)
        except Exception as exc:  # pragma: no cover - defensive.
            log.warning("robinhood_logout_failed", error=str(exc))
        self._authenticated = False

    # ── Account / positions ──────────────────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        sdk = self._ensure_sdk()
        try:
            profile = await asyncio.to_thread(sdk.profiles.load_account_profile)
        except Exception as exc:
            raise self._wrap(exc, code="GET_ACCOUNT_FAILED")
        if not isinstance(profile, dict):
            return {}
        cash = _decimal_or_none(profile.get("cash"))
        equity = _decimal_or_none(profile.get("equity"))
        buying_power = _decimal_or_none(profile.get("buying_power"))
        return {
            "id": str(profile.get("account_number") or ""),
            "account_number": str(profile.get("account_number") or ""),
            "status": str(profile.get("state") or "").upper() or "ACTIVE",
            "currency": "USD",
            "cash": _stringify_decimal(cash),
            "equity": _stringify_decimal(equity),
            "buying_power": _stringify_decimal(buying_power),
            "raw": profile,
        }

    async def list_positions(self) -> list[dict[str, Any]]:
        sdk = self._ensure_sdk()
        try:
            rows = await asyncio.to_thread(sdk.account.get_open_stock_positions)
        except Exception as exc:
            raise self._wrap(exc, code="LIST_POSITIONS_FAILED")
        if not isinstance(rows, list):
            return []
        positions: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _resolve_symbol(sdk, row)
            qty = _decimal_or_none(row.get("quantity"))
            avg = _decimal_or_none(row.get("average_buy_price"))
            positions.append(
                {
                    "symbol": symbol,
                    "qty": _stringify_decimal(qty),
                    "avg_entry_price": _stringify_decimal(avg),
                    "side": "long",
                    "raw": row,
                }
            )
        return positions

    # ── Trading ──────────────────────────────────────────────────────────────

    async def place_order(
        self,
        *,
        symbol: str,
        qty: float | str,
        side: str,
        type: str = "market",
        time_in_force: str = "day",
        limit_price: float | str | None = None,
        stop_price: float | str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sdk = self._ensure_sdk()
        normalised_side = side.strip().lower()
        if normalised_side not in {"buy", "sell"}:
            raise LiveBrokerError(
                broker="ROBINHOOD",
                code="UNSUPPORTED_SIDE",
                detail=f"side must be 'buy' or 'sell', got {side!r}",
            )
        if type.strip().lower() != "market" and limit_price is None:
            raise LiveBrokerError(
                broker="ROBINHOOD",
                code="UNSUPPORTED_ORDER_TYPE",
                detail=(
                    "Robinhood adapter only routes market and limit orders; "
                    f"got type={type!r} without limit_price"
                ),
            )
        try:
            if limit_price is not None:
                payload = await asyncio.to_thread(
                    sdk.orders.order,
                    symbol,
                    float(qty),
                    normalised_side,
                    None,
                    float(limit_price),
                    time_in_force,
                    None,
                )
            else:
                fn = (
                    sdk.orders.order_buy_market
                    if normalised_side == "buy"
                    else sdk.orders.order_sell_market
                )
                payload = await asyncio.to_thread(
                    fn, symbol, float(qty), time_in_force
                )
        except Exception as exc:
            raise self._wrap(exc, code="PLACE_ORDER_FAILED")
        return _translate_order(payload, fallback_symbol=symbol)

    async def cancel_order(self, order_id: str) -> None:
        sdk = self._ensure_sdk()
        try:
            await asyncio.to_thread(sdk.orders.cancel_stock_order, order_id)
        except Exception as exc:
            raise self._wrap(exc, code="CANCEL_ORDER_FAILED")

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        sdk = self._ensure_sdk()
        try:
            payload = await asyncio.to_thread(sdk.orders.get_stock_order_info, order_id)
        except Exception as exc:
            raise self._wrap(exc, code="GET_ORDER_FAILED")
        if not isinstance(payload, dict) or not payload:
            return None
        return _translate_order(payload, fallback_symbol="")

    # ── Internals ────────────────────────────────────────────────────────────

    def _ensure_sdk(self) -> Any:
        if self._sdk is None:
            self._sdk = _lazy_robin_stocks()
        return self._sdk

    def _wrap(self, exc: BaseException, *, code: str) -> LiveBrokerError:
        return LiveBrokerError(
            broker="ROBINHOOD",
            code=code,
            detail=str(exc),
            cause=exc,
        )


# ── Translation helpers ──────────────────────────────────────────────────────


def _translate_order(payload: Any, *, fallback_symbol: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"id": "", "status": "rejected", "symbol": fallback_symbol}
    status = str(payload.get("state") or payload.get("status") or "").lower()
    if status == "queued" or status == "unconfirmed" or status == "confirmed":
        status = "accepted"
    elif status in {"partially_filled"}:
        status = "partially_filled"
    elif status in {"filled"}:
        status = "filled"
    elif status in {"canceled", "cancelled"}:
        status = "canceled"
    elif status in {"failed", "rejected"}:
        status = "rejected"
    filled_qty = _decimal_or_none(payload.get("cumulative_quantity"))
    filled_avg = _decimal_or_none(payload.get("average_price"))
    return {
        "id": str(payload.get("id") or ""),
        "client_order_id": str(payload.get("ref_id") or ""),
        "status": status,
        "symbol": str(payload.get("symbol") or fallback_symbol),
        "qty": _stringify_decimal(_decimal_or_none(payload.get("quantity"))),
        "filled_qty": _stringify_decimal(filled_qty),
        "filled_avg_price": _stringify_decimal(filled_avg),
        "filled_at": str(payload.get("last_transaction_at") or "") or None,
        "submitted_at": str(payload.get("created_at") or "") or None,
        "raw": payload,
    }


def _resolve_symbol(sdk: Any, row: dict[str, Any]) -> str:
    symbol = row.get("symbol")
    if isinstance(symbol, str) and symbol:
        return symbol
    instrument_url = row.get("instrument")
    if not isinstance(instrument_url, str) or not instrument_url:
        return ""
    try:
        meta = sdk.stocks.get_instrument_by_url(instrument_url)
    except Exception:
        return ""
    if isinstance(meta, dict):
        return str(meta.get("symbol") or "")
    return ""


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


def _stringify_decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _totp_now(seed: str) -> str:
    """Return a six-digit RFC 6238 TOTP code for the given base32 seed."""

    import base64
    import hashlib
    import hmac
    import struct
    import time as _time

    if not seed:
        raise LiveBrokerError(
            broker="ROBINHOOD",
            code="NO_MFA_SEED",
            detail="MFA seed is required to authenticate with Robinhood",
        )
    cleaned = seed.replace(" ", "").upper()
    padding = "=" * (-len(cleaned) % 8)
    try:
        key = base64.b32decode(cleaned + padding, casefold=True)
    except Exception as exc:
        raise LiveBrokerError(
            broker="ROBINHOOD",
            code="INVALID_MFA_SEED",
            detail=str(exc),
            cause=exc,
        ) from exc
    counter = struct.pack(">Q", int(_time.time()) // 30)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


__all__ = [
    "LiveBrokerError",
    "RobinhoodLiveClient",
]


# Re-exports so the import surface mirrors the Alpaca live-client conventions.
_UNUSED = (UTC, datetime)  # keep stdlib imports referenced if future helpers grow.
