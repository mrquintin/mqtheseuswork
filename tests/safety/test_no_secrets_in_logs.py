"""P7 — no PII / secret in any log output.

Set every secret-bearing env var to a marker value, run the
public surfaces that read those env vars, then grep every captured
log line for any of the marker strings. A non-zero hit means a
secret leaked into the log stream.

This test is intentionally **silent on failure**: it reports the
marker key and the number of offending log lines but NEVER prints
the line contents — printing them would itself leak the secret into
CI output.
"""

from __future__ import annotations

import importlib
import io
import logging
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# Distinct, easy-to-grep markers per env var. Future maintainers:
# only add an entry here if the var is documented as carrying a real
# secret (key material, DB URL with credentials, etc.). Do NOT put
# innocuous test-only vars here — that would weaken the signal.
_SECRET_MARKERS: dict[str, str] = {
    "POLYMARKET_PRIVATE_KEY": "0xMARKERVALUEPOLYMARKETSECRET",
    "KALSHI_API_PRIVATE_KEY": "PEM_MARKER_KALSHI_SECRET_001",
    "KALSHI_PRIVATE_KEY_PEM": "PEM_MARKER_KALSHI_SECRET_002",
    "DATABASE_URL": "postgresql://MARKER_USER:MARKER_PASS_001@example.invalid:5432/dbx",
    "OPENAI_API_KEY": "sk-MARKER_OPENAI_SECRET_001",
    "ANTHROPIC_API_KEY": "sk-ant-MARKER_ANTHROPIC_SECRET_001",
    "FORECASTS_OPERATOR_SECRET": "MARKER_OPERATOR_SECRET_001",
    "ALPACA_API_SECRET_KEY": "MARKER_ALPACA_SECRET_001",
    "ROBINHOOD_PASSWORD": "MARKER_ROBINHOOD_PASSWORD_001",
}


def _install_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _SECRET_MARKERS.items():
        monkeypatch.setenv(key, value)
    # Live trading flags so the env-readers exercise their hottest paths.
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("EQUITIES_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("ROBINHOOD_ENABLED", "true")
    monkeypatch.setenv("ROBINHOOD_USERNAME", "smoke-user")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "smoke-key-id")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "smoke-kalshi-key")
    monkeypatch.setenv("FORECASTS_MAX_STAKE_USD", "100")
    monkeypatch.setenv("FORECASTS_MAX_DAILY_LOSS_USD", "100")


def _scrub_observed_logs(captured: str) -> dict[str, int]:
    """Return per-marker hit counts. Never returns the offending lines."""
    counts: dict[str, int] = {}
    for env_key, marker in _SECRET_MARKERS.items():
        hits = captured.count(marker)
        if hits:
            counts[env_key] = hits
    return counts


def _format_violations_safely(violations: dict[str, int]) -> str:
    # Format ONLY the env-var name and a count — never the marker value
    # and never the offending log line. The point of the test is to
    # prevent the secret from leaking; an over-helpful failure message
    # would do exactly that.
    parts = [
        f"marker for env var {key!r} appeared in {n} log line(s)"
        for key, n in sorted(violations.items())
    ]
    return "; ".join(parts)


def test_no_secret_marker_leaks_into_root_logger_or_stderr(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """End-to-end-ish: exercise env-reading surfaces and grep for markers."""

    _install_markers(monkeypatch)
    caplog.set_level(logging.DEBUG)

    # Surfaces that read the secret env vars. We invoke each one and
    # let any logging happen. If a surface prints a secret it would
    # land in caplog.records or capsys output.
    from noosphere.forecasts.safety import (
        current_trading_mode,
        gate_context_from_env,
        gate_context_from_env_for_equities,
    )

    mode = current_trading_mode()
    ctx = gate_context_from_env(None)
    eq_ctx = gate_context_from_env_for_equities(None)
    # The contexts must report configured-ness without leaking values.
    assert ctx.polymarket_configured is True
    assert ctx.kalshi_configured is True
    assert eq_ctx.alpaca_configured is True
    assert eq_ctx.robinhood_configured is True
    assert isinstance(mode, str) and mode

    # Also exercise the operator HMAC compute path (it touches the
    # secret env var but must never log it).
    from current_events_api.routes.operator import compute_operator_hmac

    _ = compute_operator_hmac(
        os.environ["FORECASTS_OPERATOR_SECRET"],
        timestamp="1700000000",
        path="/v1/operator/setup-status",
        body=b"{}",
    )

    captured_stderr = capsys.readouterr().err
    # Only consider production code paths — strip anything emitted
    # from this test module itself, since the test's own logging
    # would invalidate the assertion (and is not a real leak).
    production_records = [
        r for r in caplog.records if "test_no_secrets_in_logs" not in r.name
    ]
    captured_logs = "\n".join(r.getMessage() for r in production_records)
    full_capture = captured_logs + "\n" + captured_stderr

    violations = _scrub_observed_logs(full_capture)
    assert not violations, (
        "secret-marker leak detected in log output — "
        + _format_violations_safely(violations)
    )


def test_smoke_log_directory_is_clean_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the smoke harness has been run, its artifacts MUST be clean.

    We never trigger the harness ourselves here — that's the smoke CI's
    job. We just inspect the on-disk artifacts (if any) for marker
    occurrences. If the directory is empty, the test is informational
    (no artifacts to audit yet); the assertion only fires if an
    artifact contains a marker, which would indicate a real leak.
    """

    smoke_root = REPO_ROOT / "docs" / "verification" / "smoke"
    if not smoke_root.is_dir():
        pytest.skip("docs/verification/smoke is not present in this checkout")

    # Use the production marker set, NOT shorter substrings — we want
    # zero risk of incidental matches. Markers are >=24 chars each.
    artifacts: list[Path] = []
    for p in smoke_root.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".log", ".txt", ".md"}:
            artifacts.append(p)
    if not artifacts:
        pytest.skip("no smoke artifacts present yet")

    violations: dict[str, int] = {}
    for path in artifacts:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for env_key, marker in _SECRET_MARKERS.items():
            n = text.count(marker)
            if n:
                violations[env_key] = violations.get(env_key, 0) + n

    assert not violations, (
        "secret-marker leak detected in docs/verification/smoke artifacts — "
        + _format_violations_safely(violations)
    )
