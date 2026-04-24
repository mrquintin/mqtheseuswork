"""
Codex-side authentication for Noosphere CLI.

Many Noosphere CLI commands can mutate the Codex's Postgres database
(ingest-from-codex writes Conclusion / Contradiction / OpenQuestion
rows; codex-queued reads — still worth gating so an unauthorized user
can't enumerate what's in the queue). This module provides a
lightweight auth layer *on top of* the DIRECT_URL access:

  * ``noosphere login``   — prompts for Codex creds, stores an API key
                            at ~/.noosphere/credentials.json (chmod
                            0600). Under the hood this POSTs to the
                            Codex's /api/auth/app-login endpoint, the
                            same surface Dialectic uses.

  * ``noosphere logout``  — deletes the credentials file.

  * ``noosphere whoami``  — pings /api/auth/whoami and reports the
                            founder the current key resolves to.

Destructive-to-Codex commands (ingest-from-codex, codex-queued) call
``require_auth()`` on entry. If no valid credentials are present, they
exit with an actionable error message instead of silently running.

``DIRECT_URL`` is still the database-level secret — this layer adds a
Codex-level identity so we know which founder triggered a run, and
can audit it via AuditEvent rows.
"""

from __future__ import annotations

import dataclasses
import datetime
import getpass
import json
import logging
import os
import ssl
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


DEFAULT_CODEX_URL = "https://mqtheseuswork-qiw6.vercel.app"
DEFAULT_ORG_SLUG = "theseus-local"

_ENV_CREDENTIALS_PATH = "NOOSPHERE_CREDENTIALS_PATH"
_ENV_API_KEY = "NOOSPHERE_API_KEY"
_ENV_CODEX_URL = "NOOSPHERE_CODEX_URL"


def credentials_path() -> Path:
    override = os.environ.get(_ENV_CREDENTIALS_PATH)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".noosphere" / "credentials.json"


@dataclasses.dataclass
class Credentials:
    codex_url: str
    organization_slug: str
    api_key: str
    founder_id: str
    founder_name: str
    founder_email: str
    key_id: str
    key_label: str
    saved_at: str  # ISO-8601 UTC

    def masked(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        if self.api_key:
            d["api_key"] = self.api_key[:14] + "…"
        return d


def _ssl_context() -> Optional[ssl.SSLContext]:
    if os.environ.get("NOOSPHERE_VERIFY_TLS", "1") == "0":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _env_credentials() -> Optional[Credentials]:
    """If NOOSPHERE_API_KEY is set, treat it as an ephemeral session.

    Lets CI / scripts skip the interactive login. The env-derived
    "session" is in-memory only; we never write it to disk.
    """
    key = os.environ.get(_ENV_API_KEY)
    if not key:
        return None
    return Credentials(
        codex_url=os.environ.get(_ENV_CODEX_URL, DEFAULT_CODEX_URL).rstrip("/"),
        organization_slug=os.environ.get(
            "NOOSPHERE_ORGANIZATION_SLUG", DEFAULT_ORG_SLUG
        ),
        api_key=key,
        founder_id="",
        founder_name=os.environ.get("USER", "env-user"),
        founder_email="",
        key_id="",
        key_label="env-var",
        saved_at="",
    )


def load() -> Optional[Credentials]:
    """Read stored credentials from disk. Returns None if missing."""
    p = credentials_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return Credentials(
            codex_url=str(data["codex_url"]).rstrip("/"),
            organization_slug=str(data["organization_slug"]),
            api_key=str(data["api_key"]),
            founder_id=str(data.get("founder_id", "")),
            founder_name=str(data.get("founder_name", "")),
            founder_email=str(data.get("founder_email", "")),
            key_id=str(data.get("key_id", "")),
            key_label=str(data.get("key_label", "noosphere-cli")),
            saved_at=str(data.get("saved_at", "")),
        )
    except (OSError, ValueError, KeyError) as e:
        log.warning(
            "noosphere.auth: failed to read %s (%s); treating as logged out.",
            p,
            e,
        )
        return None


def save(c: Credentials) -> None:
    p = credentials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(dataclasses.asdict(c), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    tmp.replace(p)


def clear() -> None:
    p = credentials_path()
    try:
        p.unlink()
    except FileNotFoundError:
        pass


def active() -> Optional[Credentials]:
    env = _env_credentials()
    if env is not None:
        return env
    return load()


class AuthError(Exception):
    """User-safe authentication failure message."""


def _json_post(url: str, body: dict[str, Any], timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Noosphere-CLI/0.1 (auth)",
        },
    )
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _json_get(url: str, api_key: str, timeout: float = 10.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Noosphere-CLI/0.1 (whoami)",
        },
    )
    ctx = _ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        return e.code, body


def login_interactive(
    *,
    codex_url: Optional[str] = None,
    organization_slug: Optional[str] = None,
    email: Optional[str] = None,
    app_label: str = "noosphere-cli",
) -> Credentials:
    """Prompt for credentials on stdin/tty and mint an API key.

    Raises ``AuthError`` on sign-in failure. Writes the key to
    ``~/.noosphere/credentials.json`` on success.
    """
    codex_url = (codex_url or DEFAULT_CODEX_URL).rstrip("/")
    organization_slug = organization_slug or DEFAULT_ORG_SLUG

    # Prompt for fields that weren't passed in.
    if not email:
        email = input("Email: ").strip()
    if not email:
        raise AuthError("Email is required.")
    password = getpass.getpass("Passphrase: ")
    if not password:
        raise AuthError("Passphrase is required.")

    url = f"{codex_url}/api/auth/app-login"
    body = {
        "email": email,
        "password": password,
        "organizationSlug": organization_slug,
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
        raise AuthError(f"Can't reach {codex_url}: {e.reason}") from e

    try:
        creds = Credentials(
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
            saved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
    except KeyError as e:
        raise AuthError(f"Unexpected response from Codex: missing {e}") from e

    save(creds)
    return creds


def whoami(creds: Optional[Credentials] = None) -> dict:
    """Return the /api/auth/whoami response for the given credentials.

    Raises ``AuthError`` if the key is rejected or the request fails.
    """
    c = creds or active()
    if c is None:
        raise AuthError(
            "Not signed in. Run `noosphere login` first (or set "
            "NOOSPHERE_API_KEY for scripted use)."
        )
    url = f"{c.codex_url.rstrip('/')}/api/auth/whoami"
    status, body = _json_get(url, c.api_key)
    if status == 401:
        raise AuthError(
            "Stored API key was rejected by the Codex. Run `noosphere login` "
            "to mint a fresh one."
        )
    if status >= 400:
        raise AuthError(
            f"Codex returned HTTP {status} for /api/auth/whoami: "
            f"{body.get('error', 'unknown error')}"
        )
    return body


def require_auth(
    *,
    action: str = "this command",
) -> Optional[Credentials]:
    """Get valid credentials or exit with a clear error.

    Intended for destructive-to-Codex CLI commands. If no credentials
    exist OR the server rejects them, the command exits (non-zero)
    with instructions. Offline / transient network failures are
    tolerated — we don't want a flaky connection to kill an ingest.

    CI / server-side escape hatch
    -----------------------------
    Setting ``NOOSPHERE_SKIP_AUTH=1`` bypasses the Codex-side auth
    layer entirely. This is appropriate when the caller already
    possesses a higher-trust credential — specifically, the Supabase
    ``DIRECT_URL`` password that every destructive command needs
    anyway. The GitHub Actions workflow that processes uploads runs
    with this bypass because:
      * the workflow has its own secret vault (only repo admins can
        see CODEX_DATABASE_URL), which is a stricter trust boundary
        than a revocable per-device API key;
      * requiring the workflow to also stash and rotate an API key
        adds operational overhead with no marginal security gain.
    Interactive / desktop use is untouched — `noosphere login` is
    still required when running the CLI on a laptop.
    """
    if os.environ.get("NOOSPHERE_SKIP_AUTH", "").strip() in ("1", "true", "yes"):
        log.info(
            "noosphere.auth: NOOSPHERE_SKIP_AUTH set — skipping Codex auth gate for %s.",
            action,
        )
        return None
    c = active()
    if c is None:
        sys.stderr.write(
            f"Not signed in. {action} requires Codex auth.\n"
            f"  Run: noosphere login\n"
            f"  (CI use: set NOOSPHERE_SKIP_AUTH=1 when DIRECT_URL is already trusted)\n"
        )
        sys.exit(2)
    url = f"{c.codex_url.rstrip('/')}/api/auth/whoami"
    try:
        status, _body = _json_get(url, c.api_key, timeout=5.0)
    except (urllib.error.URLError, OSError) as e:
        # Offline or Codex down — trust the stored creds for now.
        log.info(
            "noosphere.auth: whoami unreachable (%s); proceeding with stored creds.",
            e,
        )
        return c
    if status == 401:
        sys.stderr.write(
            "Stored API key is invalid or revoked. Run `noosphere login` to refresh.\n"
        )
        sys.exit(2)
    if status >= 400:
        sys.stderr.write(
            f"Codex /api/auth/whoami returned HTTP {status}. Check NOOSPHERE_CODEX_URL.\n"
        )
        sys.exit(2)
    return c
