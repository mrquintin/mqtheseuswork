"""Outbound social-post safety gates."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from noosphere.social.x_formatter import MAX_X_CHARS, weighted_x_length

SOCIAL_KILL_KEY = "theseus.x_kill"
LEGACY_SOCIAL_KILL_KEY = "theseus.social_kill"
URL_RE = re.compile(r"https://[^\s<>()]+", flags=re.IGNORECASE)
MANDATORY_BLOCKLIST = ("password", "apikey", "api_key", "bearer ")
DEFAULT_FIRM_HOSTS = ("theseuscodex.com", "www.theseuscodex.com")

GateFailureCode = Literal[
    "NOT_CONFIGURED",
    "DISABLED",
    "DAILY_BUDGET_EXCEEDED",
    "CONTENT_REJECTED",
    "CITATION_REQUIRED",
    "NOT_APPROVED",
]


@dataclass(frozen=True)
class SocialGateContext:
    oauth_refresh_configured: bool
    posting_enabled: bool
    kill_switch_engaged: bool
    posts_last_24h: int
    daily_max: int
    forbidden_phrases: tuple[str, ...]
    firm_publication_hosts: tuple[str, ...]


class SocialGateFailure(Exception):
    code: GateFailureCode
    detail: str

    def __init__(self, code: GateFailureCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def gate_context_from_env(
    store: Any,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> SocialGateContext:
    now = _aware_utc(now or datetime.now(UTC))
    daily_max = _env_int("X_POSTS_PER_DAY_MAX", 3)
    kill_switch_engaged = social_kill_engaged(store, organization_id)
    posts_last_24h = 0
    counter = getattr(store, "count_social_posts_since", None)
    if callable(counter):
        posts_last_24h = int(
            counter(
                organization_id=organization_id,
                platform="x",
                status="posted",
                since=now - timedelta(hours=24),
            )
            or 0
        )
    return SocialGateContext(
        oauth_refresh_configured=bool(os.getenv("X_BOT_OAUTH_REFRESH_TOKEN", "").strip()),
        posting_enabled=(
            os.getenv("THESEUS_X_POSTING_ENABLED", "").strip().lower() == "true"
        ),
        kill_switch_engaged=kill_switch_engaged,
        posts_last_24h=posts_last_24h,
        daily_max=daily_max,
        forbidden_phrases=_env_csv("X_FORBIDDEN_PHRASES"),
        firm_publication_hosts=_env_csv("THESEUS_FIRM_PUBLICATION_HOSTS")
        or DEFAULT_FIRM_HOSTS,
    )


def check_all_gates(post: Any, ctx: SocialGateContext) -> None:
    """Raise on the first failing outbound-publish gate."""

    if not ctx.oauth_refresh_configured:
        raise SocialGateFailure("NOT_CONFIGURED", "X OAuth refresh token is not configured")
    if not ctx.posting_enabled:
        raise SocialGateFailure("DISABLED", "THESEUS_X_POSTING_ENABLED is not true")
    if ctx.kill_switch_engaged:
        raise SocialGateFailure("DISABLED", f"{SOCIAL_KILL_KEY} is engaged")
    if ctx.posts_last_24h >= ctx.daily_max:
        raise SocialGateFailure(
            "DAILY_BUDGET_EXCEEDED",
            f"{ctx.posts_last_24h} posts already sent in the last 24h",
        )

    body = str(getattr(post, "body", "") or "")
    content_error = content_gate_failure(body, ctx.forbidden_phrases)
    if content_error:
        raise SocialGateFailure("CONTENT_REJECTED", content_error)
    if not citation_gate_passes(body, ctx.firm_publication_hosts):
        raise SocialGateFailure(
            "CITATION_REQUIRED",
            "post body must include an https source link",
        )
    if str(getattr(post, "status", "") or "").lower() != "approved" or not str(
        getattr(post, "approved_by", "") or ""
    ).strip():
        raise SocialGateFailure("NOT_APPROVED", "post has not been approved by an operator")


def content_gate_failure(body: str, forbidden_phrases: tuple[str, ...]) -> str | None:
    if weighted_x_length(body) > MAX_X_CHARS:
        return f"weighted X length exceeds {MAX_X_CHARS}"
    lowered = body.lower()
    for token in (*MANDATORY_BLOCKLIST, *forbidden_phrases):
        token_norm = token.strip().lower()
        if token_norm and token_norm in lowered:
            return "body contains a forbidden token"
    return None


def citation_gate_passes(body: str, firm_publication_hosts: tuple[str, ...]) -> bool:
    for match in URL_RE.finditer(body):
        url = match.group(0)
        host = _host(url)
        if host in {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}:
            return True
        if host in firm_publication_hosts:
            return True
    return False


def social_kill_engaged(store: Any, organization_id: str) -> bool:
    getter = getattr(store, "get_operator_state", None)
    if not callable(getter):
        return False
    for key in (SOCIAL_KILL_KEY, LEGACY_SOCIAL_KILL_KEY):
        row = getter(organization_id, key)
        value = getattr(row, "value", None) if row is not None else None
        if isinstance(value, dict) and bool(value.get("disabled")):
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "disabled", "on"}:
            return True
        if value is not None and bool(value):
            return True
    return False


def _env_csv(key: str) -> tuple[str, ...]:
    raw = os.getenv(key, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
