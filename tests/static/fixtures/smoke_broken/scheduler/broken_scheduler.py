"""A fake scheduler module whose tick raises.

The smoke-harness self-test for ``scheduler_tick`` monkey-patches the
real ``run_once`` with the one defined here and asserts the section
reports a failing tick. The fixture exists to encode the regression
class — "tick raises, harness must catch it" — so the test stays
honest even if the production scheduler refactors.
"""
from __future__ import annotations


_LOOP_NAMES = ("smoke_broken_loop",)


class SchedulerConfig:
    def __init__(self, **_kwargs) -> None:
        pass


async def run_once(_store, *, config, loops=None):  # noqa: ARG001
    raise RuntimeError("smoke fixture: tick deliberately raises")
