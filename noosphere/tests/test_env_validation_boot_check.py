"""Boot-check refuses startup when a required env var is missing.

These tests run the boot_check function directly with a synthetic env
mapping and assert: missing required var → SystemExit(1) with a
structured stderr line; complete env → no exit, ok report logged.
"""

from __future__ import annotations

import json

import pytest

from current_events_api.boot_check import BootCheckError, run_boot_check
from noosphere.core.env_validation import (
    Mode,
    REGISTRY,
    VarType,
)


def _full_env(mode: Mode) -> dict[str, str]:
    env: dict[str, str] = {"THESEUS_MODE": mode.value}
    for req in REGISTRY:
        if not req.is_required(mode):
            continue
        if req.type == VarType.SECRET:
            env[req.var_name] = "marker-secret-do-not-leak"
        elif req.type == VarType.STRING:
            env[req.var_name] = "ok"
        elif req.type == VarType.ENUM:
            env[req.var_name] = (req.enum_values or ("HUMAN",))[0]
        elif req.type == VarType.BOOLEAN:
            env[req.var_name] = "false"
        else:
            if req.range is not None:
                lo, hi = req.range
                env[req.var_name] = str(lo + (hi - lo) / 2 if hi > lo else lo)
            else:
                env[req.var_name] = "1"
    return env


def test_boot_check_passes_on_complete_env(capsys: pytest.CaptureFixture) -> None:
    env = _full_env(Mode.ALGORITHMS_ONLY)
    report = run_boot_check(service="api", env=env)
    assert report.ok()
    err = capsys.readouterr().err
    # Structured success line is emitted on stderr.
    assert "boot_check_ok" in err
    # Secret marker never leaks.
    assert "marker-secret-do-not-leak" not in err


def test_boot_check_refuses_startup_on_missing(capsys: pytest.CaptureFixture) -> None:
    env = _full_env(Mode.ALGORITHMS_ONLY)
    env.pop("DATABASE_URL", None)
    with pytest.raises(BootCheckError) as excinfo:
        run_boot_check(service="api", env=env)
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    # The structured failure line names the offending var.
    line = next(l for l in err.splitlines() if l.startswith("{"))
    payload = json.loads(line)
    missing = {entry["var"] for entry in payload["missing"]}
    assert "DATABASE_URL" in missing
    # The human banner also mentions DATABASE_URL.
    assert "DATABASE_URL" in err


def test_boot_check_refuses_on_invalid_enum(capsys: pytest.CaptureFixture) -> None:
    env = _full_env(Mode.FULL)
    env["MEMO_DISPATCH_DEFAULT_MODE"] = "BOGUS"
    with pytest.raises(BootCheckError):
        run_boot_check(service="api", env=env)
    err = capsys.readouterr().err
    assert "MEMO_DISPATCH_DEFAULT_MODE" in err
    assert "INVALID_ENUM" in err


def test_boot_check_no_secret_leak_in_failure(capsys: pytest.CaptureFixture) -> None:
    env = _full_env(Mode.ALGORITHMS_ONLY)
    env["DATABASE_URL"] = "postgres://leak-marker:pw@host/db"
    env.pop("ANTHROPIC_API_KEY", None)
    with pytest.raises(BootCheckError):
        run_boot_check(service="api", env=env)
    err = capsys.readouterr().err
    assert "leak-marker" not in err


def test_boot_check_exit_on_failure_false_returns_report() -> None:
    env = _full_env(Mode.ALGORITHMS_ONLY)
    env.pop("DATABASE_URL", None)
    report = run_boot_check(service="api", env=env, exit_on_failure=False)
    assert not report.ok()
    failures = {r.var_name for r in report.failures()}
    assert "DATABASE_URL" in failures


def test_readyz_env_endpoint_returns_redacted_report(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitting GET /readyz/env returns the validation report with secrets masked."""
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'env.db'}")
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("THESEUS_SKIP_BOOT_CHECK", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak-marker-xyz")

    from current_events_api.main import app

    with TestClient(app) as test_client:
        response = test_client.get("/readyz/env")
    assert response.status_code == 200
    body = response.json()
    assert "mode" in body
    assert "rows" in body
    serialized = json.dumps(body)
    assert "sk-ant-leak-marker-xyz" not in serialized
    for row in body["rows"]:
        if row["type"] == "SECRET" and row["value"] is not None:
            assert row["value"] == "***"
