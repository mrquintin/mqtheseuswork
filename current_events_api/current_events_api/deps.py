"""FastAPI lifespan + dependency getters.

The Store is resolved from ``NOOSPHERE_DATA_DIR`` — a directory containing
(or about to contain) ``noosphere.db``. We use ``Store.from_database_url``
with a SQLite URL derived from that path; this matches every other
in-tree caller of the Store (see theseus-codex bridge scripts) and the
default in ``noosphere.config`` (``sqlite:///./noosphere_data/noosphere.db``).

Also owns the in-process ``OpinionTailer`` which tails the DB for newly
generated opinions and pushes them onto the ``OpinionBus`` so the
``/v1/currents/stream`` SSE route can broadcast them without the scheduler
ever touching the bus.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.publisher import OpinionTailer
from noosphere.store import Store

from current_events_api.event_bus import OpinionBus


_state: dict[str, Any] = {}


def _open_store(data_dir: str) -> Store:
    """Open a Store using the standard ``NOOSPHERE_DATA_DIR/noosphere.db`` layout."""
    db_path = Path(data_dir).expanduser().resolve() / "noosphere.db"
    url = f"sqlite:///{db_path}"
    return Store.from_database_url(url)


@asynccontextmanager
async def lifespan(app):  # noqa: ANN001 - FastAPI passes the app here
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "./noosphere_data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    _state["data_dir"] = Path(data_dir)
    _state["store"] = _open_store(data_dir)
    # Persistent hourly budget — counters and window_start live in
    # currents_budget.json so an API restart does not reset the hour.
    _state["budget"] = HourlyBudgetGuard.load(
        Path(data_dir).expanduser().resolve() / "currents_budget.json"
    )
    _state["bus"] = OpinionBus()
    # In-process tailer: scans for new opinions and publishes onto the bus.
    tailer = OpinionTailer(_state["store"], _state["bus"])
    _state["tailer"] = tailer
    try:
        await tailer.start()
    except Exception:  # noqa: BLE001
        # Never block app startup on tailer construction.
        _state["tailer"] = None
    try:
        yield
    finally:
        tailer = _state.get("tailer")
        if tailer is not None:
            try:
                await tailer.stop()
            except Exception:  # noqa: BLE001
                pass
        _state.clear()


def get_store() -> Store:
    return _state["store"]


def get_budget() -> HourlyBudgetGuard:
    return _state["budget"]


def get_bus() -> OpinionBus:
    return _state["bus"]


def get_data_dir() -> Path:
    return _state.get("data_dir", Path("./noosphere_data"))
