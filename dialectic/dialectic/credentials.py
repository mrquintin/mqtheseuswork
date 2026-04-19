"""
Credentials management for Dialectic.

Every launch must be gated by a valid Codex session — both so audio
captured in the app is attributed to a real founder, and so the cloud
upload flow has a key to post with. This module handles four things:

  1. Persist the signed-in founder's API key + metadata to a JSON file
     inside the OS-appropriate Application Support directory.
  2. Load those credentials on subsequent launches.
  3. Validate them against the Codex's `/api/auth/whoami` endpoint
     (skipped offline so a plane session still works).
  4. Expose a `login()` helper that exchanges email+password for a
     fresh API key via `/api/auth/app-login`.

Security notes:
  * The credentials file is chmod 600 on POSIX platforms so other
    users on the same machine can't read it. On Windows we rely on
    the per-user AppData directory's ACLs.
  * We store ONLY the API key plaintext, not the user's password.
    The password is never written to disk; it's used once to mint the
    key and immediately discarded.
  * `clear()` deletes the credentials file AND attempts a server-side
    revocation via /api/api-keys/:id (best-effort; if the server is
    unreachable we still wipe local state).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import ssl
import stat
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_CODEX_URL = "https://mqtheseuswork-qiw6.vercel.app"
DEFAULT_ORG_SLUG = "theseus-local"

# Pick a stable path per-OS. The env var overrides so CI / tests can
# isolate without touching the real user state.
_ENV_OVERRIDE = "DIALECTIC_CREDENTIALS_PATH"


def _default_credentials_path() -> Path:
    env = os.environ.get(_ENV_OVERRIDE)
    if env:
        return Path(env).expanduser()
    if platform.system() == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Dialectic"
            / "credentials.json"
        )
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home()))
        return Path(appdata) / "Dialectic" / "credentials.json"
    # Linux / other: XDG-ish layout
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "dialectic" / "credentials.json"


@dataclass
class StoredCredentials:
    codex_url: str
    organization_slug: str
    api_key: str
    founder_id: str
    founder_name: str
    founder_email: str
    key_id: str
    key_label: str
    saved_at: str  # ISO-8601 UTC

    def redacted(self) -> dict[str, Any]:
        """Representation safe to log (API key masked)."""
        d = asdict(self)
        masked = self.api_key[:14] + "…"
        d["api_key"] = masked
        return d


def path() -> Path:
    return _default_credentials_path()


def load() -> Optional[StoredCredentials]:
    """Read credentials from disk. Returns None if missing / malformed."""
    p = path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return StoredCredentials(
            codex_url=str(data["codex_url"]),
            organization_slug=str(data["organization_slug"]),
            api_key=str(data["api_key"]),
            founder_id=str(data["founder_id"]),
            founder_name=str(data["founder_name"]),
            founder_email=str(data["founder_email"]),
            key_id=str(data.get("key_id", "")),
            key_label=str(data.get("key_label", "dialectic-desktop")),
            saved_at=str(data.get("saved_at", "")),
        )
    except (OSError, ValueError, KeyError) as e:
        log.warning(
            "credentials: failed to read %s (%s); treating as logged out.",
            p,
            e,
        )
        return None


def save(c: StoredCredentials) -> None:
    """Persist credentials to disk with 0600 permissions (POSIX)."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(asdict(c), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        # Best-effort permission lockdown. Non-POSIX file systems (some
        # network shares) can reject chmod; we ignore those failures.
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    tmp.replace(p)
    log.info("credentials: saved to %s", p)


def clear() -> None:
    """Remove the credentials file (logout). Server-side revoke handled elsewhere."""
    p = path()
    try:
        p.unlink()
        log.info("credentials: cleared %s", p)
    except FileNotFoundError:
        pass


def _environ_cloud_fallback() -> Optional[StoredCredentials]:
    """If DIALECTIC_CLOUD_URL + DIALECTIC_CLOUD_API_KEY are set, treat
    them as an ephemeral "logged-in" state. This preserves the old
    env-only CI flow so existing scripts keep working after we add the
    login gate — `DIALECTIC_CLOUD_*` still auths the cloud uploader,
    it just doesn't persist anything."""
    url = os.environ.get("DIALECTIC_CLOUD_URL")
    key = os.environ.get("DIALECTIC_CLOUD_API_KEY")
    if not url or not key:
        return None
    return StoredCredentials(
        codex_url=url,
        organization_slug=os.environ.get(
            "DIALECTIC_ORGANIZATION_SLUG", DEFAULT_ORG_SLUG
        ),
        api_key=key,
        founder_id="",
        founder_name=os.environ.get("USER", "env-user"),
        founder_email="",
        key_id="",
        key_label="env-var",
        saved_at="",
    )


def active() -> Optional[StoredCredentials]:
    """Return credentials for this process: env override wins, then disk."""
    env = _environ_cloud_fallback()
    if env is not None:
        return env
    return load()


class AuthError(Exception):
    """Raised for login failures — message is user-safe to display."""


def _ssl_context() -> Optional[ssl.SSLContext]:
    """Build a verified SSL context that actually trusts real CAs.

    Why this is not a one-liner: on macOS the Python.org "framework"
    builds ship *without* any CA trust store unless the user runs the
    post-install `Install Certificates.command` script (a huge number
    of Dialectic installs skip this). Python's default SSLContext on
    those builds returns a context with no anchors, so every HTTPS
    call dies with CERTIFICATE_VERIFY_FAILED — which, with the old
    login dialog's broken thread marshalling, looked like "sign-in
    takes forever" because the error never reached the UI.

    We resolve this in priority order:

      1. If ``DIALECTIC_CLOUD_VERIFY_TLS=0`` — insecure mode for
         enterprise intercepting proxies. Mirrors cloud_uploader.py.
      2. If ``certifi`` is importable — use its Mozilla CA bundle.
         PyInstaller bundles already ship with it, and pip-installed
         setups usually do as well (it comes in transitively via
         requests/openai).
      3. If ``SSL_CERT_FILE`` or ``SSL_CERT_DIR`` are set — honour them.
      4. Otherwise fall back to the system default (works on Linux
         and on Homebrew/macOS Python where OpenSSL is linked to the
         system trust store).
    """
    if os.environ.get("DIALECTIC_CLOUD_VERIFY_TLS", "1") == "0":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — certifi is optional
        pass

    cafile = os.environ.get("SSL_CERT_FILE")
    capath = os.environ.get("SSL_CERT_DIR")
    if cafile or capath:
        return ssl.create_default_context(cafile=cafile, capath=capath)

    return None


def _json_post(url: str, body: dict[str, Any], timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Dialectic/0.1 (auth)",
        },
    )
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def login(
    codex_url: str,
    organization_slug: str,
    email: str,
    password: str,
    app_label: str = "dialectic-desktop",
) -> StoredCredentials:
    """Exchange email+password for a fresh API key.

    Returns the freshly-stored credentials on success. Raises AuthError
    with a user-safe message on failure (bad creds, network down,
    unreachable Codex, etc.).
    """
    url = codex_url.rstrip("/") + "/api/auth/app-login"
    body = {
        "email": email,
        "password": password,
        "organizationSlug": organization_slug or DEFAULT_ORG_SLUG,
        "appLabel": app_label,
    }
    try:
        data = _json_post(url, body)
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8", errors="replace"))
            message = str(err_body.get("error", e.reason))
        except Exception:
            message = str(e.reason)
        raise AuthError(f"Sign-in rejected: {message}") from e
    except urllib.error.URLError as e:
        reason = e.reason
        # Detect TLS trust-store failures specifically — they were the
        # #1 silent cause of "sign-in takes forever" before we fixed
        # the thread-marshalling bug upstream.
        if isinstance(reason, ssl.SSLCertVerificationError) or (
            isinstance(reason, ssl.SSLError)
            and "CERTIFICATE_VERIFY_FAILED" in str(reason)
        ):
            raise AuthError(
                "Can't verify the Codex's TLS certificate. "
                "This usually means your Python install is missing root "
                "CAs — try `pip install --upgrade certifi` or, on "
                "Python.org builds, run "
                "`/Applications/Python\\ 3.XX/Install\\ Certificates.command`."
            ) from e
        raise AuthError(f"Can't reach {codex_url}: {reason}") from e
    except OSError as e:
        raise AuthError(f"Network error: {e}") from e

    try:
        import datetime as _dt
        creds = StoredCredentials(
            codex_url=str(data.get("codexUrl") or codex_url).rstrip("/"),
            organization_slug=str(
                data.get("organizationSlug") or organization_slug
            ),
            api_key=str(data["apiKey"]),
            founder_id=str(data["founder"]["id"]),
            founder_name=str(data["founder"].get("name") or email),
            founder_email=str(data["founder"].get("email") or email),
            key_id=str(data.get("keyId", "")),
            key_label=str(data.get("label", app_label)),
            saved_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
    except KeyError as e:
        raise AuthError(f"Unexpected response from Codex: missing {e}") from e

    save(creds)
    return creds


def validate(creds: StoredCredentials, timeout: float = 5.0) -> bool:
    """Ping /api/auth/whoami with the stored key. True on success.

    Returns True also on network errors — we don't want a flaky
    connection to force a re-login when the user's credentials are
    perfectly valid. The token's validity is ultimately checked when
    the user actually uploads, which is a meaningful operation.
    """
    url = creds.codex_url.rstrip("/") + "/api/auth/whoami"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {creds.api_key}",
            "Accept": "application/json",
            "User-Agent": "Dialectic/0.1 (whoami)",
        },
    )
    ctx = _ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Server definitively says the key is bad.
            return False
        log.warning("credentials.validate: HTTP %s from %s", e.code, url)
        # Other HTTP errors (500, 503) are transient — keep the cred.
        return True
    except (urllib.error.URLError, OSError) as e:
        log.info(
            "credentials.validate: offline / unreachable Codex (%s); keeping stored creds.",
            e,
        )
        return True
