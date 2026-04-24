"""Lightweight update checker for Noosphere.

On CLI startup the checker hits a version manifest URL (JSON) in a background
thread. If the manifest reports a newer version, the callback is invoked with
the manifest dict so the CLI can print a Rich-formatted notice. No silent
auto-install — users must download manually.

Integration into the CLI (with a ``--no-update-check`` flag) is a future task;
this module only provides the check mechanism and a default Rich-formatted
callback.
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

from noosphere import __version__ as FALLBACK_VERSION

logger = logging.getLogger(__name__)

UPDATE_MANIFEST_URL = "https://releases.theseus.co/noosphere/latest.json"
# Manifest format: {"version": "0.2.0", "download_url": "https://...", "release_notes": "..."}

_REQUEST_TIMEOUT_SECONDS = 10


def _current_version() -> str:
    """Return the running version, falling back to ``noosphere.__version__``
    when dist metadata is unavailable (e.g. PyInstaller frozen builds)."""
    try:
        return pkg_version("noosphere")
    except PackageNotFoundError:
        return FALLBACK_VERSION


def default_terminal_callback(info: dict) -> None:
    """Print a Rich-formatted update notice to the terminal.

    Falls back to plain ``print`` if Rich is not installed for any reason.
    """
    version = info.get("version", "?")
    download_url = info.get("download_url", "")
    notes = info.get("release_notes", "")
    try:
        from rich.console import Console
        from rich.panel import Panel

        body = f"[bold]Noosphere {version}[/bold] is available."
        if download_url:
            body += f"\nDownload: [link]{download_url}[/link]"
        if notes:
            body += f"\n\n{notes}"
        Console(stderr=True).print(Panel(body, title="Update available", border_style="cyan"))
    except Exception:  # noqa: BLE001 - never let the notice itself crash startup
        msg = f"Noosphere {version} is available."
        if download_url:
            msg += f" Download: {download_url}"
        print(msg)


def check_for_updates(
    callback: Optional[Callable[[dict], None]] = None,
    manifest_url: str = UPDATE_MANIFEST_URL,
) -> threading.Thread:
    """Check for updates in a background thread.

    Calls ``callback(version_info_dict)`` if a newer version is available.
    Silently does nothing on network errors or malformed manifests.
    Returns the started Thread so callers can join it in tests.
    """

    def _check() -> None:
        try:
            current = Version(_current_version())
            req = Request(manifest_url, headers={"User-Agent": "Noosphere-Updater"})
            with urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read())
            latest = Version(data["version"])
            if latest > current and callback is not None:
                callback(data)
        except (URLError, KeyError, InvalidVersion, json.JSONDecodeError) as e:
            logger.debug("Update check failed (non-fatal): %s", e)
        except Exception as e:  # noqa: BLE001 - update check must never crash the CLI
            logger.debug("Unexpected update check error (non-fatal): %s", e)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    return t
