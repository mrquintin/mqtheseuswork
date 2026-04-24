"""FastAPI app factory + top-level ``app`` instance.

Run with::

    uvicorn current_events_api.main:app --port 8088

Environment:
  - ``NOOSPHERE_DATA_DIR`` — directory with ``noosphere.db`` (required in
    production; defaults to ``./noosphere_data`` in dev).
  - ``CURRENTS_CORS_ORIGINS`` — comma-separated allow-list (defaults to
    ``http://localhost:3001`` for local theseus-public dev).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from current_events_api.deps import get_bus, get_store, lifespan
from current_events_api.metrics import CurrentsMetrics
from current_events_api.routes import currents, followup, stream


def _parse_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


def _safe_count(store, method_name: str, **kwargs) -> int:
    """Call ``store.method_name(**kwargs)`` and coerce to int, swallowing errors.

    Any failure — missing method, DB error, non-int return — collapses to 0
    so ``/metrics`` never 500s because of a probe.
    """
    method = getattr(store, method_name, None)
    if method is None:
        return 0
    try:
        val = method(**kwargs) if kwargs else method()
        return int(val)
    except Exception:  # noqa: BLE001
        return 0


def create_app() -> FastAPI:
    app = FastAPI(
        title="Theseus Current Events API",
        version="1.0",
        lifespan=lifespan,
    )

    origins = _parse_origins(os.environ.get("CURRENTS_CORS_ORIGINS", ""))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:3001"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-client-id"],
    )

    # Mount the stream router FIRST so ``/v1/currents/stream`` is matched
    # before the dynamic ``/v1/currents/{opinion_id}`` path in currents.
    app.include_router(stream.router, prefix="/v1")
    app.include_router(currents.router, prefix="/v1")
    app.include_router(followup.router, prefix="/v1")

    # Legacy health endpoint kept for existing probes.
    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        from ops.healthz import data_dir_ok, database_ok, scheduler_liveness

        checks = {
            "data_dir": data_dir_ok(),
            "database": database_ok(),
            "scheduler": scheduler_liveness(),
        }
        ok_all = all(c[0] for c in checks.values())
        return JSONResponse(
            status_code=200 if ok_all else 503,
            content={
                "ok": ok_all,
                "checks": {
                    k: {"ok": v[0], "detail": v[1]} for k, v in checks.items()
                },
            },
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        store = get_store()
        bus = get_bus()
        m = CurrentsMetrics(
            opinions_published_total=_safe_count(
                store, "count_event_opinions", revoked=False
            ),
            followup_sessions_active=_safe_count(
                store, "count_active_followup_sessions", window_minutes=30
            ),
            sse_feed_clients=bus.subscriber_count(),
        )
        return PlainTextResponse(m.render(), media_type="text/plain; version=0.0.4")

    return app


app = create_app()
