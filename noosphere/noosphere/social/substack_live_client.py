"""Email-to-post client for human-approved Substack drafts."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Callable, Protocol


class SMTPConnection(Protocol):
    def __enter__(self) -> SMTPConnection: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...
    def starttls(self) -> object: ...
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, msg: EmailMessage) -> object: ...


class SubstackLiveClientError(RuntimeError):
    """Base class for outbound Substack mail failures."""


class SubstackLiveCredentialsError(SubstackLiveClientError):
    """SMTP or email-to-post credentials are missing."""


SMTPFactory = Callable[..., SMTPConnection]


@dataclass
class SubstackLiveClient:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    publish_email: str
    from_email: str
    smtp_factory: SMTPFactory | None = None
    timeout_s: float = 20.0
    use_ssl: bool = False
    use_starttls: bool = True

    @classmethod
    def from_env(cls) -> SubstackLiveClient:
        missing = [
            key
            for key in (
                "SUBSTACK_SMTP_HOST",
                "SUBSTACK_SMTP_PORT",
                "SUBSTACK_SMTP_USER",
                "SUBSTACK_SMTP_PASS",
                "SUBSTACK_PUBLISH_EMAIL",
                "SUBSTACK_FROM_EMAIL",
            )
            if not os.getenv(key, "").strip()
        ]
        if missing:
            raise SubstackLiveCredentialsError(
                "missing required env vars: " + ", ".join(missing)
            )
        port = _env_port("SUBSTACK_SMTP_PORT")
        use_ssl = port == 465
        starttls_raw = os.getenv("SUBSTACK_SMTP_STARTTLS", "true").strip().lower()
        return cls(
            smtp_host=os.environ["SUBSTACK_SMTP_HOST"].strip(),
            smtp_port=port,
            smtp_user=os.environ["SUBSTACK_SMTP_USER"].strip(),
            smtp_pass=os.environ["SUBSTACK_SMTP_PASS"].strip(),
            publish_email=os.environ["SUBSTACK_PUBLISH_EMAIL"].strip(),
            from_email=os.environ["SUBSTACK_FROM_EMAIL"].strip(),
            use_ssl=use_ssl,
            use_starttls=(not use_ssl and starttls_raw not in {"0", "false", "no"}),
        )

    def render_message(self, *, subject: str, markdown_body: str) -> EmailMessage:
        subject = str(subject or "").strip()
        markdown_body = str(markdown_body or "")
        if not subject:
            raise ValueError("subject is required")
        if not markdown_body.strip():
            raise ValueError("markdown_body is required")
        msg = EmailMessage()
        msg["To"] = self.publish_email
        msg["From"] = self.from_email
        msg["Subject"] = subject
        msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg.set_content(markdown_body, subtype="plain", charset="utf-8")
        return msg

    def send_post(self, *, subject: str, markdown_body: str) -> dict[str, str]:
        msg = self.render_message(subject=subject, markdown_body=markdown_body)
        factory = self.smtp_factory or (
            smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        )
        with factory(self.smtp_host, self.smtp_port, timeout=self.timeout_s) as smtp:
            if self.use_starttls:
                smtp.starttls()
            smtp.login(self.smtp_user, self.smtp_pass)
            smtp.send_message(msg)
        return {
            "sent": "true",
            "sent_at": datetime.now(UTC).isoformat(),
            "external_id": "substack-email-to-post",
        }

    def dry_run_text(self, *, subject: str, markdown_body: str) -> str:
        msg = self.render_message(subject=subject, markdown_body=markdown_body)
        envelope = [
            "DRY RUN: Substack email-to-post",
            f"SMTP: {self.smtp_host}:{self.smtp_port}",
            f"From: {msg['From']}",
            f"To: {msg['To']}",
            f"Subject: {msg['Subject']}",
            "",
            markdown_body,
        ]
        return "\n".join(envelope)


def dry_run_client_from_env_or_placeholders() -> SubstackLiveClient:
    return SubstackLiveClient(
        smtp_host=os.getenv("SUBSTACK_SMTP_HOST", "SUBSTACK_SMTP_HOST").strip(),
        smtp_port=_env_port("SUBSTACK_SMTP_PORT", default=587),
        smtp_user=os.getenv("SUBSTACK_SMTP_USER", "SUBSTACK_SMTP_USER").strip(),
        smtp_pass="<redacted>",
        publish_email=os.getenv("SUBSTACK_PUBLISH_EMAIL", "SUBSTACK_PUBLISH_EMAIL").strip(),
        from_email=os.getenv("SUBSTACK_FROM_EMAIL", "SUBSTACK_FROM_EMAIL").strip(),
        use_starttls=False,
    )


def _env_port(key: str, *, default: int | None = None) -> int:
    raw = os.getenv(key, "")
    if not raw.strip():
        if default is not None:
            return default
        raise SubstackLiveCredentialsError(f"{key} is not set")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SubstackLiveCredentialsError(f"{key} must be an integer") from exc
    if port <= 0:
        raise SubstackLiveCredentialsError(f"{key} must be positive")
    return port


def _payload_from_args(args: argparse.Namespace) -> tuple[str, str]:
    subject = args.subject
    markdown_body = args.markdown_body
    if args.post_json_stdin:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        subject = str(payload.get("subject") or "")
        markdown_body = str(payload.get("markdownBody") or payload.get("markdown_body") or "")
    return subject, markdown_body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.social.substack_live_client")
    parser.add_argument("--subject", default="")
    parser.add_argument("--markdown-body", default="")
    parser.add_argument("--post-json-stdin", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        subject, markdown_body = _payload_from_args(args)
        if args.dry_run:
            print(
                dry_run_client_from_env_or_placeholders().dry_run_text(
                    subject=subject,
                    markdown_body=markdown_body,
                )
            )
            return 0

        result: dict[str, Any]
        if os.getenv("THESEUS_SUBSTACK_CLIENT_MOCK") == "1":
            result = {
                "sent": "true",
                "sent_at": datetime.now(UTC).isoformat(),
                "external_id": "mock-substack-email",
            }
        else:
            result = SubstackLiveClient.from_env().send_post(
                subject=subject,
                markdown_body=markdown_body,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
