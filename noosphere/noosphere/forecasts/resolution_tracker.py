"""External Forecasts resolution polling and calibration scoring."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Literal

from sqlmodel import select

from noosphere.forecasts.paper_bet_engine import settle_paper_bets_for_market
from noosphere.forecasts._kalshi_client import KalshiClient
from noosphere.forecasts._polymarket_client import PolymarketGammaClient
from noosphere.forecasts.config import KalshiConfig, PolymarketConfig
from noosphere.models import (
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastResolution,
    ForecastSource,
)
from noosphere.observability import get_logger


ResolutionOutcome = Literal["YES", "NO", "CANCELLED", "STILL_OPEN"]
SCORE_WINDOW = timedelta(days=90)
LOG_LOSS_EPSILON = 1e-6
DEFAULT_PAPER_BALANCE = Decimal("10000.00")
log = get_logger(__name__)


@dataclass
class ResolutionResult:
    market_id: str
    outcome: ResolutionOutcome
    resolved_predictions: int
    skipped_predictions: int
    errors: list[str]


@dataclass(frozen=True)
class _MarketSettlement:
    outcome: ResolutionOutcome
    resolved_at: datetime | None
    raw: dict[str, Any] | None


async def poll_market(
    store: Any,
    market_id: str,
    *,
    polymarket_client: Any | None = None,
    kalshi_client: Any | None = None,
) -> ResolutionResult:
    """
    Fetch external market state and append ForecastResolution rows when terminal.

    A second poll of the same resolved market is idempotent because
    Store.put_forecast_resolution is append-only by prediction_id and returns
    the existing row id on duplicates.
    """

    errors: list[str] = []
    market = store.get_forecast_market(market_id)
    if market is None:
        return ResolutionResult(
            market_id=market_id,
            outcome="STILL_OPEN",
            resolved_predictions=0,
            skipped_predictions=0,
            errors=[f"unknown forecast market {market_id}"],
        )

    close_clients: list[Any] = []
    try:
        settlement = await _fetch_settlement(
            market,
            polymarket_client=polymarket_client,
            kalshi_client=kalshi_client,
            close_clients=close_clients,
        )
    except Exception as exc:
        log.warning(
            "forecast_resolution_poll_failed",
            market_id=market.id,
            source=_enum_value(market.source),
            external_id=market.external_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return ResolutionResult(
            market_id=market.id,
            outcome="STILL_OPEN",
            resolved_predictions=0,
            skipped_predictions=0,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    finally:
        for client in close_clients:
            await client.aclose()

    if settlement.outcome == "STILL_OPEN":
        log.info(
            "forecast_resolution_still_open",
            market_id=market.id,
            source=_enum_value(market.source),
            external_id=market.external_id,
        )
        return ResolutionResult(
            market_id=market.id,
            outcome="STILL_OPEN",
            resolved_predictions=0,
            skipped_predictions=0,
            errors=[],
        )

    resolved_at = settlement.resolved_at or _utcnow()
    _mark_market_terminal(store, market, settlement.outcome, resolved_at, settlement.raw)

    predictions = store.get_unresolved_predictions_for_market(market.id)
    resolved_predictions = 0
    skipped_predictions = 0
    for prediction in predictions:
        try:
            resolution = _resolution_for_prediction(
                prediction,
                settlement=settlement,
                resolved_at=resolved_at,
            )
        except ValueError as exc:
            skipped_predictions += 1
            errors.append(f"prediction:{prediction.id}:{exc}")
            continue

        existing = store.get_forecast_resolution(prediction.id)
        existing_id = existing.id if existing is not None else None
        written_id = store.put_forecast_resolution(resolution)
        if existing_id is not None or written_id != resolution.id:
            skipped_predictions += 1
            continue

        resolved_predictions += 1
        if resolution.brier_score is not None and resolution.log_loss is not None:
            _recompute_portfolio_calibration(
                store,
                prediction.organization_id,
                as_of=resolved_at,
            )
        log.info(
            "forecast_resolution_written",
            market_id=market.id,
            prediction_id=prediction.id,
            outcome=settlement.outcome,
            brier_score=resolution.brier_score,
            log_loss=resolution.log_loss,
            calibration_bucket=(
                str(resolution.calibration_bucket)
                if resolution.calibration_bucket is not None
                else None
            ),
        )

    await settle_paper_bets_for_market(store, market.id)

    return ResolutionResult(
        market_id=market.id,
        outcome=settlement.outcome,
        resolved_predictions=resolved_predictions,
        skipped_predictions=skipped_predictions,
        errors=errors,
    )


async def poll_all_open(
    store: Any,
    *,
    polymarket_client: Any | None = None,
    kalshi_client: Any | None = None,
) -> list[ResolutionResult]:
    """Iterate all OPEN ForecastMarket rows and poll each with concurrency 4."""

    markets = store.list_open_forecast_markets(limit=10_000)
    sem = asyncio.Semaphore(4)

    async def _run(market: ForecastMarket) -> ResolutionResult:
        async with sem:
            return await poll_market(
                store,
                market.id,
                polymarket_client=polymarket_client,
                kalshi_client=kalshi_client,
            )

    return await asyncio.gather(*[_run(market) for market in markets])


def brier_score(probability_yes: Decimal | float, outcome: Literal["YES", "NO"]) -> float:
    """Brier score: (probability_yes - actual)^2, with actual YES=1, NO=0."""

    p = float(probability_yes)
    actual = 1.0 if outcome == "YES" else 0.0
    return (p - actual) ** 2


def log_loss(probability_yes: Decimal | float, outcome: Literal["YES", "NO"]) -> float:
    """Binary log loss with p clamped to [1e-6, 1 - 1e-6]."""

    p = min(max(float(probability_yes), LOG_LOSS_EPSILON), 1.0 - LOG_LOSS_EPSILON)
    actual = 1.0 if outcome == "YES" else 0.0
    return -actual * math.log(p) - (1.0 - actual) * math.log(1.0 - p)


def calibration_bucket(probability_yes: Decimal | float) -> Decimal:
    """Floor probability_yes to the nearest lower tenth: 0.73 -> Decimal('0.7')."""

    p = _decimal_probability(probability_yes)
    return (p * Decimal("10")).to_integral_value(rounding=ROUND_FLOOR) / Decimal("10")


def _resolution_for_prediction(
    prediction: ForecastPrediction,
    *,
    settlement: _MarketSettlement,
    resolved_at: datetime,
) -> ForecastResolution:
    if settlement.outcome == "CANCELLED":
        return ForecastResolution(
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.CANCELLED,
            brier_score=None,
            log_loss=None,
            calibration_bucket=None,
            resolved_at=resolved_at,
            justification="External market was cancelled; prediction is excluded from calibration aggregates.",
            raw_settlement=settlement.raw,
        )

    if settlement.outcome not in {"YES", "NO"}:
        raise ValueError(f"cannot score outcome {settlement.outcome}")
    if prediction.probability_yes is None:
        raise ValueError("published prediction has null probability_yes")

    p = _decimal_probability(prediction.probability_yes)
    if p < Decimal("0") or p > Decimal("1"):
        raise ValueError(f"probability_yes out of range: {prediction.probability_yes}")

    outcome = "YES" if settlement.outcome == "YES" else "NO"
    return ForecastResolution(
        prediction_id=prediction.id,
        market_outcome=ForecastOutcome(outcome),
        brier_score=brier_score(p, outcome),
        log_loss=log_loss(p, outcome),
        calibration_bucket=calibration_bucket(p),
        resolved_at=resolved_at,
        justification=f"External market resolved {outcome}.",
        raw_settlement=settlement.raw,
    )


async def _fetch_settlement(
    market: ForecastMarket,
    *,
    polymarket_client: Any | None,
    kalshi_client: Any | None,
    close_clients: list[Any],
) -> _MarketSettlement:
    source = _enum_value(market.source)
    if source == ForecastSource.POLYMARKET.value:
        client = polymarket_client
        if client is None:
            cfg = PolymarketConfig.from_env()
            client = PolymarketGammaClient(
                base=cfg.gamma_base,
                timeout_s=cfg.request_timeout_s,
            )
            close_clients.append(client)
        payload = await client.get_market(market.external_id)
        return _parse_polymarket_settlement(payload)

    if source == ForecastSource.KALSHI.value:
        client = kalshi_client
        if client is None:
            cfg = KalshiConfig.from_env()
            if not cfg.is_configured:
                raise RuntimeError("KALSHI_NOT_CONFIGURED")
            client = KalshiClient(
                base=cfg.api_base,
                key_id=cfg.api_key_id,
                private_key_pem=cfg.api_private_key_pem,
                timeout_s=cfg.request_timeout_s,
            )
            close_clients.append(client)
        payload = await client.get_market(market.external_id)
        return _parse_kalshi_settlement(payload)

    raise ValueError(f"unsupported forecast source {source}")


def _parse_polymarket_settlement(payload: dict[str, Any] | None) -> _MarketSettlement:
    if not payload:
        return _MarketSettlement("STILL_OPEN", None, payload)
    raw = _json_safe(payload)
    direct = _direct_outcome(payload)
    if direct is not None:
        return _MarketSettlement(direct, _resolved_at(payload), raw)

    if _cancelled(payload):
        return _MarketSettlement("CANCELLED", _resolved_at(payload), raw)

    price_outcome = _outcome_from_winner_flags(payload) or _outcome_from_final_prices(payload)
    if price_outcome is not None:
        return _MarketSettlement(price_outcome, _resolved_at(payload), raw)

    if _openish(payload):
        return _MarketSettlement("STILL_OPEN", None, raw)
    return _MarketSettlement("STILL_OPEN", None, raw)


def _parse_kalshi_settlement(payload: dict[str, Any] | None) -> _MarketSettlement:
    if not payload:
        return _MarketSettlement("STILL_OPEN", None, payload)
    raw = _json_safe(payload)
    direct = _direct_outcome(payload)
    if direct is not None:
        return _MarketSettlement(direct, _resolved_at(payload), raw)

    if _cancelled(payload):
        return _MarketSettlement("CANCELLED", _resolved_at(payload), raw)

    status = _lower(payload.get("status") or payload.get("market_status"))
    if status in {"settled", "resolved", "finalized", "final", "determined"}:
        price_outcome = _outcome_from_final_prices(payload)
        if price_outcome is not None:
            return _MarketSettlement(price_outcome, _resolved_at(payload), raw)

    return _MarketSettlement("STILL_OPEN", None, raw)


def _direct_outcome(payload: dict[str, Any]) -> ResolutionOutcome | None:
    for key in (
        "resolvedOutcome",
        "resolved_outcome",
        "resolutionOutcome",
        "resolution_outcome",
        "winningOutcome",
        "winning_outcome",
        "winning_outcome_name",
        "winner",
        "result",
        "settlement",
        "settlement_value",
        "market_result",
        "outcome",
    ):
        parsed = _parse_outcome_value(payload.get(key))
        if parsed is not None:
            return parsed

    nested = payload.get("market")
    if isinstance(nested, dict):
        return _direct_outcome(nested)
    return None


def _parse_outcome_value(value: Any) -> ResolutionOutcome | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        if Decimal(str(value)) == Decimal("1"):
            return "YES"
        if Decimal(str(value)) == Decimal("0"):
            return "NO"
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"yes", "y", "true", "1", "resolved_yes", "yes_win", "yes wins"}:
        return "YES"
    if text in {"no", "n", "false", "0", "resolved_no", "no_win", "no wins"}:
        return "NO"
    if text in {
        "cancelled",
        "canceled",
        "void",
        "voided",
        "withdrawn",
        "annulled",
        "ambiguous",
        "no contest",
    }:
        return "CANCELLED"
    return None


def _cancelled(payload: dict[str, Any]) -> bool:
    for key in ("cancelled", "canceled", "voided", "annulled"):
        if _as_bool(payload.get(key)):
            return True
    status = _lower(payload.get("status") or payload.get("market_status"))
    return status in {"cancelled", "canceled", "voided", "void", "withdrawn", "annulled"}


def _openish(payload: dict[str, Any]) -> bool:
    if _as_bool(payload.get("active")):
        return True
    if _as_bool(payload.get("closed")):
        return False
    status = _lower(payload.get("status") or payload.get("market_status"))
    return status in {"", "open", "active", "trading", "pending_settlement"}


def _outcome_from_winner_flags(payload: dict[str, Any]) -> ResolutionOutcome | None:
    outcomes = _parse_payload_array(payload.get("outcomes") or payload.get("outcome"))
    for item in outcomes:
        if not isinstance(item, dict):
            continue
        if not _as_bool(item.get("winner") or item.get("winning") or item.get("won")):
            continue
        parsed = _parse_outcome_value(
            item.get("name") or item.get("label") or item.get("outcome")
        )
        if parsed in {"YES", "NO"}:
            return parsed
    return None


def _outcome_from_final_prices(payload: dict[str, Any]) -> ResolutionOutcome | None:
    yes_price, no_price = _terminal_prices(payload)
    if yes_price is None and no_price is None:
        return None
    if yes_price is not None and yes_price >= Decimal("0.999"):
        return "YES"
    if no_price is not None and no_price >= Decimal("0.999"):
        return "NO"
    return None


def _terminal_prices(payload: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    outcomes = _parse_payload_array(payload.get("outcomes") or payload.get("outcome"))
    prices = _parse_payload_array(
        payload.get("outcomePrices")
        or payload.get("outcome_prices")
        or payload.get("prices")
    )
    if outcomes and prices:
        for outcome, price in zip(outcomes, prices, strict=False):
            label = _outcome_label(outcome).lower()
            value = _decimal_or_none(price)
            if label == "yes":
                yes_price = value
            elif label == "no":
                no_price = value

    for item in outcomes:
        if not isinstance(item, dict):
            continue
        label = _outcome_label(item).lower()
        value = _decimal_or_none(
            item.get("price")
            or item.get("finalPrice")
            or item.get("final_price")
            or item.get("settlementPrice")
            or item.get("settlement_price")
        )
        if label == "yes" and value is not None:
            yes_price = value
        elif label == "no" and value is not None:
            no_price = value

    if yes_price is None:
        yes_price = _decimal_or_none(
            payload.get("yes_price")
            or payload.get("yesPrice")
            or payload.get("yes_ask")
            or payload.get("yes_bid")
        )
    if no_price is None:
        no_price = _decimal_or_none(
            payload.get("no_price")
            or payload.get("noPrice")
            or payload.get("no_ask")
            or payload.get("no_bid")
        )
    if yes_price is not None and yes_price > Decimal("1"):
        yes_price = yes_price / Decimal("100")
    if no_price is not None and no_price > Decimal("1"):
        no_price = no_price / Decimal("100")
    return yes_price, no_price


def _mark_market_terminal(
    store: Any,
    market: ForecastMarket,
    outcome: ResolutionOutcome,
    resolved_at: datetime,
    raw: dict[str, Any] | None,
) -> None:
    status = (
        ForecastMarketStatus.CANCELLED
        if outcome == "CANCELLED"
        else ForecastMarketStatus.RESOLVED
    )
    resolved_outcome = None if outcome == "STILL_OPEN" else ForecastOutcome(outcome)
    updated = market.model_copy(
        update={
            "status": status,
            "resolved_at": resolved_at,
            "resolved_outcome": resolved_outcome,
            "raw_payload": raw or market.raw_payload,
        }
    )
    store.put_forecast_market(updated)


def _recompute_portfolio_calibration(
    store: Any,
    organization_id: str,
    *,
    as_of: datetime | None = None,
) -> None:
    now = _aware_utc(as_of or _utcnow())
    cutoff = now - SCORE_WINDOW
    with store.session() as session:
        rows = list(
            session.exec(
                select(ForecastResolution, ForecastPrediction)
                .join(
                    ForecastPrediction,
                    ForecastPrediction.id == ForecastResolution.prediction_id,
                )
                .where(ForecastPrediction.organization_id == organization_id)
                .where(ForecastResolution.brier_score.is_not(None))
                .where(ForecastResolution.log_loss.is_not(None))
            ).all()
        )
        all_scored = [resolution for resolution, _prediction in rows]
        scored = [
            resolution
            for resolution in all_scored
            if _aware_utc(resolution.resolved_at) >= cutoff
        ]
        mean_brier = (
            sum(float(row.brier_score) for row in scored if row.brier_score is not None)
            / len(scored)
            if scored
            else None
        )
        mean_log = (
            sum(float(row.log_loss) for row in scored if row.log_loss is not None)
            / len(scored)
            if scored
            else None
        )

    state = store.get_portfolio_state(organization_id)
    updates = {
        "mean_brier_90d": mean_brier,
        "mean_log_loss_90d": mean_log,
        "updated_at": now,
    }
    if "total_resolved" in ForecastPortfolioState.model_fields:
        updates["total_resolved"] = len(all_scored)
    if state is None:
        state = ForecastPortfolioState(
            organization_id=organization_id,
            paper_balance_usd=DEFAULT_PAPER_BALANCE,
            live_balance_usd=None,
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=now,
            kill_switch_engaged=False,
            kill_switch_reason=None,
            **updates,
        )
    else:
        state = ForecastPortfolioState(
            id=state.id,
            organization_id=state.organization_id,
            paper_balance_usd=state.paper_balance_usd,
            live_balance_usd=state.live_balance_usd,
            daily_loss_usd=state.daily_loss_usd,
            daily_loss_reset_at=state.daily_loss_reset_at,
            kill_switch_engaged=state.kill_switch_engaged,
            kill_switch_reason=state.kill_switch_reason,
            total_resolved=int(updates.get("total_resolved", state.total_resolved)),
            mean_brier_90d=mean_brier,
            mean_log_loss_90d=mean_log,
            updated_at=now,
        )

    store.set_portfolio_state(state)


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
                import json

                parsed = json.loads(stripped)
            except ValueError:
                return []
            return parsed if isinstance(parsed, list) else []
        return [stripped]
    return []


def _outcome_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("label")
            or value.get("outcome")
            or ""
        )
    return str(value)


def _resolved_at(payload: dict[str, Any]) -> datetime | None:
    for key in (
        "resolvedAt",
        "resolved_at",
        "resolutionTime",
        "resolution_time",
        "settled_at",
        "settledAt",
        "closedTime",
        "closed_time",
        "closeTime",
        "close_time",
        "endDate",
        "endDateIso",
    ):
        parsed = _parse_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return _aware_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _decimal_probability(value: Decimal | float) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid probability_yes: {value}") from exc


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _lower(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(payload, default=str))
