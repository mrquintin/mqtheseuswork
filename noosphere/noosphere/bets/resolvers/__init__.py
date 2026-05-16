"""Kind-specific BetSpec resolvers."""

from noosphere.bets.resolvers.advisory import resolve_advisory
from noosphere.bets.resolvers.market import resolve_market
from noosphere.bets.resolvers.scientific import (
    ScientificFeedProbe,
    resolve_scientific,
)
from noosphere.bets.resolvers.strategic import resolve_strategic

__all__ = [
    "ScientificFeedProbe",
    "resolve_advisory",
    "resolve_market",
    "resolve_scientific",
    "resolve_strategic",
]
