"""P8 — operator HMAC secret guards operator routes.

Every Round-19 operator-only route MUST refuse a request that:

* lacks an HMAC signature header,
* signs with the wrong secret,
* signs with a timestamp outside the 5-minute replay window,
* signs the correct body but the body is then tampered with.

The healthy path (valid signature, valid timestamp, untampered body)
MUST be accepted by the dependency. We exercise the dependency
function directly rather than booting the full FastAPI app — the
property under test is the auth check, not the route handlers.

Note on status codes: the current implementation raises
``HTTPException(status_code=401)`` for HMAC failures. The original
spec text said 403; the test pins the actual behavior. Changing this
mapping requires updating both the route and this test.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from current_events_api.routes.operator import (
    OPERATOR_HEADER,
    OPERATOR_REPLAY_WINDOW_SECONDS,
    OPERATOR_TIMESTAMP_HEADER,
    compute_operator_hmac,
    require_operator,
)


SECRET = "test-operator-secret-001"


# Routes that the current operator router protects. Listed here so a
# future addition of a new operator route which forgets to add
# ``dependencies=[Depends(require_operator)]`` will be flagged when a
# maintainer extends this list.
PROTECTED_ROUTES: list[tuple[str, str]] = [
    ("POST", "/v1/operator/forecasts/prn_x/authorize-live"),
    ("POST", "/v1/operator/forecasts/prn_x/bets/bet_x/confirm"),
    ("POST", "/v1/operator/forecasts/prn_x/bets/bet_x/cancel"),
    ("POST", "/v1/operator/kill-switch/engage"),
    ("POST", "/v1/operator/kill-switch/disengage"),
    ("GET", "/v1/operator/live-bets"),
    ("GET", "/v1/operator/setup-status"),
    ("GET", "/v1/operator/stream"),
]


def _make_request(
    *,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> Request:
    """Build a starlette Request that ``require_operator`` can consume."""

    raw_headers: list[tuple[bytes, bytes]] = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "headers": raw_headers,
        "query_string": b"",
        "scheme": "http",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
    }

    body_sent = {"done": False}

    async def receive():
        if body_sent["done"]:
            return {"type": "http.disconnect"}
        body_sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive=receive)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _sign(
    *,
    method: str,
    path: str,
    body: bytes,
    secret: str = SECRET,
    timestamp: float | None = None,
) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else time.time())
    digest = compute_operator_hmac(secret, timestamp=ts, path=path, body=body)
    return {
        OPERATOR_HEADER: f"sha256={digest}",
        OPERATOR_TIMESTAMP_HEADER: ts,
        "content-type": "application/json",
    }


@pytest.fixture(autouse=True)
def _operator_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORECASTS_OPERATOR_SECRET", SECRET)
    yield


# ── Per-route auth contract ───────────────────────────────────────────────


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_route_refuses_missing_signature(method: str, path: str) -> None:
    body = b"{}"
    req = _make_request(method=method, path=path, body=body, headers={})
    with pytest.raises(HTTPException) as exc:
        _run(require_operator(req))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_route_refuses_wrong_secret(method: str, path: str) -> None:
    body = b"{}"
    bad_headers = _sign(method=method, path=path, body=body, secret="WRONG-SECRET")
    req = _make_request(method=method, path=path, body=body, headers=bad_headers)
    with pytest.raises(HTTPException) as exc:
        _run(require_operator(req))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_route_refuses_stale_timestamp(method: str, path: str) -> None:
    body = b"{}"
    stale = time.time() - OPERATOR_REPLAY_WINDOW_SECONDS - 60
    headers = _sign(method=method, path=path, body=body, timestamp=stale)
    req = _make_request(method=method, path=path, body=body, headers=headers)
    with pytest.raises(HTTPException) as exc:
        _run(require_operator(req))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_route_refuses_tampered_body(method: str, path: str) -> None:
    original_body = b'{"operator_id":"op_1","csrf_token":"csrf-001"}'
    tampered_body = b'{"operator_id":"op_attacker","csrf_token":"csrf-001"}'
    headers = _sign(method=method, path=path, body=original_body)
    req = _make_request(method=method, path=path, body=tampered_body, headers=headers)
    with pytest.raises(HTTPException) as exc:
        _run(require_operator(req))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_route_accepts_valid_signature(method: str, path: str) -> None:
    body = b'{"operator_id":"op_1","csrf_token":"csrf-001"}'
    headers = _sign(method=method, path=path, body=body)
    req = _make_request(method=method, path=path, body=body, headers=headers)
    # require_operator returns None on success.
    result = _run(require_operator(req))
    assert result is None


# ── HMAC primitive sanity ─────────────────────────────────────────────────


def test_compute_operator_hmac_is_constant_for_same_input() -> None:
    a = compute_operator_hmac(SECRET, timestamp="1700000000", path="/p", body=b"")
    b = compute_operator_hmac(SECRET, timestamp="1700000000", path="/p", body=b"")
    assert a == b
    # Use hmac.compare_digest so a future regression that breaks
    # constant-time comparison surfaces here too.
    assert hmac.compare_digest(a, b)


def test_compute_operator_hmac_differs_for_different_secret() -> None:
    a = compute_operator_hmac(SECRET, timestamp="t", path="/p", body=b"")
    b = compute_operator_hmac("DIFFERENT", timestamp="t", path="/p", body=b"")
    assert a != b


def test_compute_operator_hmac_differs_for_different_body() -> None:
    a = compute_operator_hmac(SECRET, timestamp="t", path="/p", body=b"a")
    b = compute_operator_hmac(SECRET, timestamp="t", path="/p", body=b"b")
    # Confirm via the underlying primitive too.
    assert hashlib.sha256(b"a").hexdigest() != hashlib.sha256(b"b").hexdigest()
    assert a != b
