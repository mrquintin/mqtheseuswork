from __future__ import annotations

import json
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from noosphere.llm import MockLLMClient
from noosphere.models import SocialPost
from noosphere.social.substack_formatter import format_for_substack
from noosphere.social.substack_live_client import SubstackLiveClient
from noosphere.social.substack_safety import SubstackGateFailure, check_all_gates
from noosphere.social.substack_safety import SubstackGateContext
from noosphere.store import Store


class CapturingSMTP:
    messages: list[EmailMessage] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self) -> CapturingSMTP:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def starttls(self) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        return None

    def send_message(self, msg: EmailMessage) -> None:
        type(self).messages.append(msg)


def test_fixture_session_becomes_draft_then_sends_only_after_approval() -> None:
    CapturingSMTP.messages.clear()
    transcript = (
        "[00:00:12] Michael: Conviction has to survive inspection.\n"
        "[00:01:30] Ada: Memory changes incentives.\n"
        "[00:02:45] Michael: Publish the part that can bear pressure.\n"
    )
    blurb = " ".join(["This session turns a private conversation into public reasoning."] * 8)
    why = " ".join(["The firm needs recorded judgment to become inspectable capital."] * 4)
    payload = format_for_substack(
        title="conviction under inspection",
        source_text=transcript,
        source_kind="session",
        llm_client=MockLLMClient(
            responses=[
                json.dumps(
                    {
                        "subtitle": "A clean draft from a recorded session.",
                        "blurb": blurb,
                        "highlights": [
                            {"timestamp": "00:00:12", "line": "Conviction has to survive inspection."},
                            {"timestamp": "00:01:30", "line": "Memory changes incentives."},
                            {"timestamp": "00:02:45", "line": "Publish the part that can bear pressure."},
                        ],
                        "why_this_matters": why,
                    }
                )
            ]
        ),
    )
    store = Store.from_database_url("sqlite:///:memory:")
    post_id = store.add_social_post(
        SocialPost(
            organization_id="org_1",
            source="session",
            source_id="session_1",
            platform="substack",
            subject=payload["subject"],
            body=payload["body"],
            markdown_body=payload["markdownBody"],
            media=[],
            status="draft",
        )
    )
    post = store.get_social_post(post_id)
    assert post is not None
    assert post.status == "draft"
    assert CapturingSMTP.messages == []

    ctx = SubstackGateContext(identity_configured=True, posting_enabled=True)
    gate_post = _gate_post(post, status="draft", approved_by=None)
    with pytest.raises(SubstackGateFailure) as excinfo:
        check_all_gates(gate_post, ctx)
    assert excinfo.value.code == "NOT_APPROVED"
    assert CapturingSMTP.messages == []

    approved = _gate_post(post, status="approved", approved_by="founder_1")
    check_all_gates(approved, ctx)
    client = SubstackLiveClient(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="smtp-user",
        smtp_pass="smtp-pass",
        publish_email="post@substack.example",
        from_email="founder@example.com",
        smtp_factory=CapturingSMTP,
    )
    client.send_post(subject=approved.subject, markdown_body=approved.markdown_body)

    assert len(CapturingSMTP.messages) == 1
    msg = CapturingSMTP.messages[0]
    assert msg["Subject"] == payload["subject"]
    assert msg["From"] == "founder@example.com"
    assert payload["markdownBody"] in msg.get_content()


def _gate_post(post: SocialPost, *, status: str, approved_by: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        source=post.source,
        source_owner_id="founder_1",
        source_owner_role="founder",
        subject=post.subject,
        body=post.body,
        markdown_body=post.markdown_body,
        status=status,
        approved_by=approved_by,
    )
