"""Shared fixtures for the smoke harness.

The smoke harness MUST NOT touch live data, real network, or the
operator's working database. Every helper here returns an isolated,
disposable artifact:

* :func:`temp_sqlite_url` — a per-run SQLite file under ``$TMPDIR``.
* :func:`founder_session_cookies` — a fabricated, signed-style cookie
  pair that the Next.js auth middleware accepts when
  ``THESEUS_SMOKE_TRUST_HEADER`` is set (see frontend_routes).
* :func:`dynamic_segment_value` — deterministic placeholder values for
  ``[id]`` / ``[slug]`` segments when probing routes.
* :func:`with_smoke_env` — context manager that installs the smoke
  environment variables (fixture DB URL, fake API keys, etc.) and
  restores the prior environment on exit.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any


_SMOKE_ENV_DEFAULTS: dict[str, str] = {
    # Fake keys — every external client is expected to be mocked at the
    # request layer (respx/httpx_mock) and never reach the real
    # network. These values exist solely so a `from x import settings`
    # at module load time does not blow up with KeyError.
    "OPENAI_API_KEY": "sk-smoke-test-not-real",
    "ANTHROPIC_API_KEY": "sk-ant-smoke-test-not-real",
    "POLYMARKET_API_KEY": "smoke-test-not-real",
    "KALSHI_API_KEY": "smoke-test-not-real",
    # Operator-only endpoints check an HMAC signature; the harness
    # signs with this shared secret.
    "OPERATOR_HMAC_SECRET": "smoke-harness-operator-secret",
    "CURRENTS_OPERATOR_HMAC_SECRET": "smoke-harness-operator-secret",
    # Tell every component it is running under smoke. Modules that
    # need to no-op external side effects (background polling, real
    # bet submission) gate on this flag.
    "THESEUS_SMOKE": "1",
    # CORS must be a concrete origin under smoke; wildcard fails fast.
    "CURRENTS_CORS_ORIGINS": "http://127.0.0.1:3000",
    # Disable any phone-home telemetry.
    "DO_NOT_TRACK": "1",
}


def temp_sqlite_url(prefix: str = "smoke") -> tuple[str, Path]:
    """Allocate a per-run SQLite file and return ``(url, path)``."""
    fd, path_str = tempfile.mkstemp(prefix=f"{prefix}-", suffix=".sqlite")
    os.close(fd)
    path = Path(path_str)
    return f"sqlite:///{path}", path


def founder_session_cookies() -> dict[str, str]:
    """Return cookies that mark the request as a seeded founder session.

    The frontend harness sets ``THESEUS_SMOKE_TRUST_HEADER`` so the
    Next.js middleware accepts these unsigned cookies — they are
    refused in any environment that does not opt in.
    """
    return {
        "theseus_smoke_session": "founder-fixture",
        "theseus_smoke_role": "founder",
    }


def dynamic_segment_value(segment: str) -> str:
    """Return a deterministic placeholder for a dynamic route segment.

    Keeps fixture IDs stable across runs so any 404/500 captured in a
    smoke JSON is reproducible.
    """
    seg = segment.strip("[]")
    if seg.startswith("..."):
        seg = seg[3:]
    return {
        "id": "smoke-fixture-id",
        "slug": "smoke-fixture-slug",
        "method": "smoke-fixture-method",
        "name": "smoke-fixture-name",
        "version": "v1",
        "uploadId": "smoke-fixture-upload",
        "submissionId": "smoke-fixture-submission",
        "conclusionId": "smoke-fixture-conclusion",
        "runId": "smoke-fixture-run",
        "invocationId": "smoke-fixture-invocation",
        "day": "monday",
    }.get(seg, f"smoke-{seg}")


@contextlib.contextmanager
def with_smoke_env(extra: dict[str, str] | None = None) -> Iterator[dict[str, str]]:
    """Install the smoke env (plus ``extra``); restore prior env on exit."""
    saved: dict[str, Any] = {}
    merged = {**_SMOKE_ENV_DEFAULTS, **(extra or {})}
    for key, value in merged.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield merged
    finally:
        for key, prior in saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def deterministic_id() -> str:
    """Return a stable-ish ID for objects created by smoke pipelines."""
    return f"smoke-{uuid.uuid4().hex[:12]}"
