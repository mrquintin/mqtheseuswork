"""Write-side X API v2 client for human-approved posts."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error, parse, request

TOKEN_URL = "https://api.x.com/2/oauth2/token"
TWEET_URL = "https://api.x.com/2/tweets"


class XLiveClientError(RuntimeError):
    """Base class for outbound X client failures."""


class XLiveCredentialsError(XLiveClientError):
    """OAuth user-context credentials are missing or unusable."""


class XLiveAPIError(XLiveClientError):
    """X returned a non-success API response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"X API returned {status_code}: {detail}")


@dataclass
class XLiveClient:
    client_id: str
    refresh_token: str
    client_secret: str | None = None
    access_token: str | None = None
    token_url: str = TOKEN_URL
    tweet_url: str = TWEET_URL
    timeout_s: float = 15.0

    @classmethod
    def from_env(cls) -> XLiveClient:
        client_id = os.getenv("X_BOT_OAUTH_CLIENT_ID", "").strip()
        refresh_token = os.getenv("X_BOT_OAUTH_REFRESH_TOKEN", "").strip()
        if not client_id:
            raise XLiveCredentialsError("X_BOT_OAUTH_CLIENT_ID is not set")
        if not refresh_token:
            raise XLiveCredentialsError("X_BOT_OAUTH_REFRESH_TOKEN is not set")
        return cls(
            client_id=client_id,
            refresh_token=refresh_token,
            client_secret=os.getenv("X_BOT_OAUTH_CLIENT_SECRET", "").strip() or None,
            access_token=os.getenv("X_BOT_OAUTH_ACCESS_TOKEN", "").strip() or None,
            token_url=os.getenv("X_API_OAUTH_TOKEN_URL", TOKEN_URL).strip() or TOKEN_URL,
            tweet_url=os.getenv("X_API_TWEET_URL", TWEET_URL).strip() or TWEET_URL,
        )

    def post_tweet(self, body: str) -> dict[str, str]:
        body = str(body)
        access_token = self.access_token or self.refresh_access_token()
        try:
            payload = self._post_with_token(body, access_token)
        except XLiveAPIError as exc:
            if exc.status_code != 401:
                raise
            access_token = self.refresh_access_token()
            payload = self._post_with_token(body, access_token)

        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            raise XLiveAPIError(502, "X response omitted data.id")
        return {
            "tweet_id": str(data["id"]),
            "posted_at": datetime.now(UTC).isoformat(),
        }

    def dry_run_curl(self, body: str) -> str:
        payload = json.dumps({"text": str(body)}, separators=(",", ":"))
        return (
            f"curl -X POST {json.dumps(self.tweet_url)} "
            "-H 'Authorization: Bearer <redacted-user-access-token>' "
            "-H 'Content-Type: application/json' "
            f"--data {json.dumps(payload)}"
        )

    def refresh_access_token(self) -> str:
        form: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            basic = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"
        else:
            form["client_id"] = self.client_id

        payload = self._request_json(
            self.token_url,
            method="POST",
            headers=headers,
            body=parse.urlencode(form).encode("utf-8"),
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise XLiveCredentialsError("OAuth refresh response omitted access_token")
        rotated_refresh = payload.get("refresh_token")
        if isinstance(rotated_refresh, str) and rotated_refresh:
            self.refresh_token = rotated_refresh
        self.access_token = access_token
        return access_token

    def _post_with_token(self, body: str, access_token: str) -> dict[str, Any]:
        return self._request_json(
            self.tweet_url,
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            body=json.dumps({"text": body}).encode("utf-8"),
        )

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise XLiveAPIError(exc.code, detail) from exc
        except error.URLError as exc:
            raise XLiveAPIError(0, str(exc.reason)) from exc

        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise XLiveAPIError(502, "X response was not JSON") from exc
        if not isinstance(payload, dict):
            raise XLiveAPIError(502, "X response JSON was not an object")
        return payload


def _safe_error_detail(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return exc.reason or "HTTP error"
    if not raw:
        return exc.reason or "HTTP error"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]
    if isinstance(payload, dict):
        for key in ("title", "detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:500]
    return raw[:500]


def _mock_post(body: str) -> dict[str, str]:
    return {
        "tweet_id": f"mock-{abs(hash(body)) % 10_000_000}",
        "posted_at": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.social.x_live_client")
    parser.add_argument("--body", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post-json-stdin", action="store_true")
    args = parser.parse_args(argv)

    try:
        body = args.body
        if args.post_json_stdin:
            payload = json.loads(sys.stdin.read() or "{}")
            if not isinstance(payload, dict):
                raise ValueError("stdin JSON must be an object")
            body = str(payload.get("body") or "")

        if args.dry_run:
            client = XLiveClient(
                client_id="<redacted-client-id>",
                refresh_token="<redacted-refresh-token>",
                tweet_url=os.getenv("X_API_TWEET_URL", TWEET_URL).strip() or TWEET_URL,
            )
            print(client.dry_run_curl(body))
            return 0
        client = XLiveClient.from_env()
        if args.post_json_stdin and os.getenv("THESEUS_X_CLIENT_MOCK") == "1":
            print(json.dumps(_mock_post(body), sort_keys=True))
            return 0
        if not args.post_json_stdin:
            parser.error("refusing live post without --post-json-stdin")
        print(json.dumps(client.post_tweet(body), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
