from __future__ import annotations

import asyncio

from current_events_api.routes.forecasts_stream import stream_forecasts


def test_forecasts_stream_emits_forecast_published_after_bus_publish(client) -> None:
    async def run() -> bytes:
        response = stream_forecasts(
            bus=client.app.state.bus,
            metrics=client.app.state.metrics,
        )
        iterator = response.body_iterator.__aiter__()
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.01)
        await client.app.state.bus.publish_forecast(
            "forecast.published",
            {"id": "forecast_stream_prediction", "headline": "Published forecast"},
        )
        try:
            return await asyncio.wait_for(pending, timeout=1.0)
        finally:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()

    frame = asyncio.run(run())

    assert b"event: forecast.published" in frame
    assert b"forecast_stream_prediction" in frame


def test_forecasts_stream_never_announces_live_bets(client) -> None:
    async def run() -> bytes:
        response = stream_forecasts(
            bus=client.app.state.bus,
            metrics=client.app.state.metrics,
        )
        iterator = response.body_iterator.__aiter__()
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.01)
        await client.app.state.bus.publish_forecast(
            "bet.placed",
            {"id": "live_bet", "predictionId": "p1", "mode": "LIVE"},
        )
        await client.app.state.bus.publish_forecast(
            "bet.placed",
            {"id": "paper_bet", "predictionId": "p1", "mode": "PAPER"},
        )
        try:
            return await asyncio.wait_for(pending, timeout=1.0)
        finally:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()

    frame = asyncio.run(run())

    assert b"event: bet.placed" in frame
    assert b"paper_bet" in frame
    assert b"live_bet" not in frame
