"""Outbound Substack safety gates."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

SUBSTACK_KILL_KEY = "theseus.substack_kill"

GateFailureCode = Literal[
    "NOT_CONFIGURED",
    "DISABLED",
    "CONTENT_REJECTED",
    "SOURCE_REJECTED",
    "NOT_APPROVED",
]

REQUIRED_IDENTITY_ENV = (
    "SUBSTACK_SMTP_HOST",
    "SUBSTACK_SMTP_PORT",
    "SUBSTACK_SMTP_USER",
    "SUBSTACK_SMTP_PASS",
    "SUBSTACK_PUBLISH_EMAIL",
    "SUBSTACK_FROM_EMAIL",
)


@dataclass(frozen=True)
class SubstackGateContext:
    identity_configured: bool
    posting_enabled: bool
    kill_switch_engaged: bool = False
    missing_identity: tuple[str, ...] = ()


class SubstackGateFailure(Exception):
    code: GateFailureCode
    detail: str

    def __init__(self, code: GateFailureCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def gate_context_from_env(
    store: Any | None = None,
    organization_id: str | None = None,
) -> SubstackGateContext:
    missing = tuple(key for key in REQUIRED_IDENTITY_ENV if not os.getenv(key, "").strip())
    return SubstackGateContext(
        identity_configured=not missing,
        posting_enabled=(
            os.getenv("THESEUS_SUBSTACK_POSTING_ENABLED", "").strip().lower() == "true"
        ),
        kill_switch_engaged=_substack_kill_engaged(store, organization_id),
        missing_identity=missing,
    )


def check_all_gates(post: Any, ctx: SubstackGateContext) -> None:
    """Raise on the first failing Substack publish gate."""

    if not ctx.identity_configured:
        missing = ", ".join(ctx.missing_identity) if ctx.missing_identity else "required env vars"
        raise SubstackGateFailure("NOT_CONFIGURED", f"Substack identity is incomplete: {missing}")
    if not ctx.posting_enabled:
        raise SubstackGateFailure("DISABLED", "THESEUS_SUBSTACK_POSTING_ENABLED is not true")
    if ctx.kill_switch_engaged:
        raise SubstackGateFailure("DISABLED", f"{SUBSTACK_KILL_KEY} is engaged")

    content_error = content_gate_failure(post)
    if content_error:
        raise SubstackGateFailure("CONTENT_REJECTED", content_error)

    source_error = source_gate_failure(post)
    if source_error:
        raise SubstackGateFailure("SOURCE_REJECTED", source_error)

    if str(_get(post, "status") or "").lower() != "approved" or not str(
        _get(post, "approved_by", "approvedBy") or ""
    ).strip():
        raise SubstackGateFailure("NOT_APPROVED", "post has not been approved by a founder")


def content_gate_failure(post: Any) -> str | None:
    markdown_body = str(_get(post, "markdown_body", "markdownBody") or "")
    subject = str(_get(post, "subject") or "")
    body = str(_get(post, "body") or "")
    if len(markdown_body) < 400:
        return "markdownBody must be at least 400 characters"
    if not (5 <= len(subject) <= 100):
        return "subject must be 5-100 characters"
    if len(body) > 240:
        return "body subtitle must be <= 240 characters"
    return None


def source_gate_failure(post: Any) -> str | None:
    source = str(_get(post, "source") or "").strip().lower()
    approved_by = str(_get(post, "approved_by", "approvedBy") or "").strip()
    if source == "manual":
        return None if approved_by else "manual posts require an approving founder"

    if source in {"currents.opinion", "currents-opinion"}:
        opinion_id = str(_get(post, "source_id", "sourceId", "opinion_id", "opinionId") or "").strip()
        return None if opinion_id else "source opinion id is required"

    if source in {"session", "upload", "upload.essay", "upload.transcript"}:
        owner_id = str(
            _get(post, "source_owner_id", "session_owner_id", "founder_id", "founderId")
            or ""
        ).strip()
        owner_role = str(
            _get(post, "source_owner_role", "session_owner_role", "founder_role", "founderRole")
            or ""
        ).strip().lower()
        if owner_id and owner_role in {"admin", "founder"}:
            return None
        return "source must be owned by a real founder"

    return "unsupported source for Substack publishing"


def _substack_kill_engaged(store: Any | None, organization_id: str | None) -> bool:
    if store is None or not organization_id:
        return False
    getter = getattr(store, "get_operator_state", None)
    if not callable(getter):
        return False
    row = getter(organization_id, SUBSTACK_KILL_KEY)
    value = getattr(row, "value", None) if row is not None else None
    if isinstance(value, dict):
        return bool(value.get("disabled"))
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "disabled", "on"}
    return bool(value) if value is not None else False


def _get(post: Any, *names: str) -> Any:
    for name in names:
        if isinstance(post, dict) and name in post:
            return post[name]
        if hasattr(post, name):
            return getattr(post, name)
    return None
