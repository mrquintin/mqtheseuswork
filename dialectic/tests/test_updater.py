"""Tests for dialectic.updater — the lightweight update checker."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from dialectic import updater


def _fake_response(payload: dict) -> MagicMock:
    """Build a context-manager mock that mimics urlopen()'s return value."""
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _join(thread, timeout: float = 5.0) -> None:
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "update check thread did not finish in time"


def test_callback_invoked_when_newer_version_available():
    callback = MagicMock()
    payload = {
        "version": "2.0.0",
        "download_url": "https://example.com/dialectic-99.0.0.dmg",
        "release_notes": "test",
    }
    with (
        patch.object(updater, "_current_version", return_value="1.0.0"),
        patch.object(updater, "_current_commit", return_value="abc123"),
        patch.object(updater, "urlopen", return_value=_fake_response(payload)),
    ):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_called_once()
    info = callback.call_args.args[0]
    assert info["version"] == "2.0.0"
    assert info["update_reason"] == "version"
    assert info["current_version"] == "1.0.0"


def test_callback_not_invoked_when_running_latest():
    callback = MagicMock()
    payload = {
        "version": "1.0.0",
        "commit": "abc123",
        "download_url": "x",
        "release_notes": "y",
    }
    with (
        patch.object(updater, "_current_version", return_value="1.0.0"),
        patch.object(updater, "_current_commit", return_value="abc123"),
        patch.object(updater, "urlopen", return_value=_fake_response(payload)),
    ):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


def test_callback_invoked_when_same_version_has_new_commit():
    callback = MagicMock()
    payload = {
        "version": "1.0.0",
        "commit": "def456",
        "download_url": "https://example.com/dialectic.dmg",
    }
    with (
        patch.object(updater, "_current_version", return_value="1.0.0"),
        patch.object(updater, "_current_commit", return_value="abc123"),
        patch.object(updater, "urlopen", return_value=_fake_response(payload)),
    ):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_called_once()
    info = callback.call_args.args[0]
    assert info["update_reason"] == "commit"
    assert info["commit"] == "def456"
    assert info["current_commit"] == "abc123"


def test_short_and_full_matching_commit_do_not_prompt():
    callback = MagicMock()
    payload = {
        "version": "1.0.0",
        "commit": "abcdef1234567890",
        "download_url": "https://example.com/dialectic.dmg",
    }
    with (
        patch.object(updater, "_current_version", return_value="1.0.0"),
        patch.object(updater, "_current_commit", return_value="abcdef1"),
        patch.object(updater, "urlopen", return_value=_fake_response(payload)),
    ):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


def test_callback_invoked_when_same_commit_has_new_build():
    callback = MagicMock()
    payload = {
        "version": "1.0.0",
        "commit": "abc123",
        "build": "new-run",
        "download_url": "https://example.com/dialectic.dmg",
    }
    with (
        patch.object(updater, "_current_version", return_value="1.0.0"),
        patch.object(updater, "_current_commit", return_value="abc123"),
        patch.object(updater, "_current_build_id", return_value="old-run"),
        patch.object(updater, "urlopen", return_value=_fake_response(payload)),
    ):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_called_once()
    assert callback.call_args.args[0]["update_reason"] == "build"


def test_url_error_does_not_propagate():
    callback = MagicMock()
    with patch.object(updater, "urlopen", side_effect=URLError("offline")):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


def test_malformed_manifest_does_not_propagate():
    callback = MagicMock()
    resp = MagicMock()
    resp.read.return_value = b"{not json"
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    with patch.object(updater, "urlopen", return_value=resp):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


def test_missing_version_key_does_not_propagate():
    callback = MagicMock()
    payload = {"download_url": "x"}  # no "version" key
    with patch.object(updater, "urlopen", return_value=_fake_response(payload)):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


def test_returns_started_thread():
    with patch.object(updater, "urlopen", side_effect=URLError("x")):
        t = updater.check_for_updates(callback=None)
    assert t.daemon is True
    _join(t)
