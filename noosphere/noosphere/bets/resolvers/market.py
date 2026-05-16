"""MARKET_BET resolver.

Reuses the existing prediction-market resolution machinery from Round
10 (``noosphere.forecasts.resolution_tracker``). The lifecycle ticker
only flips the BetSpec status; the underlying ``ForecastBet`` /
``EquityPosition`` row is the source of truth for P&L.
"""

from __future__ import annotations

from typing import Any, Optional

from noosphere.bets.spec import (
    BetOutcome,
    BetResolution,
    BetSpec,
    BetStatus,
)


def _bet_status_value(bet: Any) -> str:
    status = getattr(bet, "status", None)
    return getattr(status, "value", None) or str(status or "")


def resolve_market(
    spec: BetSpec,
    *,
    store: Any,
) -> Optional[BetResolution]:
    """Try to resolve a MARKET_BET by inspecting its linked downstream row.

    Returns ``None`` if the downstream bet hasn't settled yet — the
    lifecycle ticker will try again on the next pass. When the
    downstream row carries a P&L, that determines CORRECT vs INCORRECT.
    """

    market = spec.market_bet
    if market is None:  # pragma: no cover - validator catches this
        return None

    forecast_bet_id = market.forecast_bet_id
    equity_position_id = market.equity_position_id

    if forecast_bet_id:
        from noosphere.models import ForecastBet

        with store.session() as session:
            row = session.get(ForecastBet, forecast_bet_id)
        if row is None:
            return None
        pnl = float(row.settlement_pnl_usd) if row.settlement_pnl_usd is not None else None
        settled = _bet_status_value(row) in {"SETTLED", "CLOSED", "RESOLVED"} or (
            getattr(row, "settled_at", None) is not None
        )
        if not settled:
            return None
        outcome = BetOutcome.UNDETERMINED if pnl is None else (
            BetOutcome.CORRECT if pnl > 0 else
            BetOutcome.INCORRECT if pnl < 0 else
            BetOutcome.UNDETERMINED
        )
        return BetResolution(
            bet_spec_id=spec.id,
            outcome=outcome,
            evidence_note=f"forecast_bet={row.id} status={_bet_status_value(row)}",
            pnl_usd=pnl,
        )

    if equity_position_id:
        from noosphere.models import EquityPosition

        with store.session() as session:
            row = session.get(EquityPosition, equity_position_id)
        if row is None:
            return None
        pnl = (
            float(row.realized_pnl_usd) if row.realized_pnl_usd is not None else None
        )
        settled = _bet_status_value(row) in {"CLOSED", "SETTLED", "RESOLVED"} or (
            getattr(row, "exit_at", None) is not None
        )
        if not settled:
            return None
        outcome = BetOutcome.UNDETERMINED if pnl is None else (
            BetOutcome.CORRECT if pnl > 0 else
            BetOutcome.INCORRECT if pnl < 0 else
            BetOutcome.UNDETERMINED
        )
        return BetResolution(
            bet_spec_id=spec.id,
            outcome=outcome,
            evidence_note=(
                f"equity_position={row.id} status={_bet_status_value(row)}"
            ),
            pnl_usd=pnl,
        )

    # No downstream link yet — the bet was AUTHORIZED but the order has
    # not been placed. Lifecycle ticker leaves status as-is.
    _ = BetStatus  # quiet the linter on the imported enum
    return None
