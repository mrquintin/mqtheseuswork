"""SSE contract tests for /v1/algorithms/stream."""

from __future__ import annotations

import asyncio

from current_events_api.routes.algorithms_stream import (
    ALGORITHMS_OPERATOR_TOPIC,
    ALGORITHMS_TOPIC,
    publish_algorithm_event,
    stream_algorithms,
)


def test_algorithm_fired_frame_lands_within_one_second(client) -> None:
    async def run() -> bytes:
        response = stream_algorithms(
            bus=client.app.state.bus,
            metrics=client.app.state.metrics,
            elevated=0,
        )
        iterator = response.body_iterator.__aiter__()
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.01)
        await publish_algorithm_event(
            client.app.state.bus,
            "algorithm.fired",
            {
                "algorithmId": "algo_under_test",
                "invocationId": "inv_under_test",
                "name": "test algorithm",
            },
        )
        try:
            return await asyncio.wait_for(pending, timeout=1.0)
        finally:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()

    frame = asyncio.run(run())
    assert b"event: algorithm.fired" in frame
    assert b"inv_under_test" in frame


def test_public_stream_skips_operator_only_pause_frames(client) -> None:
    async def run() -> bytes:
        response = stream_algorithms(
            bus=client.app.state.bus,
            metrics=client.app.state.metrics,
            elevated=0,
        )
        iterator = response.body_iterator.__aiter__()
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.01)
        # Publish a paused event to the operator topic — public stream
        # must not surface it. Then publish a public event so the test
        # has something to land on.
        await client.app.state.bus.publish_topic(
            ALGORITHMS_OPERATOR_TOPIC,
            {"event": "algorithm.paused", "data": {"algorithmId": "should_not_leak"}},
        )
        await client.app.state.bus.publish_topic(
            ALGORITHMS_TOPIC,
            {
                "event": "invocation.resolved",
                "data": {"invocationId": "inv_resolved", "correctness": "CORRECT"},
            },
        )
        try:
            return await asyncio.wait_for(pending, timeout=1.0)
        finally:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()

    frame = asyncio.run(run())
    assert b"should_not_leak" not in frame
    assert b"event: invocation.resolved" in frame
