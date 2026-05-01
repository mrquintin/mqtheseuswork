from __future__ import annotations

import json
from urllib import error

import pytest

from noosphere.social.x_live_client import XLiveAPIError, XLiveClient


def test_dry_run_curl_redacts_authorization() -> None:
    client = XLiveClient(client_id="client", refresh_token="refresh")
    out = client.dry_run_curl("hello")

    assert "hello" in out
    assert "refresh" not in out
    assert "client" not in out
    assert "<redacted-user-access-token>" in out


def test_post_tweet_refreshes_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_request_json(self, url, *, method, headers, body):  # type: ignore[no-untyped-def]
        calls.append((url, headers.get("Authorization")))
        if url.endswith("/oauth2/token"):
            return {"access_token": "fresh-access"}
        if headers.get("Authorization") == "Bearer stale-access":
            raise XLiveAPIError(401, "expired")
        return {"data": {"id": "tweet_1", "text": json.loads(body)["text"]}}

    monkeypatch.setattr(XLiveClient, "_request_json", fake_request_json)
    client = XLiveClient(
        client_id="client",
        refresh_token="refresh",
        access_token="stale-access",
    )

    result = client.post_tweet("approved body")

    assert result["tweet_id"] == "tweet_1"
    assert calls == [
        ("https://api.x.com/2/tweets", "Bearer stale-access"),
        ("https://api.x.com/2/oauth2/token", None),
        ("https://api.x.com/2/tweets", "Bearer fresh-access"),
    ]


def test_http_error_detail_does_not_require_secret_values() -> None:
    client = XLiveClient(client_id="client", refresh_token="refresh")
    req = error.HTTPError(
        "https://api.x.com/2/tweets",
        403,
        "Forbidden",
        {},
        None,
    )

    with pytest.raises(XLiveAPIError) as excinfo:
        raise XLiveAPIError(req.code, req.reason)

    assert excinfo.value.status_code == 403
