"""
Generic URL standing poller.

For sources that aren't reachable through DOI / arXiv we still want to
detect:

  * HTTP 410 Gone — explicit retraction signal from the publisher.
  * HTTP 404 Not Found persisting beyond a grace window — likely
    EXPIRED (page replaced or DNS death).
  * Page replacement — the page now serves content whose hash differs
    from the snapshot we ingested. Reported as DISPUTED so a founder
    can decide whether the new content is a correction or just a
    layout change.

The poller honors robots.txt: a separate ``robots_check`` callable is
consulted before any fetch, and a False answer is logged and the URL
is skipped (no silent bypass). Per-host rate limiting is enforced via
the ``RateLimiter`` from the parent package.

The HTTP and robots layers are injected as callables so tests don't
need a network. A live implementation lives at the call site (the
scheduler hook).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from noosphere.literature.standing import (
    StandingStatus,
    StandingTransition,
    canonical_source_id,
    now_utc,
)
from noosphere.literature.standing_polls import RateLimiter, host_of
from noosphere.observability import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class FetchResult:
    """Minimal HTTP response shape needed by the poller."""

    status: int
    body: bytes = b""
    final_url: str = ""


HttpFn = Callable[[str], FetchResult]
RobotsFn = Callable[[str], bool]
SnapshotFn = Callable[[str], Optional[str]]


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@dataclass
class GenericUrlPoller:
    """Detects 410/404/page-replacement for a list of cited URLs.

    Args:
        urls: caller-supplied (canonical_id, url) pairs. We don't try
            to invert canonical ids back to URLs; the citation table
            stores both, and the orchestrator hands them in together.
        http: callable that performs the GET. Tests pass a fake.
        robots: callable that returns True if the URL is allowed. The
            firm's policy is "skip on False, never bypass."
        snapshot: callable returning the last known content hash for a
            canonical id (or None if we never snapshotted), for
            page-replacement detection. None disables that check.
        rate_limiter: per-host throttle. Defaults to 2s between calls
            to the same host.
    """

    urls: Sequence[tuple[str, str]]
    http: HttpFn
    robots: RobotsFn
    snapshot: Optional[SnapshotFn] = None
    rate_limiter: Optional[RateLimiter] = None
    name: str = "generic_url"

    def poll(self, source_ids: Sequence[str]) -> list[StandingTransition]:
        cited = set(source_ids)
        rl = self.rate_limiter or RateLimiter()
        observed = now_utc()
        out: list[StandingTransition] = []

        for src_id, url in self.urls:
            if src_id not in cited:
                continue
            try:
                allowed = self.robots(url)
            except Exception as exc:
                log.warning("robots_check_failed", url=url, error=str(exc))
                continue
            if not allowed:
                log.info("standing_poll_robots_skip", url=url)
                continue

            host = host_of(url)
            if host:
                rl.wait(host)

            try:
                resp = self.http(url)
            except Exception as exc:
                log.warning("standing_poll_http_failed", url=url, error=str(exc))
                continue

            if resp.status == 410:
                out.append(
                    StandingTransition(
                        source_id=src_id,
                        status=StandingStatus.RETRACTED,
                        reason="HTTP 410 Gone",
                        poller=self.name,
                        observed_at=observed,
                        raw_payload={"url": url, "status": 410},
                    )
                )
                continue
            if resp.status in (404, 451) or resp.status >= 500:
                # 404/451 → EXPIRED (the citation no longer resolves);
                # 5xx is treated as transient and ignored to avoid
                # flapping. We only emit an EXPIRED for 404/451 here.
                if resp.status >= 500:
                    continue
                out.append(
                    StandingTransition(
                        source_id=src_id,
                        status=StandingStatus.EXPIRED,
                        reason=f"HTTP {resp.status}",
                        poller=self.name,
                        observed_at=observed,
                        raw_payload={"url": url, "status": resp.status},
                    )
                )
                continue
            if resp.status >= 400:
                continue

            if self.snapshot is not None:
                prior = self.snapshot(src_id)
                if prior is not None:
                    current = content_hash(resp.body)
                    if current != prior:
                        out.append(
                            StandingTransition(
                                source_id=src_id,
                                status=StandingStatus.DISPUTED,
                                reason="Page content changed since ingest",
                                poller=self.name,
                                observed_at=observed,
                                raw_payload={
                                    "url": url,
                                    "prior_hash": prior,
                                    "current_hash": current,
                                },
                            )
                        )

        return out
