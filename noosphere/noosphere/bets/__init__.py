"""Polymorphic bet abstraction (Round 19 prompt 15).

A ``BetSpec`` is a structured claim about a future state of the world
with a defined resolution criterion and (optionally) a financial stake.
Four kinds are modelled today:

* ``MARKET_BET`` — wraps a ``ForecastBet`` (prediction markets) or an
  ``EquityPosition`` (equities). The eight-gate live-trading safety
  contract applies *only* to this kind.
* ``ADVISORY_BET`` — a public non-financial commitment of position
  (a publicly stated thesis). Operator-only resolution.
* ``STRATEGIC_BET`` — internal commitment of firm resources (founder
  time, hiring direction, partnership pursuit). Operator-only
  resolution.
* ``SCIENTIFIC_BET`` — a falsifiable prediction about the world that
  doesn't map to a market. Resolves against named external data feeds
  (BLS, FRED, World Bank, etc.).

The agent is never permitted to resolve ADVISORY or STRATEGIC bets
unilaterally — both require explicit operator judgment.
"""

from noosphere.bets.spec import (
    AdvisoryAudience,
    AdvisoryBetSpec,
    BetKind,
    BetOutcome,
    BetResolution,
    BetSpec,
    BetStatus,
    MarketBetExchange,
    MarketBetSpec,
    ScientificBetSpec,
    StrategicBetSpec,
    StrategicResourceKind,
    bet_spec_from_implied_bet,
)

__all__ = [
    "AdvisoryAudience",
    "AdvisoryBetSpec",
    "BetKind",
    "BetOutcome",
    "BetResolution",
    "BetSpec",
    "BetStatus",
    "MarketBetExchange",
    "MarketBetSpec",
    "ScientificBetSpec",
    "StrategicBetSpec",
    "StrategicResourceKind",
    "bet_spec_from_implied_bet",
]
