"""
External pollers that detect standing changes for cited sources.

Each adapter exposes a ``poll`` callable that takes a sequence of
canonical source ids (the ones the firm currently cites) and returns
new ``StandingTransition`` rows. The orchestrator below ties them to
the standing ledger and to the cascade-revision wiring.

Pollers MUST honor robots.txt and per-host rate limits — see
``RateLimiter`` in this module. The generic URL fetcher is the one that
materially touches arbitrary hosts, so the rate limiter is built around
it; the Retraction Watch and arXiv adapters hit known feeds at modest
cadence and self-throttle by feed paging.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Protocol, Sequence
from urllib.parse import urlsplit

from noosphere.literature.standing import (
    PROPAGATING_STATUSES,
    CitationLink,
    StandingLedger,
    StandingStatus,
    StandingTransition,
    affected_conclusions,
)
from noosphere.observability import get_logger

log = get_logger(__name__)


class StandingPoller(Protocol):
    name: str

    def poll(
        self, source_ids: Sequence[str]
    ) -> list[StandingTransition]: ...


class RateLimiter:
    """Per-host token bucket; refuses bursts and sleeps within the
    process. Defaults to 1 request per host every 2 seconds — slow
    enough to be polite to small academic mirrors, generous enough that
    a few hundred sources finish in minutes.

    Stateful, but the state is in-memory; pollers that re-instantiate
    a ``RateLimiter`` per run reset the throttle. That's intentional:
    the alternative (process-wide singleton) would couple unrelated
    pollers' rate budgets together.
    """

    def __init__(self, min_interval_s: float = 2.0) -> None:
        self.min_interval_s = float(min_interval_s)
        self._last: dict[str, float] = defaultdict(lambda: 0.0)

    def wait(self, host: str) -> None:
        now = time.monotonic()
        elapsed = now - self._last[host]
        if elapsed < self.min_interval_s:
            sleep = self.min_interval_s - elapsed
            time.sleep(sleep)
        self._last[host] = time.monotonic()


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


@dataclass
class PollerOrchestrator:
    """Runs a registered set of pollers, writes results to the ledger,
    returns the transitions whose status is in ``PROPAGATING_STATUSES``
    so the caller can hand them to the cascade-revision wiring.

    Idempotent: a re-poll that yields the same transitions writes no
    new rows (the ledger handles dedupe).
    """

    ledger: StandingLedger
    pollers: list[StandingPoller] = field(default_factory=list)

    def register(self, poller: StandingPoller) -> None:
        self.pollers.append(poller)

    def run(self, source_ids: Sequence[str]) -> list[StandingTransition]:
        propagating: list[StandingTransition] = []
        for poller in self.pollers:
            try:
                transitions = poller.poll(source_ids)
            except Exception as exc:
                log.warning("standing_poller_failed", poller=poller.name, error=str(exc))
                continue
            for t in transitions:
                wrote = self.ledger.append(t)
                if not wrote:
                    continue
                if t.status in PROPAGATING_STATUSES:
                    propagating.append(t)
        return propagating


# Cascade hook: given a set of propagating transitions and the firm's
# citation graph, produce one ``RevisionInput`` per affected conclusion
# with weight = 0.0 ("evidence weight removed"), per the prompt:
# "evidence weight removed", not "evidence weight inverted".


def revision_inputs_for(
    transitions: Iterable[StandingTransition],
    links: Sequence[CitationLink],
):
    """Return a list of ``(conclusion_id, RevisionInput)`` tuples.

    Imported lazily to avoid pulling cascade dependencies into the
    poller-only code path used by tests.
    """
    from noosphere.cascade.revision import RevisionInput

    out: list[tuple[str, "RevisionInput"]] = []
    for t in transitions:
        for cid in affected_conclusions(links, t.source_id):
            out.append(
                (
                    cid,
                    RevisionInput(
                        claim_id=t.source_id,
                        new_evidence=f"{t.status.value}: {t.reason}",
                        weight=0.0,
                    ),
                )
            )
    return out


__all__ = [
    "PollerOrchestrator",
    "RateLimiter",
    "StandingPoller",
    "host_of",
    "revision_inputs_for",
]
