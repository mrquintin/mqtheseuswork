"""Load-test runner core.

Stdlib-only on purpose: the harness needs to run in CI images that may
not have a Python venv install step. Concurrency is implemented with a
``ThreadPoolExecutor`` ramping a worker pool against ``urllib.request``;
that is plenty for K=500 against a single Vercel deploy and avoids
introducing ``aiohttp`` / ``httpx`` as a CI-only dependency.

Three responsibilities live here:

1. **Profile loading.** ``load_profile`` reads ``profiles.json`` and
   returns a typed ``LoadProfile``.
2. **Session simulation.** ``simulate_session`` performs the request
   sequence a real reader of a viral article makes — page load, a few
   public-API hits, and a public ask — using the synthetic User-Agent
   so observability (prompt 44) can filter the traffic out of real
   metrics.
3. **Result aggregation + pass/fail.** ``aggregate`` turns the raw
   request-result list into percentile and error-rate stats;
   ``evaluate`` compares those stats to a profile's budget and returns
   a structured pass/fail object the CLI and dashboard both consume.

The third-party-API constraint is enforced here by listing the only
endpoints the simulator may hit. We do **not** call Polymarket, Kalshi,
or OpenAI — and the public ``/api/public/ask`` endpoint runs retrieval
locally, so it is safe.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SYNTHETIC_USER_AGENT_PREFIX = "theseus-loadtest"
"""Synthetic UA marker. Observability (prompt 44) keys off this prefix
to filter load-test traffic out of real-traffic metrics. Keep stable —
changing it requires a coordinated update on the observability side.
"""

POOL_EXHAUSTION_HINTS = (
    "too many connections",
    "connection pool",
    "remaining connection slots",
    "sorry, too many clients",
)
"""Substrings (case-insensitive) that indicate the upstream DB ran out
of pool slots. We sample the response body of 5xx responses for these.
A single hit counts as one pool-exhaustion event in the run summary.
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Budget:
    """Pass/fail thresholds for a profile.

    A run is failing if **any** of these are violated. ``p50_ms`` and
    ``p95_ms`` apply to the full request mix (homepage + article +
    public-API). ``error_rate`` is the fraction of requests with an
    HTTP 5xx, network error, or timeout. Pool-exhaustion events are
    counted separately because they are typically the leading
    indicator of a concurrency-tier misconfiguration.
    """

    p50_ms: float
    p95_ms: float
    error_rate: float
    max_pool_exhaustion_events: int = 0


@dataclass(frozen=True)
class LoadProfile:
    name: str
    concurrency: int
    peak_concurrency: int
    ramp_seconds: int
    duration_seconds: int
    budget: Budget


@dataclass
class RequestResult:
    path: str
    status: int  # HTTP status, or 0 if the request never reached the server.
    duration_ms: float
    error: str | None = None
    pool_exhaustion: bool = False


@dataclass
class RunStats:
    total: int
    errors: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    pool_exhaustion_events: int
    by_path: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class Verdict:
    passed: bool
    reasons: list[str]


@dataclass
class RunReport:
    profile: str
    started_at: str
    finished_at: str
    base_url: str
    article_slug: str | None
    stats: RunStats
    budget: Budget
    verdict: Verdict
    samples: int


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def load_profile(profile_name: str, profiles_path: Path) -> LoadProfile:
    """Read ``profiles.json`` and return the named profile."""
    with profiles_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    profiles = raw.get("profiles", {})
    if profile_name not in profiles:
        valid = ", ".join(sorted(profiles.keys()))
        raise KeyError(
            f"unknown load profile {profile_name!r}; valid options: {valid}"
        )
    spec = profiles[profile_name]
    budget_spec = spec["budget"]
    return LoadProfile(
        name=profile_name,
        concurrency=int(spec["concurrency"]),
        peak_concurrency=int(spec.get("peak_concurrency", spec["concurrency"])),
        ramp_seconds=int(spec["ramp_seconds"]),
        duration_seconds=int(spec["duration_seconds"]),
        budget=Budget(
            p50_ms=float(budget_spec["p50_ms"]),
            p95_ms=float(budget_spec["p95_ms"]),
            error_rate=float(budget_spec["error_rate"]),
            max_pool_exhaustion_events=int(
                budget_spec.get("max_pool_exhaustion_events", 0)
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Request driver
# ---------------------------------------------------------------------------


def synthetic_user_agent(profile: str, run_id: str) -> str:
    """The UA observability filters on. Format documented at the
    constant ``SYNTHETIC_USER_AGENT_PREFIX``.
    """
    return f"{SYNTHETIC_USER_AGENT_PREFIX}/{profile}/{run_id}"


def _do_request(
    base_url: str,
    path: str,
    user_agent: str,
    method: str = "GET",
    body: bytes | None = None,
    timeout: float = 10.0,
) -> RequestResult:
    """Single HTTP call. Times out at ``timeout`` seconds.

    Network exceptions (DNS failures, refused connections, read
    timeouts) all surface as a ``RequestResult`` with ``status=0`` and a
    populated ``error``; the caller treats those as errors when
    computing the error rate.
    """
    url = base_url.rstrip("/") + path
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            sample = resp.read(4096)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return RequestResult(
                path=path,
                status=resp.status,
                duration_ms=elapsed_ms,
                error=None,
                pool_exhaustion=_looks_like_pool_exhaustion(resp.status, sample),
            )
    except urllib.error.HTTPError as exc:
        # 4xx/5xx responses still count as completed requests.
        try:
            sample = exc.read(4096) if exc.fp else b""
        except Exception:
            sample = b""
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return RequestResult(
            path=path,
            status=exc.code,
            duration_ms=elapsed_ms,
            error=f"HTTP {exc.code}" if exc.code >= 500 else None,
            pool_exhaustion=_looks_like_pool_exhaustion(exc.code, sample),
        )
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return RequestResult(
            path=path,
            status=0,
            duration_ms=elapsed_ms,
            error=type(exc).__name__,
            pool_exhaustion=False,
        )


def _looks_like_pool_exhaustion(status: int, body_sample: bytes) -> bool:
    if status < 500:
        return False
    try:
        text = body_sample.decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    return any(hint in text for hint in POOL_EXHAUSTION_HINTS)


# ---------------------------------------------------------------------------
# Session simulation
# ---------------------------------------------------------------------------


def session_paths(article_slug: str | None, conclusion_id: str | None) -> list[tuple[str, str, bytes | None]]:
    """The ordered call-list a typical reader makes when an article goes
    viral.

    Tuple shape: ``(method, path, body)``. ``body`` is JSON-encoded for
    POSTs, ``None`` for GETs.

    Hard rule: every path here lives under our own deploy. We never
    contact Polymarket, Kalshi, OpenAI, or any third-party API. Any
    upstream those endpoints fan out to is the deploy's problem to mock
    or rate-limit; the harness itself only ever talks to the public
    site.
    """
    article = article_slug or "preview"
    paths: list[tuple[str, str, bytes | None]] = [
        ("GET", "/", None),
        ("GET", f"/post/{article}", None),
        ("GET", "/api/public/methodology/manifest", None),
    ]
    if conclusion_id:
        paths.append(("GET", f"/api/public/conclusion/{conclusion_id}/lineage", None))
    paths.append(
        (
            "POST",
            "/api/public/ask",
            json.dumps({"query": "what does this article conclude"}).encode("utf-8"),
        ),
    )
    return paths


def simulate_session(
    base_url: str,
    user_agent: str,
    article_slug: str | None,
    conclusion_id: str | None,
    request_fn: Callable[..., RequestResult] = _do_request,
    jitter_ms: tuple[int, int] = (50, 250),
) -> list[RequestResult]:
    """Replay one reader's sequence. Inserts a small random jitter
    between calls so 200 sessions don't fire the same request at the
    same instant — that is unrealistic and produces misleading p95
    numbers.
    """
    out: list[RequestResult] = []
    for method, path, body in session_paths(article_slug, conclusion_id):
        result = request_fn(
            base_url,
            path,
            user_agent,
            method=method,
            body=body,
        )
        out.append(result)
        lo, hi = jitter_ms
        time.sleep(random.uniform(lo, hi) / 1000.0)
    return out


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------


def _ramp_concurrency(profile: LoadProfile, elapsed: float) -> int:
    """Linear ramp from ``concurrency`` up to ``peak_concurrency`` over
    ``ramp_seconds``, then hold. ``elapsed`` is seconds since run start.
    """
    if profile.peak_concurrency <= profile.concurrency:
        return profile.concurrency
    if elapsed >= profile.ramp_seconds:
        return profile.peak_concurrency
    frac = max(0.0, elapsed / max(1, profile.ramp_seconds))
    return int(
        profile.concurrency
        + frac * (profile.peak_concurrency - profile.concurrency)
    )


def run_profile(
    base_url: str,
    profile: LoadProfile,
    article_slug: str | None,
    conclusion_id: str | None,
    run_id: str,
    request_fn: Callable[..., RequestResult] = _do_request,
) -> list[RequestResult]:
    """Drive ``profile.peak_concurrency`` worker threads against the
    deploy for ``profile.duration_seconds``. The pool is sized to peak
    so spike profiles don't have to grow it mid-run; ramping is
    expressed as the number of *active* sessions at any moment, which
    a token bucket gates.
    """
    user_agent = synthetic_user_agent(profile.name, run_id)
    results: list[RequestResult] = []
    results_lock = threading.Lock()
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            session_results = simulate_session(
                base_url,
                user_agent,
                article_slug,
                conclusion_id,
                request_fn=request_fn,
            )
            with results_lock:
                results.extend(session_results)

    pool_size = max(profile.peak_concurrency, profile.concurrency)
    executor = ThreadPoolExecutor(max_workers=pool_size)
    started_at = time.perf_counter()
    active: list[Any] = []
    try:
        end_at = started_at + profile.duration_seconds
        # Initial fill, then top up on each tick to honor the ramp.
        last_target = 0
        while time.perf_counter() < end_at:
            elapsed = time.perf_counter() - started_at
            target = _ramp_concurrency(profile, elapsed)
            while len(active) < target:
                active.append(executor.submit(worker))
            last_target = target
            time.sleep(0.5)
        stop.set()
    finally:
        stop.set()
        executor.shutdown(wait=True)
    _ = last_target  # silence unused
    return results


# ---------------------------------------------------------------------------
# Aggregation + verdict
# ---------------------------------------------------------------------------


def _percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile; matches the convention used in the ops
    dashboard (prompt 44 metrics) so dashboards stay comparable.
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(1, math.ceil((pct / 100.0) * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def aggregate(results: Iterable[RequestResult]) -> RunStats:
    rows = list(results)
    durations = [r.duration_ms for r in rows]
    errors = [
        r
        for r in rows
        if r.status == 0 or r.status >= 500 or r.error is not None
    ]
    pool_events = sum(1 for r in rows if r.pool_exhaustion)

    by_path: dict[str, dict[str, float]] = {}
    paths = sorted({r.path for r in rows})
    for path in paths:
        path_rows = [r for r in rows if r.path == path]
        path_durations = [r.duration_ms for r in path_rows]
        path_errors = sum(
            1
            for r in path_rows
            if r.status == 0 or r.status >= 500 or r.error is not None
        )
        by_path[path] = {
            "count": float(len(path_rows)),
            "errors": float(path_errors),
            "p50_ms": _percentile(path_durations, 50),
            "p95_ms": _percentile(path_durations, 95),
        }

    return RunStats(
        total=len(rows),
        errors=len(errors),
        error_rate=(len(errors) / len(rows)) if rows else 0.0,
        p50_ms=_percentile(durations, 50),
        p95_ms=_percentile(durations, 95),
        p99_ms=_percentile(durations, 99),
        pool_exhaustion_events=pool_events,
        by_path=by_path,
    )


def evaluate(stats: RunStats, budget: Budget) -> Verdict:
    reasons: list[str] = []
    if stats.p50_ms > budget.p50_ms:
        reasons.append(
            f"p50 {stats.p50_ms:.0f}ms exceeds budget {budget.p50_ms:.0f}ms"
        )
    if stats.p95_ms > budget.p95_ms:
        reasons.append(
            f"p95 {stats.p95_ms:.0f}ms exceeds budget {budget.p95_ms:.0f}ms"
        )
    if stats.error_rate > budget.error_rate:
        reasons.append(
            f"error rate {stats.error_rate:.3f} exceeds budget {budget.error_rate:.3f}"
        )
    if stats.pool_exhaustion_events > budget.max_pool_exhaustion_events:
        reasons.append(
            f"observed {stats.pool_exhaustion_events} pool-exhaustion events "
            f"(budget {budget.max_pool_exhaustion_events})"
        )
    return Verdict(passed=len(reasons) == 0, reasons=reasons)


def report_to_json(report: RunReport) -> dict[str, Any]:
    """Serialize a ``RunReport`` to a JSON-safe dict. The dashboard
    parses this exact shape — see ``loadTestData.ts``.
    """
    return {
        "profile": report.profile,
        "startedAt": report.started_at,
        "finishedAt": report.finished_at,
        "baseUrl": report.base_url,
        "articleSlug": report.article_slug,
        "samples": report.samples,
        "stats": {
            "total": report.stats.total,
            "errors": report.stats.errors,
            "errorRate": report.stats.error_rate,
            "p50Ms": report.stats.p50_ms,
            "p95Ms": report.stats.p95_ms,
            "p99Ms": report.stats.p99_ms,
            "poolExhaustionEvents": report.stats.pool_exhaustion_events,
            "byPath": report.stats.by_path,
        },
        "budget": asdict(report.budget),
        "verdict": {
            "passed": report.verdict.passed,
            "reasons": list(report.verdict.reasons),
        },
    }
