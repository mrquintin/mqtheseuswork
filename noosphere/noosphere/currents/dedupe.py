"""Dedupe hash generation for externally observed events."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_OR_HASHTAG_RE = re.compile(r"(?<![\w])[@#][A-Za-z0-9_]+")
_LEADING_RT_RE = re.compile(r"^\s*rt\s+@[A-Za-z0-9_]+:\s*", re.IGNORECASE)
_LEADING_RT_AFTER_MENTION_RE = re.compile(r"^\s*rt\s*:?\s*", re.IGNORECASE)
_X_STATUS_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}


def _normalize_text(text: str) -> str:
    body = _LEADING_RT_RE.sub("", text)
    body = _URL_RE.sub(" ", body)
    body = _MENTION_OR_HASHTAG_RE.sub(" ", body)
    body = _LEADING_RT_AFTER_MENTION_RE.sub("", body)
    body = body.lower()
    return " ".join(body.split())


def _normalize_url(url: str | None) -> str:
    if not url:
        return ""
    value = url.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return " ".join(value.lower().split())

    host = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]
    if host in _X_STATUS_HOSTS and (
        (len(path_parts) >= 3 and path_parts[1] == "status")
        or path_parts[:3] == ["i", "web", "status"]
    ):
        return ""

    path = parsed.path.rstrip("/")
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=host,
        path=path,
        query="",
        fragment="",
    )
    return urlunsplit(normalized)


def dedupe_hash(text: str, url: str | None) -> str:
    """Return a SHA-256 hash over normalized text plus non-X canonical URL.

    X status URLs identify the observation row, not the underlying event. They
    are therefore omitted from the dedupe payload so quote tweets, reposts, and
    bare-text variants collide when their normalized text is the same.
    """

    payload = f"{_normalize_text(text)}\x00{_normalize_url(url)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

