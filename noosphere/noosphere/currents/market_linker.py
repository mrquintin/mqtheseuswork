"""Link Currents opinions to forecast-portfolio markets.

The matcher answers: for a published EventOpinion on a yes/no claim, which
mirrored Polymarket / Kalshi markets resolve on entailing or entailed-by
questions? Used by the founder portal only — public Currents must never see
the link.

Design notes:
- Matching is claim-level NLI, not keyword overlap. Two markets can both name
  "China" and be unrelated; the gate must reject those silently.
- The scorer is injected (a callable returning per-pair entailment probability)
  so tests run without loading the heavy DeBERTa NLI weights.
- Liquidity is read from ``ForecastMarket.volume`` (or the raw payload's
  ``openInterest`` if present). Below the threshold, the match is still
  surfaced as low-liquidity but downstream callers must skip position sizing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Protocol

from noosphere.models import (
    EventOpinion,
    ForecastMarket,
    ForecastMarketStatus,
    OpinionStance,
)


DEFAULT_NLI_THRESHOLD = float(os.getenv("CURRENTS_MARKET_NLI_THRESHOLD", "0.7"))
DEFAULT_CONTRADICTION_CEILING = float(
    os.getenv("CURRENTS_MARKET_CONTRADICTION_CEILING", "0.25")
)
DEFAULT_LIQUIDITY_FLOOR_USD = float(
    os.getenv("CURRENTS_MARKET_LIQUIDITY_FLOOR_USD", "5000")
)


class NLIPairScorer(Protocol):
    def __call__(self, premise: str, hypothesis: str) -> "NLIScore": ...


@dataclass(frozen=True)
class NLIScore:
    entailment: float
    contradiction: float


@dataclass(frozen=True)
class MarketMatch:
    market_id: str
    source: str
    external_id: str
    title: str
    market_yes_price: float | None
    entailment_forward: float
    entailment_reverse: float
    contradiction_max: float
    liquidity_usd: float
    low_liquidity: bool
    market_url: str | None


def _opinion_claim_text(opinion: EventOpinion) -> str:
    """Compress an EventOpinion into a single-claim string for NLI."""
    headline = (opinion.headline or "").strip()
    body = (opinion.body_markdown or "").strip()
    first_sentence = body.split(".", 1)[0].strip() if body else ""
    if first_sentence and first_sentence != headline:
        return f"{headline}. {first_sentence}".strip()
    return headline


def _market_claim_text(market: ForecastMarket) -> str:
    title = (market.title or "").strip()
    criteria = (market.resolution_criteria or "").strip()
    if criteria:
        return f"{title}. Resolution: {criteria}"
    return title


def _market_liquidity_usd(market: ForecastMarket) -> float:
    raw = market.raw_payload or {}
    for key in ("openInterest", "open_interest", "liquidity", "liquidityNum"):
        candidate = raw.get(key) if isinstance(raw, dict) else None
        if candidate is not None:
            try:
                return float(candidate)
            except (TypeError, ValueError):
                continue
    if market.volume is not None:
        try:
            return float(Decimal(market.volume))
        except (TypeError, ValueError, ArithmeticError):
            return 0.0
    return 0.0


def _market_url(market: ForecastMarket) -> str | None:
    raw = market.raw_payload or {}
    if isinstance(raw, dict):
        for key in ("url", "market_url", "marketUrl", "source_url"):
            value = raw.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    source = str(market.source.value if hasattr(market.source, "value") else market.source)
    if source == "POLYMARKET" and market.external_id:
        return f"https://polymarket.com/event/{market.external_id}"
    if source == "KALSHI" and market.external_id:
        return f"https://kalshi.com/markets/{market.external_id}"
    return None


def _market_yes_price(market: ForecastMarket) -> float | None:
    if market.current_yes_price is None:
        return None
    try:
        return float(Decimal(market.current_yes_price))
    except (TypeError, ValueError, ArithmeticError):
        return None


def is_opinion_directional(opinion: EventOpinion) -> bool:
    """An opinion offers a directional yes/no probability only when the firm
    actually picked a side. COMPLICATES and ABSTAINED do not."""
    stance = opinion.stance
    if hasattr(stance, "value"):
        stance = stance.value
    return str(stance) in {OpinionStance.AGREES.value, OpinionStance.DISAGREES.value}


def link_opinion_to_markets(
    opinion: EventOpinion,
    markets: Iterable[ForecastMarket],
    *,
    scorer: NLIPairScorer,
    threshold: float = DEFAULT_NLI_THRESHOLD,
    contradiction_ceiling: float = DEFAULT_CONTRADICTION_CEILING,
    liquidity_floor_usd: float = DEFAULT_LIQUIDITY_FLOOR_USD,
) -> list[MarketMatch]:
    """Return the markets whose claim entails or is entailed by the opinion.

    A match requires:
    - the opinion is directional (AGREES or DISAGREES);
    - the market is OPEN;
    - bidirectional NLI clears ``threshold`` in *one* direction with the
      reverse direction not contradicting.

    Markets below the liquidity floor are still returned, but with
    ``low_liquidity=True`` so the caller can suppress position sizing.
    """
    if not is_opinion_directional(opinion):
        return []

    opinion_text = _opinion_claim_text(opinion)
    if not opinion_text:
        return []

    matches: list[MarketMatch] = []
    for market in markets:
        market_status = market.status
        if hasattr(market_status, "value"):
            market_status = market_status.value
        if str(market_status) != ForecastMarketStatus.OPEN.value:
            continue

        market_text = _market_claim_text(market)
        if not market_text:
            continue

        forward = scorer(opinion_text, market_text)
        reverse = scorer(market_text, opinion_text)

        forward_entail = float(forward.entailment)
        reverse_entail = float(reverse.entailment)
        contradiction_max = max(
            float(forward.contradiction), float(reverse.contradiction)
        )

        if max(forward_entail, reverse_entail) < threshold:
            continue
        if contradiction_max > contradiction_ceiling:
            continue

        liquidity = _market_liquidity_usd(market)
        matches.append(
            MarketMatch(
                market_id=market.id,
                source=str(market.source.value if hasattr(market.source, "value") else market.source),
                external_id=market.external_id,
                title=market.title,
                market_yes_price=_market_yes_price(market),
                entailment_forward=forward_entail,
                entailment_reverse=reverse_entail,
                contradiction_max=contradiction_max,
                liquidity_usd=liquidity,
                low_liquidity=liquidity < liquidity_floor_usd,
                market_url=_market_url(market),
            )
        )
    return matches


def make_default_scorer() -> NLIPairScorer:
    """Build the production NLI-backed scorer.

    Imported lazily so unit tests don't pay the model load.
    """
    from noosphere.coherence.nli import NLIScorer

    backing = NLIScorer()

    def _score(premise: str, hypothesis: str) -> NLIScore:
        probs, _, _ = backing.score_pair(premise, hypothesis)
        return NLIScore(entailment=probs.entailment, contradiction=probs.contradiction)

    return _score
