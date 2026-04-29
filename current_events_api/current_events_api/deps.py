"""FastAPI dependencies for store, budget, rate limiting, and metrics access."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request, status

from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.rate_limit import RateLimitExceeded, RateLimitRegistry

from noosphere.config import get_settings
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.store import Store


class PersistentBudgetGuard:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._guard = HourlyBudgetGuard.load(path)
        self._lock = Lock()

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        with self._lock:
            self._guard.authorize(est_prompt, est_completion)

    def charge(self, prompt: int, completion: int) -> None:
        with self._lock:
            self._guard.charge(prompt, completion)
            self._guard.save(self.path)


def database_url_from_env() -> str:
    explicit = os.environ.get("DATABASE_URL") or os.environ.get("THESEUS_DATABASE_URL")
    if explicit:
        return explicit
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR")
    if data_dir:
        return f"sqlite:///{Path(data_dir) / 'noosphere.db'}"
    return get_settings().database_url


def budget_path_from_env() -> Path:
    explicit = os.environ.get("CURRENTS_BUDGET_PATH")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "currents_budget.json"
    return get_settings().data_dir / "currents_budget.json"


def make_store() -> Store:
    return Store.from_database_url(database_url_from_env())


def make_budget() -> PersistentBudgetGuard:
    return PersistentBudgetGuard(budget_path_from_env())


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_budget(request: Request) -> PersistentBudgetGuard:
    return request.app.state.budget


def get_bus(request: Request) -> OpinionBus:
    return request.app.state.bus


def get_metrics(request: Request) -> Metrics:
    return request.app.state.metrics


def get_rate_limits(request: Request) -> RateLimitRegistry:
    return request.app.state.rate_limits


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    forwarded = request.headers.get("forwarded", "")
    for part in forwarded.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key.lower() == "for":
            return value.strip('"[]') or "unknown"
    if request.client is None:
        return "unknown"
    return request.client.host


def client_fingerprint(request: Request) -> str:
    explicit = (
        request.headers.get("x-client-id")
        or request.headers.get("x-client-fingerprint")
        or ""
    ).strip()
    if explicit:
        return explicit[:128]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    material = f"{client_ip(request)}\n{request.headers.get('user-agent', '')}\n{day}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def rate_limit_http_exception(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"reason": exc.reason, "retry_after_s": exc.retry_after_s},
        headers={"Retry-After": str(exc.retry_after_s)},
    )


async def enforce_read_rate_limit(request: Request) -> None:
    try:
        get_rate_limits(request).check_read(client_ip(request))
    except RateLimitExceeded as exc:
        raise rate_limit_http_exception(exc) from exc


def require_metrics_access(request: Request) -> None:
    token = os.environ.get("CURRENTS_METRICS_TOKEN", "").strip()
    if token:
        bearer = request.headers.get("authorization", "")
        supplied = ""
        if bearer.lower().startswith("bearer "):
            supplied = bearer[7:].strip()
        supplied = supplied or request.headers.get("x-metrics-token", "").strip()
        if supplied == token:
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "metrics_forbidden")

    if client_ip(request) in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "metrics_local_only")


def rate_limit_body(reason: str, retry_after_s: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"reason": reason}
    if retry_after_s is not None:
        body["retry_after_s"] = retry_after_s
    return body
