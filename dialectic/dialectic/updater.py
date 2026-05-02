"""Lightweight update checker for Dialectic.

On launch, checks a JSON release manifest. A manifest can announce either a
new semantic version or a new build from a later commit at the same version.
If an update is available, the callback receives the manifest plus local build
metadata so the UI can prompt the user. There is no silent auto-install.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from dialectic import __version__ as FALLBACK_VERSION
from dialectic import build_info

logger = logging.getLogger(__name__)

UPDATE_MANIFEST_URL = (
    "https://github.com/mrquintin/mqtheseuswork/releases/download/"
    "latest-main/dialectic-latest.json"
)
# Manifest format:
# {
#   "version": "0.2.0",
#   "commit": "abc123...",
#   "build": "github-run-id",
#   "download_url": "https://...",
#   "download_urls": {"macos": "https://...", "windows": "https://..."},
#   "release_notes": "..."
# }

_REQUEST_TIMEOUT_SECONDS = 10
_MISSING = {"", "unknown", "none", "null"}


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _MISSING else text


def _current_version() -> str:
    """Return the running version, falling back to the package __version__
    when the dist metadata is unavailable (e.g. PyInstaller frozen builds)."""
    try:
        return pkg_version("dialectic")
    except PackageNotFoundError:
        return _clean(getattr(build_info, "BUILD_VERSION", "")) or FALLBACK_VERSION


def _current_build_id() -> str:
    return _clean(
        os.environ.get("DIALECTIC_BUILD_ID")
        or getattr(build_info, "BUILD_ID", "")
    )


def _git_commit_from_checkout() -> str:
    """Return the local checkout commit in development mode, if available."""
    if getattr(sys, "frozen", False):
        return ""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return _clean(result.stdout)


def _current_commit() -> str:
    return _clean(
        os.environ.get("DIALECTIC_BUILD_COMMIT")
        or _git_commit_from_checkout()
        or getattr(build_info, "BUILD_COMMIT", "")
    )


def _manifest_commit(data: dict) -> str:
    for key in ("commit", "commit_sha", "sha", "git_sha"):
        value = _clean(data.get(key))
        if value:
            return value
    return ""


def _manifest_build_id(data: dict) -> str:
    for key in ("build", "build_id", "run_id", "build_number"):
        value = _clean(data.get(key))
        if value:
            return value
    return ""


def _same_commit(a: str, b: str) -> bool:
    left = _clean(a).lower()
    right = _clean(b).lower()
    if not left or not right:
        return False
    return left == right or left.startswith(right) or right.startswith(left)


def _update_reason(data: dict) -> str:
    """Return ``version``, ``commit``, or ``build`` when an update is available."""
    current_version = Version(_current_version())
    latest_version = Version(str(data["version"]))
    if latest_version > current_version:
        return "version"
    if latest_version < current_version:
        return ""

    latest_commit = _manifest_commit(data)
    current_commit = _current_commit()
    if (
        latest_commit
        and current_commit
        and not _same_commit(latest_commit, current_commit)
    ):
        return "commit"

    latest_build = _manifest_build_id(data)
    current_build = _current_build_id()
    if latest_build and current_build and latest_build != current_build:
        return "build"

    return ""


def _annotate_update(data: dict, reason: str) -> dict:
    info = dict(data)
    info["update_reason"] = reason
    info["current_version"] = _current_version()
    current_commit = _current_commit()
    current_build = _current_build_id()
    if current_commit:
        info["current_commit"] = current_commit
    if current_build:
        info["current_build"] = current_build
    return info


def check_for_updates(
    callback: Optional[Callable[[dict], None]] = None,
    manifest_url: Optional[str] = None,
) -> threading.Thread:
    """Check for updates in a background thread.

    Calls ``callback(version_info_dict)`` if an update is available. The default
    manifest URL can be overridden with ``DIALECTIC_UPDATE_MANIFEST_URL``.
    Silently does nothing on network errors or malformed manifests.
    Returns the started Thread so callers can join it in tests.
    """

    def _check() -> None:
        try:
            url = manifest_url or os.environ.get(
                "DIALECTIC_UPDATE_MANIFEST_URL", UPDATE_MANIFEST_URL
            )
            if not url:
                return
            req = Request(url, headers={"User-Agent": "Dialectic-Updater"})
            with urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read())
            if not isinstance(data, dict):
                return
            reason = _update_reason(data)
            if reason and callback is not None:
                callback(_annotate_update(data, reason))
        except (
            URLError,
            KeyError,
            InvalidVersion,
            json.JSONDecodeError,
            ValueError,
        ) as e:
            logger.debug("Update check failed (non-fatal): %s", e)
        except Exception as e:  # noqa: BLE001 - update check must never crash the app
            logger.debug("Unexpected update check error (non-fatal): %s", e)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    return t
