from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from noosphere.forecasts.paper_bet_engine import (
    PaperBetConfig,
    evaluate_and_stake,
    settle_paper_bets_for_market,
)
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)
from noosphere.store import Store

NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
ORG_ID = "org_paper_bets"


def test_no_bet_below_edge_threshold() -> None:
    store = _store()
    market = _seed_market(store, yes_price=Decimal("0.500000"))
    prediction = _seed_prediction(store, market, Decimal("0.520000"))

    bet = asyncio.run(
        evaluate_and_stake(
            store,
            prediction.id,
            config=PaperBetConfig(edge_threshold=0.05),
            now=NOW,
        )
    )

    assert bet is None
    assert store.list_bets_for_prediction(prediction.id) == []


def test_bet_yes_when_model_higher() -> None:
    store = _store()
    market = _seed_market(store, yes_price=Decimal("0.550000"))
    prediction = _seed_prediction(store, market, Decimal("0.700000"))

    bet = asyncio.run(
        evaluate_and_stake(store, prediction.id, config=PaperBetConfig(), now=NOW)
    )

    assert bet is not None
    assert bet.mode == ForecastBetMode.PAPER
    assert bet.status == ForecastBetStatus.FILLED
    assert bet.side == ForecastBetSide.YES
    assert bet.entry_price == Decimal("0.550000")
    assert Decimal("1.00") <= bet.stake_usd <= Decimal("50.00")


def test_bet_no_when_model_lower() -> None:
    store = _store()
    market = _seed_market(
        store,
        yes_price=Decimal("0.550000"),
        no_price=Decimal("0.450000"),
    )
    prediction = _seed_prediction(store, market, Decimal("0.300000"))

    bet = asyncio.run(
        evaluate_and_stake(store, prediction.id, config=PaperBetConfig(), now=NOW)
    )

    assert bet is not None
    assert bet.side == ForecastBetSide.NO
    assert bet.entry_price == Decimal("0.450000")


def test_kelly_clamped_to_max_stake_ceiling() -> None:
    store = _store()
    market = _seed_market(store, yes_price=Decimal("0.500000"))
    prediction = _seed_prediction(store, market, Decimal("0.990000"))

    bet = asyncio.run(
        evaluate_and_stake(
            store,
            prediction.id,
            config=PaperBetConfig(max_stake_usd=12.34),
            now=NOW,
        )
    )

    assert bet is not None
    assert bet.stake_usd == Decimal("12.34")


def test_decrements_balance() -> None:
    store = _store()
    market = _seed_market(store, yes_price=Decimal("0.550000"))
    prediction = _seed_prediction(store, market, Decimal("0.700000"))

    bet = asyncio.run(
        evaluate_and_stake(
            store,
            prediction.id,
            config=PaperBetConfig(max_stake_usd=25.0),
            now=NOW,
        )
    )

    assert bet is not None
    assert bet.stake_usd == Decimal("25.00")
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.paper_balance_usd == Decimal("9975.00")


def test_settle_winning_bet() -> None:
    store = _store()
    market, prediction = _seed_resolvable_bet(store, outcome=ForecastOutcome.YES)

    count = asyncio.run(settle_paper_bets_for_market(store, market.id))

    assert count == 1
    bet = store.list_bets_for_prediction(prediction.id)[0]
    assert bet.status == ForecastBetStatus.SETTLED
    assert bet.exit_price == Decimal("1.000000")
    assert bet.settlement_pnl_usd == Decimal("40.91")
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.paper_balance_usd == Decimal("10040.91")


def test_settle_losing_bet() -> None:
    store = _store()
    market, prediction = _seed_resolvable_bet(store, outcome=ForecastOutcome.NO)

    count = asyncio.run(settle_paper_bets_for_market(store, market.id))

    assert count == 1
    bet = store.list_bets_for_prediction(prediction.id)[0]
    assert bet.status == ForecastBetStatus.SETTLED
    assert bet.exit_price == Decimal("0.000000")
    assert bet.settlement_pnl_usd == Decimal("-50.00")
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.paper_balance_usd == Decimal("9950.00")


def test_settle_cancelled_market() -> None:
    store = _store()
    market, prediction = _seed_resolvable_bet(store, outcome=ForecastOutcome.CANCELLED)

    count = asyncio.run(settle_paper_bets_for_market(store, market.id))

    assert count == 1
    bet = store.list_bets_for_prediction(prediction.id)[0]
    assert bet.status == ForecastBetStatus.SETTLED
    assert bet.exit_price == Decimal("0.550000")
    assert bet.settlement_pnl_usd == Decimal("0.00")
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.paper_balance_usd == Decimal("10000.00")


def test_idempotent_settlement() -> None:
    store = _store()
    market, prediction = _seed_resolvable_bet(store, outcome=ForecastOutcome.YES)

    first = asyncio.run(settle_paper_bets_for_market(store, market.id))
    second = asyncio.run(settle_paper_bets_for_market(store, market.id))

    assert first == 1
    assert second == 0
    bet = store.list_bets_for_prediction(prediction.id)[0]
    assert bet.status == ForecastBetStatus.SETTLED
    assert bet.settlement_pnl_usd == Decimal("40.91")
    state = store.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.paper_balance_usd == Decimal("10040.91")


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_market(
    store: Store,
    *,
    yes_price: Decimal,
    no_price: Decimal | None = None,
    status: ForecastMarketStatus = ForecastMarketStatus.OPEN,
    outcome: ForecastOutcome | None = None,
) -> ForecastMarket:
    market = ForecastMarket(
        id="forecast_market_paper",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="paper_market",
        title="Will the paper fixture resolve YES?",
        description="Fixture market.",
        resolution_criteria="Fixture settlement.",
        current_yes_price=yes_price,
        current_no_price=(
            no_price if no_price is not None else Decimal("1.000000") - yes_price
        ),
        open_time=NOW - timedelta(days=1),
        close_time=NOW + timedelta(days=1),
        status=status,
        resolved_outcome=outcome,
        resolved_at=NOW if outcome is not None else None,
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    return market


def _seed_prediction(
    store: Store,
    market: ForecastMarket,
    probability_yes: Decimal,
) -> ForecastPrediction:
    prediction = ForecastPrediction(
        id="forecast_prediction_paper",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=probability_yes,
        confidence_low=max(Decimal("0.000000"), probability_yes - Decimal("0.100000")),
        confidence_high=min(Decimal("1.000000"), probability_yes + Decimal("0.100000")),
        headline="Fixture paper forecast",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="fixture",
        model_name="fixture-model",
        created_at=NOW,
    )
    store.put_forecast_prediction(prediction)
    return prediction


def _seed_resolvable_bet(
    store: Store,
    *,
    outcome: ForecastOutcome,
) -> tuple[ForecastMarket, ForecastPrediction]:
    status = (
        ForecastMarketStatus.CANCELLED
        if outcome == ForecastOutcome.CANCELLED
        else ForecastMarketStatus.RESOLVED
    )
    market = _seed_market(
        store,
        yes_price=Decimal("0.550000"),
        status=status,
        outcome=outcome,
    )
    prediction = _seed_prediction(store, market, Decimal("0.700000"))
    store.set_portfolio_state(
        ForecastPortfolioState(
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("9950.00"),
            live_balance_usd=None,
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=NOW,
            updated_at=NOW,
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id="forecast_bet_paper",
            prediction_id=prediction.id,
            organization_id=ORG_ID,
            mode=ForecastBetMode.PAPER,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("50.00"),
            entry_price=Decimal("0.550000"),
            status=ForecastBetStatus.FILLED,
            created_at=NOW,
        )
    )
    return market, prediction
