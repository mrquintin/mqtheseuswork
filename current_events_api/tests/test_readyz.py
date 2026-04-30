from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noosphere.currents.status import write_status as write_currents_status
from noosphere.forecasts.status import write_status as write_forecasts_status


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_currents_fresh() -> None:
    write_currents_status({"cycle_id": "readyz_test", "errors": []})


def _forecast_payload(
    *,
    last_ingest: datetime,
    kill_switch_engaged: bool = False,
) -> dict[str, object]:
    return {
        "ts": _iso(datetime.now(timezone.utc)),
        "kill_switch_engaged": kill_switch_engaged,
        "kill_switch_reason": "OPERATOR" if kill_switch_engaged else None,
        "last_ingest_ts": _iso(last_ingest),
        "last_generate_ts": _iso(last_ingest),
        "last_resolve_ts": _iso(last_ingest),
        "paper_balance_usd": 9876.42,
        "live_balance_usd": 0.0,
        "live_trading_enabled": False,
        "open_markets": 47,
        "predictions_this_hour": 6,
    }


def test_readyz_reports_fresh_forecasts_status(client) -> None:
    now = datetime.now(timezone.utc)
    _write_currents_fresh()
    write_forecasts_status(_forecast_payload(last_ingest=now))

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["scheduler"] == "fresh"
    assert body["forecasts"]["state"] == "fresh"
    assert body["forecasts"]["status"]["open_markets"] == 47


def test_readyz_fails_when_forecasts_ingest_is_stuck(client, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("FORECASTS_INGEST_INTERVAL_S", "1")
    _write_currents_fresh()
    write_forecasts_status(_forecast_payload(last_ingest=now - timedelta(seconds=3)))

    response = client.get("/readyz")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["forecasts"]["code"] == "forecasts_ingest_stuck"
    assert detail["forecasts"]["stuck_after_seconds"] == 2.0


def test_readyz_fails_when_forecasts_kill_switch_is_engaged(client) -> None:
    now = datetime.now(timezone.utc)
    _write_currents_fresh()
    write_forecasts_status(
        _forecast_payload(last_ingest=now, kill_switch_engaged=True)
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["forecasts"]["code"] == "forecasts_kill_switch_engaged"
    assert detail["forecasts"]["reason"] == "OPERATOR"
