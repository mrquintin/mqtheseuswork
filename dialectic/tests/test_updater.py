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
        "version": "99.0.0",
        "download_url": "https://example.com/dialectic-99.0.0.dmg",
        "release_notes": "test",
    }
    with patch.object(updater, "urlopen", return_value=_fake_response(payload)):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_called_once_with(payload)


def test_callback_not_invoked_when_running_latest():
    callback = MagicMock()
    current = updater._current_version()
    payload = {"version": current, "download_url": "x", "release_notes": "y"}
    with patch.object(updater, "urlopen", return_value=_fake_response(payload)):
        t = updater.check_for_updates(callback=callback)
        _join(t)

    callback.assert_not_called()


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
