from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from noosphere.models import SocialPost
from noosphere.social.post_safety import (
    SOCIAL_KILL_KEY,
    SocialGateContext,
    SocialGateFailure,
    check_all_gates,
    gate_context_from_env,
)
from noosphere.store import Store

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def test_identity_gate_fails_without_refresh_token() -> None:
    _assert_gate_code(_ctx(oauth_refresh_configured=False), "NOT_CONFIGURED")


def test_mode_gate_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THESEUS_X_POSTING_ENABLED", raising=False)
    monkeypatch.setenv("X_BOT_OAUTH_REFRESH_TOKEN", "refresh")
    store = Store.from_database_url("sqlite:///:memory:")
    ctx = gate_context_from_env(store, "org_1", now=NOW)

    _assert_gate_code(ctx, "DISABLED")


def test_mode_gate_reads_operator_kill_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THESEUS_X_POSTING_ENABLED", "true")
    monkeypatch.setenv("X_BOT_OAUTH_REFRESH_TOKEN", "refresh")
    store = Store.from_database_url("sqlite:///:memory:")
    store.set_operator_state("org_1", SOCIAL_KILL_KEY, {"disabled": True})
    ctx = gate_context_from_env(store, "org_1", now=NOW)

    assert ctx.kill_switch_engaged is True
    _assert_gate_code(ctx, "DISABLED")


def test_daily_budget_gate_counts_posts_in_last_24h(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THESEUS_X_POSTING_ENABLED", "true")
    monkeypatch.setenv("X_BOT_OAUTH_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("X_POSTS_PER_DAY_MAX", "1")
    store = Store.from_database_url("sqlite:///:memory:")
    store.add_social_post(
        SocialPost(
            organization_id="org_1",
            source="manual",
            platform="x",
            body=_body(),
            media=[],
            status="posted",
            posted_at=NOW - timedelta(hours=1),
        )
    )
    ctx = gate_context_from_env(store, "org_1", now=NOW)

    _assert_gate_code(ctx, "DAILY_BUDGET_EXCEEDED")


def test_content_gate_rejects_over_length_body() -> None:
    post = _post(body=("x" * 280) + " https://x.com/source/status/1")
    _assert_gate_code(_ctx(), "CONTENT_REJECTED", post=post)


@pytest.mark.parametrize("token", ["password", "apikey", "api_key", "bearer "])
def test_content_gate_rejects_mandatory_secret_tokens(token: str) -> None:
    _assert_gate_code(_ctx(), "CONTENT_REJECTED", post=_post(body=f"{token} https://x.com/source/status/1"))


def test_content_gate_rejects_configured_forbidden_phrases() -> None:
    ctx = _ctx(forbidden_phrases=("reckless",))
    _assert_gate_code(ctx, "CONTENT_REJECTED", post=_post(body="reckless https://x.com/source/status/1"))


def test_citation_gate_requires_https_source() -> None:
    _assert_gate_code(_ctx(), "CITATION_REQUIRED", post=_post(body="Pure assertion without a link."))


def test_human_gate_requires_approved_status_and_approver() -> None:
    _assert_gate_code(_ctx(), "NOT_APPROVED", post=_post(status="draft", approved_by=None))


def test_all_gates_pass() -> None:
    check_all_gates(_post(), _ctx())


def _assert_gate_code(
    ctx: SocialGateContext,
    code: str,
    *,
    post: SimpleNamespace | None = None,
) -> None:
    with pytest.raises(SocialGateFailure) as excinfo:
        check_all_gates(post or _post(), ctx)
    assert excinfo.value.code == code


def _ctx(**overrides) -> SocialGateContext:  # type: ignore[no-untyped-def]
    values = {
        "oauth_refresh_configured": True,
        "posting_enabled": True,
        "kill_switch_engaged": False,
        "posts_last_24h": 0,
        "daily_max": 3,
        "forbidden_phrases": (),
        "firm_publication_hosts": ("theseuscodex.com",),
    }
    values.update(overrides)
    return SocialGateContext(**values)


def _post(**overrides) -> SimpleNamespace:  # type: ignore[no-untyped-def]
    values = {"body": _body(), "status": "approved", "approved_by": "founder_1"}
    values.update(overrides)
    return SimpleNamespace(**values)


def _body() -> str:
    return "Theseus complicates the premise. https://x.com/source/status/1"
