"""Edge calculator for Currents <-> Forecast linkage.

Given a directional EventOpinion and a matched market, compute the gap
between the firm's stated probability and the market's mid-price. When the
gap clears the configured threshold, the founder portal surfaces it; below
threshold we still return the report but mark ``surface=False`` so the
caller can log without showing it.

Position sizing reuses the paper-betting engine's quarter-Kelly logic so the
founder workspace link can pre-fill a stake suggestion. The actual paper
budget guard (``forecasts/budget.py``) is not consumed here — sizing is just
advisory; the founder must explicitly confirm any position.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from noosphere.forecasts.paper_bet_engine import (
    PaperBetConfig,
    _decimal_from_float,
    _money,
    _stake_usd,
)
from noosphere.models import EventOpinion, OpinionStance


if TYPE_CHECKING:
    from noosphere.currents.market_linker import MarketMatch


@dataclass(frozen=True)
class EdgeReport:
    """One opinion ↔ one matched market.

    ``surface`` is the founder-portal gate: True iff |edge| ≥ threshold.
    ``suggested_stake_usd`` is None whenever liquidity is too thin to bet.
    """

    market_id: str
    source: str
    external_id: str
    title: str
    firm_yes_probability: float
    market_yes_price: float
    edge_pts: float
    side: str  # "YES" or "NO"
    surface: bool
    low_liquidity: bool
    suggested_stake_usd: float | None
    market_url: str | None
    threshold: float


def firm_yes_probability(opinion: EventOpinion) -> float | None:
    """Project an EventOpinion onto a probability that the underlying yes/no
    claim resolves YES.

    AGREES → confidence (the firm is confident the post's claim is true).
    DISAGREES → 1 − confidence.
    COMPLICATES / ABSTAINED → None (no directional probability).
    """
    stance = opinion.stance
    if hasattr(stance, "value"):
        stance = stance.value
    confidence = float(opinion.confidence or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    if str(stance) == OpinionStance.AGREES.value:
        return confidence
    if str(stance) == OpinionStance.DISAGREES.value:
        return 1.0 - confidence
    return None


def compute_edge(
    opinion: EventOpinion,
    match: "MarketMatch",
    *,
    config: PaperBetConfig | None = None,
    paper_balance_usd: float | None = None,
) -> EdgeReport | None:
    """Compute the firm-vs-market edge for one opinion/market pair.

    Returns ``None`` when the inputs are too thin to compute an edge
    (non-directional opinion, missing market price, etc.). The caller logs
    or skips depending on context.
    """
    config = config or PaperBetConfig.from_env()
    firm_p = firm_yes_probability(opinion)
    if firm_p is None:
        return None
    if match.market_yes_price is None:
        return None

    market_p = float(match.market_yes_price)
    if not 0.0 < market_p < 1.0:
        return None

    edge = firm_p - market_p
    edge_pts = round(edge * 100.0, 1)
    side = "YES" if edge >= 0 else "NO"
    threshold = float(config.edge_threshold)
    surface = abs(edge) >= threshold

    suggested_stake = _suggest_stake_usd(
        firm_p=firm_p,
        market_p=market_p,
        side=side,
        config=config,
        paper_balance_usd=paper_balance_usd,
        low_liquidity=match.low_liquidity,
    )

    return EdgeReport(
        market_id=match.market_id,
        source=match.source,
        external_id=match.external_id,
        title=match.title,
        firm_yes_probability=firm_p,
        market_yes_price=market_p,
        edge_pts=edge_pts,
        side=side,
        surface=surface,
        low_liquidity=match.low_liquidity,
        suggested_stake_usd=suggested_stake,
        market_url=match.market_url,
        threshold=threshold,
    )


def _suggest_stake_usd(
    *,
    firm_p: float,
    market_p: float,
    side: str,
    config: PaperBetConfig,
    paper_balance_usd: float | None,
    low_liquidity: bool,
) -> float | None:
    """Mirror ``paper_bet_engine._stake_usd`` for the advisory link.

    Returns None when the market is below the liquidity floor — the founder
    UI surfaces the edge but withholds size, per the prompt contract.
    """
    if low_liquidity:
        return None
    if paper_balance_usd is None:
        paper_balance_usd = float(config.initial_balance_usd)
    if paper_balance_usd <= 0:
        return None

    if side == "YES":
        side_prob = Decimal(str(firm_p))
        side_price = Decimal(str(market_p))
    else:
        side_prob = Decimal(str(1.0 - firm_p))
        side_price = Decimal(str(1.0 - market_p))

    if not (Decimal("0") < side_price < Decimal("1")):
        return None

    stake = _stake_usd(
        model_probability=side_prob,
        market_price=side_price,
        paper_balance=_money(_decimal_from_float(paper_balance_usd)),
        config=config,
    )
    if stake < Decimal("1.00"):
        return None
    return float(stake)


def edge_report_to_wire(report: EdgeReport) -> dict:
    """Stable JSON shape consumed by the founder UI."""
    return {
        "market_id": report.market_id,
        "source": report.source,
        "external_id": report.external_id,
        "title": report.title,
        "firm_yes_probability": report.firm_yes_probability,
        "market_yes_price": report.market_yes_price,
        "edge_pts": report.edge_pts,
        "side": report.side,
        "surface": report.surface,
        "low_liquidity": report.low_liquidity,
        "suggested_stake_usd": report.suggested_stake_usd,
        "market_url": report.market_url,
        "threshold": report.threshold,
    }
