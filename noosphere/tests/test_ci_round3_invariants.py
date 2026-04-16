"""Tests for the round-3 CI umbrella runner and individual checks."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _run_script(script: str, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "noosphere")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Umbrella runner tests
# ---------------------------------------------------------------------------

class TestUmbrellaRunner:
    def test_json_output_is_valid(self):
        result = _run_script("check_round3_invariants.py", "--json", "--check", "ui-uses-gated-api")
        data = json.loads(result.stdout)
        assert "total" in data
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_single_check_filter(self):
        result = _run_script("check_round3_invariants.py", "--json", "--check", "ui-uses-gated-api")
        data = json.loads(result.stdout)
        assert data["total"] == 1
        assert data["checks"][0]["name"] == "ui-uses-gated-api"

    def test_unknown_check_returns_error(self):
        result = _run_script("check_round3_invariants.py", "--check", "nonexistent-check")
        assert result.returncode == 2

    def test_plain_text_output_has_summary(self):
        result = _run_script("check_round3_invariants.py", "--check", "ui-uses-gated-api")
        assert "Round-3 Invariant Check Summary" in result.stdout


# ---------------------------------------------------------------------------
# No-phone-home check tests
# ---------------------------------------------------------------------------

class TestNoPhoneHome:
    def test_passes_on_clean_repo(self):
        result = _run_script("check_no_phone_home.py")
        assert result.returncode == 0

    def test_json_output(self):
        result = _run_script("check_no_phone_home.py", "--json")
        data = json.loads(result.stdout)
        assert "ok" in data
        assert "violations" in data

    def test_allowlist_env(self):
        result = _run_script(
            "check_no_phone_home.py",
            "--json",
            env_extra={"THESEUS_ALLOWLIST": "custom-domain.org"},
        )
        data = json.loads(result.stdout)
        assert isinstance(data["violations"], list)


# ---------------------------------------------------------------------------
# Phone-home synthetic failure test
# ---------------------------------------------------------------------------

class TestNoPhoneHomeSyntheticFailure:
    def test_detects_unallowlisted_url(self, tmp_path):
        bad_file = tmp_path / "bad_route.py"
        bad_file.write_text(textwrap.dedent("""\
            import requests
            resp = requests.get("https://evil-tracker.io/ping")
        """))

        sys.path.insert(0, str(SCRIPTS))
        try:
            import check_no_phone_home as mod

            violations = mod._scan_file(bad_file, mod._load_allowlist())
            assert len(violations) == 1
            assert "evil-tracker.io" in violations[0]
        finally:
            sys.path.pop(0)

    def test_allowlisted_domain_passes(self, tmp_path):
        ok_file = tmp_path / "ok_route.py"
        ok_file.write_text('url = "https://localhost:8080/api"\n')

        sys.path.insert(0, str(SCRIPTS))
        try:
            import importlib
            import check_no_phone_home as mod

            importlib.reload(mod)
            violations = mod._scan_file(ok_file, mod._load_allowlist())
            assert len(violations) == 0
        finally:
            sys.path.pop(0)


# ---------------------------------------------------------------------------
# Signed artifacts check tests
# ---------------------------------------------------------------------------

class TestSignedArtifacts:
    def test_passes_on_empty_dirs(self):
        result = _run_script("check_signed_artifacts.py")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_json_output(self):
        result = _run_script("check_signed_artifacts.py", "--json")
        data = json.loads(result.stdout)
        assert data["ok"] is True


# ---------------------------------------------------------------------------
# UI-uses-gated-api check tests
# ---------------------------------------------------------------------------

class TestUiUsesGatedApi:
    def test_passes_on_real_repo(self):
        result = _run_script("check_ui_uses_gated_api.py")
        assert result.returncode == 0

    def test_json_output(self):
        result = _run_script("check_ui_uses_gated_api.py", "--json")
        data = json.loads(result.stdout)
        assert data["ok"] is True

    def test_detects_missing_withGated(self, tmp_path):
        route_dir = tmp_path / "round3" / "bad" / "action"
        route_dir.mkdir(parents=True)
        (route_dir / "route.ts").write_text(textwrap.dedent("""\
            import { NextResponse } from "next/server";
            export const POST = async (req) => {
                return NextResponse.json({ ok: true });
            };
        """))

        sys.path.insert(0, str(SCRIPTS))
        try:
            import importlib
            import check_ui_uses_gated_api as mod

            importlib.reload(mod)
            violations = mod._check_round3_routes(tmp_path / "round3")
            assert len(violations) == 1
            assert "POST" in violations[0]
            assert "withGated" in violations[0]
        finally:
            sys.path.pop(0)

    def test_detects_public_write_handler(self, tmp_path):
        api_dir = tmp_path / "app" / "api" / "things"
        api_dir.mkdir(parents=True)
        (api_dir / "route.ts").write_text(textwrap.dedent("""\
            import { NextResponse } from "next/server";
            export const POST = async (req) => {
                return NextResponse.json({ ok: true });
            };
        """))

        sys.path.insert(0, str(SCRIPTS))
        try:
            import importlib
            import check_ui_uses_gated_api as mod

            importlib.reload(mod)
            violations = mod._check_public_routes(tmp_path / "app")
            assert len(violations) == 1
            assert "write handler POST" in violations[0]
        finally:
            sys.path.pop(0)

    def test_public_get_only_passes(self, tmp_path):
        api_dir = tmp_path / "app" / "api" / "data"
        api_dir.mkdir(parents=True)
        (api_dir / "route.ts").write_text(textwrap.dedent("""\
            import { NextResponse } from "next/server";
            export const GET = async () => {
                return NextResponse.json({ items: [] });
            };
        """))

        sys.path.insert(0, str(SCRIPTS))
        try:
            import importlib
            import check_ui_uses_gated_api as mod

            importlib.reload(mod)
            violations = mod._check_public_routes(tmp_path / "app")
            assert len(violations) == 0
        finally:
            sys.path.pop(0)
