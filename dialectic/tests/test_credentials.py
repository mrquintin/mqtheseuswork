"""Tests for Dialectic Codex credential login and validation."""

from __future__ import annotations

import io
import json
import stat
import urllib.error
from unittest.mock import MagicMock, patch

from dialectic import credentials


def _login_response() -> dict:
    return {
        "apiKey": "tcx_test_key",
        "keyId": "key_123",
        "label": "dialectic-desktop",
        "organizationSlug": "theseus-local",
        "codexUrl": "https://www.theseuscodex.com",
        "founder": {
            "id": "founder_123",
            "name": "Test Founder",
            "email": "founder@example.com",
        },
    }


def _fake_response(status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_default_codex_url_points_to_public_production():
    assert credentials.DEFAULT_CODEX_URL == "https://www.theseuscodex.com"


def test_login_mints_and_persists_api_key(monkeypatch, tmp_path):
    cred_path = tmp_path / "credentials.json"
    monkeypatch.setenv("DIALECTIC_CREDENTIALS_PATH", str(cred_path))

    with patch.object(credentials, "_json_post", return_value=_login_response()):
        stored = credentials.login(
            codex_url="https://www.theseuscodex.com",
            organization_slug="theseus-local",
            email="founder@example.com",
            password="not-a-real-password",
        )

    assert stored.codex_url == "https://www.theseuscodex.com"
    assert stored.organization_slug == "theseus-local"
    assert stored.api_key == "tcx_test_key"
    assert credentials.load() == stored

    mode = stat.S_IMODE(cred_path.stat().st_mode)
    assert mode == 0o600


def test_login_reports_server_error_without_persisting(monkeypatch, tmp_path):
    cred_path = tmp_path / "credentials.json"
    monkeypatch.setenv("DIALECTIC_CREDENTIALS_PATH", str(cred_path))
    err = urllib.error.HTTPError(
        url="https://www.theseuscodex.com/api/auth/app-login",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(json.dumps({"error": "Invalid credentials"}).encode()),
    )

    with patch.object(credentials, "_json_post", side_effect=err):
        try:
            credentials.login(
                codex_url="https://www.theseuscodex.com",
                organization_slug="theseus-local",
                email="founder@example.com",
                password="wrong-password",
            )
        except credentials.AuthError as exc:
            assert "Invalid credentials" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("login should have raised AuthError")

    assert not cred_path.exists()


def test_validate_returns_true_for_valid_key():
    stored = credentials.StoredCredentials(
        codex_url="https://www.theseuscodex.com",
        organization_slug="theseus-local",
        api_key="tcx_test_key",
        founder_id="founder_123",
        founder_name="Test Founder",
        founder_email="founder@example.com",
        key_id="key_123",
        key_label="dialectic-desktop",
        saved_at="2026-05-02T00:00:00+00:00",
    )
    with patch.object(
        credentials.urllib.request, "urlopen", return_value=_fake_response(200)
    ):
        assert credentials.validate(stored) is True


def test_validate_returns_false_for_rejected_key():
    stored = credentials.StoredCredentials(
        codex_url="https://www.theseuscodex.com",
        organization_slug="theseus-local",
        api_key="tcx_bad_key",
        founder_id="founder_123",
        founder_name="Test Founder",
        founder_email="founder@example.com",
        key_id="key_123",
        key_label="dialectic-desktop",
        saved_at="2026-05-02T00:00:00+00:00",
    )
    err = urllib.error.HTTPError(
        url="https://www.theseuscodex.com/api/auth/whoami",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b""),
    )
    with patch.object(credentials.urllib.request, "urlopen", side_effect=err):
        assert credentials.validate(stored) is False


def test_validate_keeps_credentials_when_network_is_unreachable():
    stored = credentials.StoredCredentials(
        codex_url="https://www.theseuscodex.com",
        organization_slug="theseus-local",
        api_key="tcx_test_key",
        founder_id="founder_123",
        founder_name="Test Founder",
        founder_email="founder@example.com",
        key_id="key_123",
        key_label="dialectic-desktop",
        saved_at="2026-05-02T00:00:00+00:00",
    )
    err = urllib.error.URLError("offline")
    with patch.object(credentials.urllib.request, "urlopen", side_effect=err):
        assert credentials.validate(stored) is True
