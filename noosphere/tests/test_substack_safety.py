from __future__ import annotations

from types import SimpleNamespace

import pytest

from noosphere.social.substack_safety import (
    SUBSTACK_KILL_KEY,
    SubstackGateContext,
    SubstackGateFailure,
    check_all_gates,
    gate_context_from_env,
)
from noosphere.store import Store


def test_identity_gate_requires_all_substack_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SUBSTACK_SMTP_HOST",
        "SUBSTACK_SMTP_PORT",
        "SUBSTACK_SMTP_USER",
        "SUBSTACK_SMTP_PASS",
        "SUBSTACK_PUBLISH_EMAIL",
        "SUBSTACK_FROM_EMAIL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THESEUS_SUBSTACK_POSTING_ENABLED", "true")

    ctx = gate_context_from_env()

    assert ctx.identity_configured is False
    _assert_gate_code(ctx, "NOT_CONFIGURED")


def test_mode_gate_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_identity(monkeypatch)
    monkeypatch.delenv("THESEUS_SUBSTACK_POSTING_ENABLED", raising=False)

    _assert_gate_code(gate_context_from_env(), "DISABLED")


def test_mode_gate_reads_substack_kill_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_identity(monkeypatch)
    monkeypatch.setenv("THESEUS_SUBSTACK_POSTING_ENABLED", "true")
    store = Store.from_database_url("sqlite:///:memory:")
    store.set_operator_state("org_1", SUBSTACK_KILL_KEY, {"disabled": True})

    ctx = gate_context_from_env(store, "org_1")

    assert ctx.kill_switch_engaged is True
    _assert_gate_code(ctx, "DISABLED")


def test_content_gate_rejects_short_markdown() -> None:
    _assert_gate_code(_ctx(), "CONTENT_REJECTED", post=_post(markdown_body="short"))


def test_content_gate_rejects_bad_subject_or_long_subtitle() -> None:
    _assert_gate_code(_ctx(), "CONTENT_REJECTED", post=_post(subject="no"))
    _assert_gate_code(_ctx(), "CONTENT_REJECTED", post=_post(body="x" * 241))


def test_source_gate_requires_founder_owned_session() -> None:
    _assert_gate_code(
        _ctx(),
        "SOURCE_REJECTED",
        post=_post(source_owner_id="", source_owner_role="viewer"),
    )


def test_manual_source_gate_requires_approver() -> None:
    _assert_gate_code(
        _ctx(),
        "SOURCE_REJECTED",
        post=_post(source="manual", approved_by=None),
    )


def test_human_gate_requires_approved_status() -> None:
    _assert_gate_code(_ctx(), "NOT_APPROVED", post=_post(status="draft"))


def test_all_substack_gates_pass() -> None:
    check_all_gates(_post(), _ctx())


def _assert_gate_code(
    ctx: SubstackGateContext,
    code: str,
    *,
    post: SimpleNamespace | None = None,
) -> None:
    with pytest.raises(SubstackGateFailure) as excinfo:
        check_all_gates(post or _post(), ctx)
    assert excinfo.value.code == code


def _ctx(**overrides) -> SubstackGateContext:  # type: ignore[no-untyped-def]
    values = {
        "identity_configured": True,
        "posting_enabled": True,
        "kill_switch_engaged": False,
        "missing_identity": (),
    }
    values.update(overrides)
    return SubstackGateContext(**values)


def _post(**overrides) -> SimpleNamespace:  # type: ignore[no-untyped-def]
    values = {
        "source": "session",
        "source_owner_id": "founder_1",
        "source_owner_role": "founder",
        "subject": "Recorded Reasoning",
        "body": "A short subtitle.",
        "markdown_body": "This is a long Substack draft body. " * 20,
        "status": "approved",
        "approved_by": "founder_1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _set_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTACK_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SUBSTACK_SMTP_PORT", "587")
    monkeypatch.setenv("SUBSTACK_SMTP_USER", "smtp-user")
    monkeypatch.setenv("SUBSTACK_SMTP_PASS", "smtp-pass")
    monkeypatch.setenv("SUBSTACK_PUBLISH_EMAIL", "post@substack.example")
    monkeypatch.setenv("SUBSTACK_FROM_EMAIL", "founder@example.com")
