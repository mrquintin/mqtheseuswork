"""Smoke harness — full-stack safety net.

Each section module exposes ``run(output_dir, **opts) -> dict`` which
returns a structured payload (also written to disk as
``<section>.json``) of the form::

    {
        "section": str,
        "ok": bool,
        "duration_s": float,
        "checks": [{"name": str, "ok": bool, "detail": Any}, ...],
        "perf_warning": Optional[str],
    }

Failures carry enough information that an operator can act on the JSON
alone — no scraping stderr.
"""

from __future__ import annotations

SECTIONS = (
    "frontend-routes",
    "api-endpoints",
    "cli-help",
    "scheduler-tick",
    "pipelines-e2e",
)
