"""Lightweight update checker for Dialectic.

On launch, checks a version manifest URL (JSON) for the latest version.
If newer than the running version, invokes a callback with the version info
so the UI can show a non-blocking notification. No silent auto-install —
the user must download manually.
"""
from __future__ import annotations

import json
import logging
import threading
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from dialectic import __version__ as FALLBACK_VERSION

logger = logging.getLogger(__name__)

UPDATE_MANIFEST_URL = "https://releases.theseus.co/dialectic/latest.json"
# Manifest format: {"version": "0.2.0", "download_url": "https://...", "release_notes": "..."}

_REQUEST_TIMEOUT_SECONDS = 10


def _current_version() -> str:
    """Return the running version, falling back to the package __version__
    when the dist metadata is unavailable (e.g. PyInstaller frozen builds)."""
    try:
        return pkg_version("dialectic")
    except PackageNotFoundError:
        return FALLBACK_VERSION


def check_for_updates(
    callback: Optional[Callable[[dict], None]] = None,
    manifest_url: str = UPDATE_MANIFEST_URL,
) -> threading.Thread:
    """Check for updates in a background thread.

    Calls ``callback(version_info_dict)`` if an update is available.
    Silently does nothing on network errors or malformed manifests.
    Returns the started Thread so callers can join it in tests.
    """

    def _check() -> None:
        try:
            current = Version(_current_version())
            req = Request(manifest_url, headers={"User-Agent": "Dialectic-Updater"})
            with urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read())
            latest = Version(data["version"])
            if latest > current and callback is not None:
                callback(data)
        except (URLError, KeyError, InvalidVersion, json.JSONDecodeError) as e:
            logger.debug("Update check failed (non-fatal): %s", e)
        except Exception as e:  # noqa: BLE001 - update check must never crash the app
            logger.debug("Unexpected update check error (non-fatal): %s", e)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    return t
