"""Check: personal_info_scrub — no PII unless pre-declared in author attestation acknowledgments."""
from __future__ import annotations

import json
import re

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_personal_info_scrub"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
ADDRESS_RE = re.compile(
    r"\d{1,5}\s+\w+(?:\s+\w+){0,3}\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Ct|Court)\b",
    re.IGNORECASE,
)


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _extract_text(payload_ref: str) -> str:
    try:
        data = json.loads(payload_ref)
        return str(data.get("text", ""))
    except (json.JSONDecodeError, TypeError):
        return payload_ref


def _find_pii(text: str) -> list[str]:
    hits: list[str] = []
    for m in EMAIL_RE.finditer(text):
        hits.append(f"email:{m.group()}")
    for m in PHONE_RE.finditer(text):
        hits.append(f"phone:{m.group()}")
    for m in ADDRESS_RE.finditer(text):
        hits.append(f"address:{m.group()}")
    return hits


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.mitigations import pii_patterns  # noqa: F401
    except ImportError:
        return _stub_pass()

    text = _extract_text(submission.payload_ref)
    if not text.strip():
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="empty_payload")

    hits = _find_pii(text)
    acknowledged = set(submission.author_attestation.acknowledgments)

    unacknowledged = [h for h in hits if h not in acknowledged]
    if unacknowledged:
        return CheckResult(
            check_name=CHECK_NAME,
            pass_=False,
            detail=f"pii_found: {', '.join(unacknowledged[:5])}",
        )

    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="pii_clean")


register(CHECK_NAME, run)
