from __future__ import annotations

from email.message import EmailMessage

from noosphere.social.substack_live_client import SubstackLiveClient


class FakeSMTP:
    messages: list[EmailMessage] = []
    logins: list[tuple[str, str]] = []
    starttls_calls = 0

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def starttls(self) -> None:
        type(self).starttls_calls += 1

    def login(self, user: str, password: str) -> None:
        type(self).logins.append((user, password))

    def send_message(self, msg: EmailMessage) -> None:
        type(self).messages.append(msg)


def test_live_client_sends_expected_email() -> None:
    FakeSMTP.messages.clear()
    FakeSMTP.logins.clear()
    FakeSMTP.starttls_calls = 0
    client = SubstackLiveClient(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="smtp-user",
        smtp_pass="smtp-pass",
        publish_email="post@substack.example",
        from_email="founder@example.com",
        smtp_factory=FakeSMTP,
    )

    result = client.send_post(
        subject="Recorded Reasoning",
        markdown_body="# Recorded Reasoning\n\nFull post body.",
    )

    assert result["sent"] == "true"
    assert FakeSMTP.starttls_calls == 1
    assert FakeSMTP.logins == [("smtp-user", "smtp-pass")]
    assert len(FakeSMTP.messages) == 1
    msg = FakeSMTP.messages[0]
    assert msg["Subject"] == "Recorded Reasoning"
    assert msg["From"] == "founder@example.com"
    assert msg["To"] == "post@substack.example"
    assert "# Recorded Reasoning" in msg.get_content()


def test_dry_run_renders_envelope_without_send() -> None:
    FakeSMTP.messages.clear()
    client = SubstackLiveClient(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="smtp-user",
        smtp_pass="smtp-pass",
        publish_email="post@substack.example",
        from_email="founder@example.com",
        smtp_factory=FakeSMTP,
    )

    out = client.dry_run_text(subject="Draft", markdown_body="Body")

    assert "DRY RUN" in out
    assert "From: founder@example.com" in out
    assert "To: post@substack.example" in out
    assert "Subject: Draft" in out
    assert "Body" in out
    assert FakeSMTP.messages == []
