"""FastAPI app for the Theseus Currents live feed."""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from current_events_api import __version__
from current_events_api.deps import (
    budget_path_from_env,
    get_bus,
    get_metrics,
    make_store,
    require_metrics_access,
)
from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.publisher import OpinionTailer
from current_events_api.rate_limit import RateLimitRegistry
from current_events_api.routes.currents import router as currents_router
from current_events_api.routes.forecasts import (
    forecasts_readyz_contract,
    router as forecasts_router,
)
from current_events_api.routes.forecasts_followup import router as forecasts_followup_router
from current_events_api.routes.forecasts_stream import router as forecasts_stream_router
from current_events_api.routes.followup import router as followup_router
from current_events_api.routes.operator import router as operator_router
from current_events_api.routes.portfolio import router as portfolio_router
from current_events_api.routes.stream import router as stream_router
from noosphere.currents.budget import PersistentHourlyBudgetGuard
from noosphere.currents.status import status_path_from_env


def cors_origins_from_env() -> list[str]:
    raw = os.environ.get("CURRENTS_CORS_ORIGINS", "")
    origins = [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]
    if any(origin == "*" for origin in origins):
        raise RuntimeError("CURRENTS_CORS_ORIGINS must not contain wildcard origins")
    return origins


def scheduler_status_path() -> Path:
    return status_path_from_env()


def scheduler_status_max_age_seconds() -> int:
    raw = os.environ.get("CURRENTS_STATUS_MAX_AGE_SECONDS", "600")
    try:
        return max(1, int(raw))
    except ValueError:
        return 600


def forecasts_resolution_status_path() -> Path:
    explicit = (
        os.environ.get("FORECASTS_RESOLUTION_STATUS_PATH", "").strip()
        or os.environ.get("FORECASTS_STATUS_PATH", "").strip()
    )
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "forecasts_status.json"
    return Path("/var/lib/theseus/forecasts_status.json")


def forecasts_resolution_status_max_age_seconds() -> int:
    raw = (
        os.environ.get("FORECASTS_RESOLUTION_STATUS_MAX_AGE_SECONDS")
        or os.environ.get("FORECASTS_STATUS_MAX_AGE_SECONDS")
        or "600"
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return 600


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = make_store()
    bus = OpinionBus()
    metrics = Metrics()
    tailer = OpinionTailer(store=store, bus=bus, metrics=metrics)
    app.state.store = store
    app.state.bus = bus
    app.state.metrics = metrics
    app.state.rate_limits = RateLimitRegistry()
    app.state.budget = PersistentHourlyBudgetGuard(budget_path_from_env())
    app.state.tailer = tailer
    tailer.start()
    try:
        yield
    finally:
        await tailer.stop()


app = FastAPI(
    title="Theseus Currents API",
    version=__version__,
    lifespan=lifespan,
)

_cors_origins = cors_origins_from_env()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "content-type",
            "x-client-id",
            "x-client-fingerprint",
            "x-forecasts-operator",
            "x-forecasts-timestamp",
        ],
        allow_credentials=False,
        max_age=600,
    )

# Static stream paths must be registered before dynamic detail routes.
app.include_router(forecasts_stream_router)
app.include_router(forecasts_followup_router)
app.include_router(portfolio_router)
app.include_router(operator_router)
app.include_router(forecasts_router)
app.include_router(stream_router)
app.include_router(followup_router)
app.include_router(currents_router)


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/readyz")
def readyz(request: Request) -> dict[str, Any]:
    db_ok = False
    try:
        with request.app.state.store.session() as db:
            db.exec(text("select 1")).first()
        db_ok = True
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"ok": False, "db": "unreachable", "error": str(exc)},
        ) from exc

    status_path = scheduler_status_path()
    max_age = scheduler_status_max_age_seconds()
    if not status_path.is_file():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "db": db_ok,
                "scheduler": "missing_status_file",
                "path": str(status_path),
            },
        )
    age = time.time() - status_path.stat().st_mtime
    if age > max_age:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "db": db_ok,
                "scheduler": "stale",
                "age_seconds": round(age, 3),
                "max_age_seconds": max_age,
            },
        )

    try:
        forecasts_readyz = forecasts_readyz_contract()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
        detail = {
            "ok": False,
            "db": db_ok,
            "scheduler": "fresh",
            "forecasts": detail,
        }
        raise HTTPException(exc.status_code, detail) from exc
    return {
        "ok": True,
        "db": True,
        "scheduler": "fresh",
        "forecasts": forecasts_readyz,
    }


@app.get("/metrics", dependencies=[Depends(require_metrics_access)])
def metrics(
    bus: OpinionBus = Depends(get_bus),
    metrics_obj: Metrics = Depends(get_metrics),
) -> PlainTextResponse:
    metrics_obj.set_gauge("currents_feed_clients", bus.feed_client_count())
    metrics_obj.set_gauge("forecasts_feed_clients", bus.forecasts_client_count())
    metrics_obj.set_gauge("forecasts_operator_clients", bus.operator_client_count())
    metrics_obj.set_gauge("currents_followup_clients", bus.followup_client_count())
    return PlainTextResponse(
        metrics_obj.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
