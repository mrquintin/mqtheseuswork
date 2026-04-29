from __future__ import annotations

import asyncio

from current_events_api.sse import with_heartbeats


def test_with_heartbeats_keeps_source_alive_after_idle_timeout() -> None:
    async def run() -> list[bytes]:
        ready = asyncio.Event()

        async def source():
            ready.set()
            await asyncio.sleep(0.05)
            yield b"event: opinion\ndata: {}\n\n"

        frames = with_heartbeats(source(), heartbeat_seconds=0.01)
        first = await anext(frames)
        await ready.wait()
        rest: list[bytes] = []
        for _ in range(10):
            frame = await anext(frames)
            rest.append(frame)
            if frame == b"event: opinion\ndata: {}\n\n":
                break
        await frames.aclose()
        return [first, *rest]

    heartbeat, *rest = asyncio.run(run())

    assert b"event: heartbeat" in heartbeat
    assert b"event: opinion\ndata: {}\n\n" in rest
