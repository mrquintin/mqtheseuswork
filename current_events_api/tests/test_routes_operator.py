from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from current_events_api.routes.operator import compute_operator_hmac
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)

ORG_ID = "org_operator_api"
MARKET_ID = "operator_market"
PREDICTION_ID = "operator_prediction"
BET_ID = "operator_live_bet"
NOW = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)


def _json_body(body: dict[str, object]) -> bytes:
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _headers(secret: str, path: str, body: bytes) -> dict[str, str]:
    timestamp = str(time.time())
    return {
        "content-type": "application/json",
        "x-forecasts-timestamp": timestamp,
        "x-forecasts-operator": compute_operator_hmac(
            secret,
            timestamp=timestamp,
            path=path,
            body=body,
        ),
    }


def _operator_post(client, path: str, body: dict[str, object], *, secret: str = "secret"):
    raw = _json_body(body)
    return client.post(path, headers=_headers(secret, path, raw), content=raw)


def _operator_get(client, path: str, *, secret: str = "secret"):
    return client.get(path, headers=_headers(secret, path, b""))


def _configure_operator_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    live_enabled: bool = True,
    configured: bool = True,
    max_stake: str = "100",
    max_loss: str = "100",
) -> None:
    monkeypatch.setenv("FORECASTS_OPERATOR_SECRET", "secret")
    monkeypatch.setenv("FORECASTS_OPERATOR_CSRF_TOKEN", "csrf")
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true" if live_enabled else "false")
    monkeypatch.setenv("FORECASTS_MAX_STAKE_USD", max_stake)
    monkeypatch.setenv("FORECASTS_MAX_DAILY_LOSS_USD", max_loss)
    monkeypatch.setenv("FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S", "0")
    if configured:
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "1" * 64)
    else:
        monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)


def seed_operator_live_bet(
    store,
    *,
    prediction_authorized: bool = True,
    bet_status: ForecastBetStatus = ForecastBetStatus.AUTHORIZED,
    stake: Decimal = Decimal("10.00"),
    live_balance: Decimal = Decimal("1000.00"),
    daily_loss: Decimal = Decimal("0.00"),
    kill_switch: bool = False,
    external_order_id: str | None = "operator-external-order",
) -> None:
    market = ForecastMarket(
        id=MARKET_ID,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="operator_market_external",
        title="Operator fixture market",
        current_yes_price=Decimal("0.500000"),
        current_no_price=Decimal("0.500000"),
        raw_payload={"outcomes": ["Yes", "No"], "clobTokenIds": ["yes", "no"]},
    )
    store.put_forecast_market(market)
    store.put_forecast_prediction(
        ForecastPrediction(
            id=PREDICTION_ID,
            market_id=MARKET_ID,
            organization_id=ORG_ID,
            probability_yes=Decimal("0.700000"),
            confidence_low=Decimal("0.600000"),
            confidence_high=Decimal("0.800000"),
            headline="Operator fixture forecast",
            reasoning="Fixture reasoning.",
            status=ForecastPredictionStatus.PUBLISHED,
            topic_hint="operator",
            model_name="fixture-model",
            live_authorized_at=NOW if prediction_authorized else None,
            live_authorized_by="operator_1" if prediction_authorized else None,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.set_portfolio_state(
        ForecastPortfolioState(
            id="operator_portfolio",
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10000.00"),
            live_balance_usd=live_balance,
            daily_loss_usd=daily_loss,
            daily_loss_reset_at=NOW,
            kill_switch_engaged=kill_switch,
            kill_switch_reason="OPERATOR" if kill_switch else None,
            updated_at=NOW,
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id=BET_ID,
            prediction_id=PREDICTION_ID,
            organization_id=ORG_ID,
            mode=ForecastBetMode.LIVE,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=stake,
            entry_price=Decimal("0.500000"),
            status=bet_status,
            external_order_id=external_order_id,
            client_order_id="operator-client-order",
            live_authorized_at=NOW,
            confirmed_at=NOW if bet_status == ForecastBetStatus.CONFIRMED else None,
            created_at=NOW,
        )
    )
    store.put_forecast_bet(
        ForecastBet(
            id="operator_paper_bet",
            prediction_id=PREDICTION_ID,
            organization_id=ORG_ID,
            mode=ForecastBetMode.PAPER,
            exchange=ForecastExchange.POLYMARKET,
            side=ForecastBetSide.YES,
            stake_usd=Decimal("100.00"),
            entry_price=Decimal("0.500000"),
            status=ForecastBetStatus.FILLED,
            created_at=NOW,
        )
    )


def test_operator_auth_rejects_missing_and_wrong_hmac_then_accepts_valid(client, monkeypatch) -> None:
    _configure_operator_env(monkeypatch)
    seed_operator_live_bet(client.app.state.store, prediction_authorized=False)
    path = f"/v1/operator/forecasts/{PREDICTION_ID}/authorize-live"
    body = {"operator_id": "operator_1", "csrf_token": "csrf"}

    missing = client.post(path, json=body)
    wrong = _operator_post(client, path, body, secret="wrong")
    valid = _operator_post(client, path, body)

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["live_authorized_at"] is not None


@pytest.mark.parametrize(
    ("gate_code", "env_kwargs", "seed_kwargs"),
    [
        ("DISABLED", {"live_enabled": False}, {}),
        ("NOT_CONFIGURED", {"configured": False}, {}),
        ("NOT_AUTHORIZED", {}, {"prediction_authorized": False}),
        ("NOT_CONFIRMED", {}, {"bet_status": ForecastBetStatus.PENDING}),
        ("STAKE_OVER_CEILING", {"max_stake": "5"}, {"stake": Decimal("10.00")}),
        ("DAILY_LOSS_OVER_CEILING", {"max_loss": "100"}, {"daily_loss": Decimal("101.00")}),
        ("KILL_SWITCH_ENGAGED", {}, {"kill_switch": True}),
        ("INSUFFICIENT_BALANCE", {}, {"live_balance": Decimal("5.00")}),
    ],
)
def test_confirm_live_bet_returns_gate_failure_codes(
    client,
    monkeypatch,
    gate_code,
    env_kwargs,
    seed_kwargs,
) -> None:
    _configure_operator_env(monkeypatch, **env_kwargs)
    seed_operator_live_bet(client.app.state.store, **seed_kwargs)
    path = f"/v1/operator/forecasts/{PREDICTION_ID}/bets/{BET_ID}/confirm"

    response = _operator_post(
        client,
        path,
        {"operator_id": "operator_1", "csrf_token": "csrf"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["gate_code"] == gate_code


def test_operator_live_bets_include_live_order_fields_public_bets_do_not(client, monkeypatch) -> None:
    _configure_operator_env(monkeypatch)
    seed_operator_live_bet(client.app.state.store)

    operator_response = _operator_get(client, "/v1/operator/live-bets")
    public_response = client.get(f"/v1/forecasts/{PREDICTION_ID}/bets")

    assert operator_response.status_code == 200
    live_item = operator_response.json()["items"][0]
    assert live_item["mode"] == "LIVE"
    assert live_item["external_order_id"] == "operator-external-order"
    assert public_response.status_code == 200
    assert [item["id"] for item in public_response.json()] == ["operator_paper_bet"]
    assert "external_order_id" not in str(public_response.json())


def test_operator_kill_switch_routes_require_csrf_and_long_disengage_note(client, monkeypatch) -> None:
    _configure_operator_env(monkeypatch)
    seed_operator_live_bet(client.app.state.store)

    engage_path = "/v1/operator/kill-switch/engage"
    bad_csrf = _operator_post(
        client,
        engage_path,
        {"operator_id": "operator_1", "reason": "OPERATOR", "note": "manual", "csrf_token": "wrong"},
    )
    engaged = _operator_post(
        client,
        engage_path,
        {"operator_id": "operator_1", "reason": "OPERATOR", "note": "manual", "csrf_token": "csrf"},
    )
    disengage_path = "/v1/operator/kill-switch/disengage"
    disengaged = _operator_post(
        client,
        disengage_path,
        {
            "operator_id": "operator_1",
            "note": "Reviewed the incident and cleared live risk.",
            "csrf_token": "csrf",
        },
    )

    assert bad_csrf.status_code == 403
    assert engaged.status_code == 200
    assert engaged.json()["kill_switch_engaged"] is True
    assert disengaged.status_code == 200
    assert disengaged.json()["kill_switch_engaged"] is False


def test_operator_can_cancel_authorized_live_bet_before_submission(client, monkeypatch) -> None:
    _configure_operator_env(monkeypatch)
    seed_operator_live_bet(client.app.state.store, external_order_id=None)
    path = f"/v1/operator/forecasts/{PREDICTION_ID}/bets/{BET_ID}/cancel"

    response = _operator_post(
        client,
        path,
        {"operator_id": "operator_1", "csrf_token": "csrf"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
