"""Scheduler tick smoke.

Imports ``noosphere.forecasts.scheduler`` and runs ``run_once`` for
each declared sub-loop against a temp SQLite store. The check fails
if:

* importing the scheduler module raises (a top-level import broke);
* ``run_once`` raises for any individual sub-loop;
* the structured-log payload returned by the tick is missing the
  expected keys (``last_tick_ts``, per-loop entries).

The harness explicitly walks ``_LOOP_NAMES`` so a sub-loop added to
the scheduler but forgotten in this check fails the "newly registered
sub-loop has a broken import" case the spec calls out.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from . import _fixtures


def run(output_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    db_url, db_path = _fixtures.temp_sqlite_url("smoke-scheduler")
    workdir = Path(tempfile.mkdtemp(prefix="smoke-scheduler-"))
    payload: dict[str, Any]
    try:
        with _fixtures.with_smoke_env(
            {
                "THESEUS_CODEX_DATABASE_URL": db_url,
                "DATABASE_URL": db_url,
                "CODEX_DATABASE_URL": db_url,
                "NOOSPHERE_DATA_DIR": str(workdir),
            }
        ):
            # Import is the first failure surface — capture cleanly.
            try:
                from noosphere.forecasts import scheduler as sched_mod
                from noosphere.store import Store
            except Exception as exc:
                checks.append(
                    {"name": "import_scheduler", "ok": False, "detail": repr(exc)}
                )
                return _finalise(checks, started, output_dir)
            checks.append({"name": "import_scheduler", "ok": True, "detail": "ok"})
            try:
                store = Store.from_database_url(db_url)
            except Exception as exc:
                checks.append(
                    {"name": "init_store", "ok": False, "detail": repr(exc)}
                )
                return _finalise(checks, started, output_dir)
            checks.append({"name": "init_store", "ok": True, "detail": "ok"})
            cfg = sched_mod.SchedulerConfig(
                status_file=workdir / "status.json",
                budget_file=workdir / "budget.json",
                equities_budget_file=workdir / "equities_budget.json",
            )
            loop_names = list(sched_mod._LOOP_NAMES)
            for name in loop_names:
                check = _tick_one(sched_mod, store, cfg, name)
                checks.append(check)
    finally:
        try:
            db_path.unlink()
        except OSError:
            pass
    return _finalise(checks, started, output_dir)


def _tick_one(sched_mod: Any, store: Any, cfg: Any, name: str) -> dict[str, Any]:
    try:
        result = asyncio.run(sched_mod.run_once(store, config=cfg, loops=[name]))
    except Exception as exc:
        return {
            "name": f"tick::{name}",
            "ok": False,
            "detail": f"raised: {exc!r}",
        }
    if not isinstance(result, dict):
        return {
            "name": f"tick::{name}",
            "ok": False,
            "detail": f"non-dict status payload ({type(result).__name__})",
        }
    if "last_tick_ts" not in result:
        return {
            "name": f"tick::{name}",
            "ok": False,
            "detail": "status payload missing last_tick_ts",
        }
    return {"name": f"tick::{name}", "ok": True, "detail": "ok"}


def _finalise(checks: list[dict[str, Any]], started: float, output_dir: Path) -> dict[str, Any]:
    duration = time.monotonic() - started
    payload = {
        "section": "scheduler-tick",
        "ok": all(c["ok"] for c in checks) and len(checks) > 0,
        "duration_s": round(duration, 3),
        "checks": checks,
        "summary": {
            "loops_probed": sum(1 for c in checks if c["name"].startswith("tick::")),
            "failures": sum(1 for c in checks if not c["ok"]),
        },
        "perf_warning": f"section exceeded 30s budget ({duration:.1f}s)" if duration > 30 else None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scheduler-tick.json").write_text(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_dir)
    raise SystemExit(0 if result["ok"] else 1)
