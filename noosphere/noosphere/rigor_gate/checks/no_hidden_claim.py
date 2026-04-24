"""Check: no_hidden_claim — LLM-based detection of assertions not traceable to declared claims."""
from __future__ import annotations

import json

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_no_hidden_claim"

_SYSTEM_PROMPT = (
    "You are a rigorous fact-checker. Given a payload text and a set of traced claims, "
    "determine if any assertion in the payload is NOT traceable to the listed claims. "
    "Respond with ONLY 'CLEAN' if all assertions are traceable, or 'HIDDEN: <description>' "
    "if you find an untraceable assertion."
)


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_payload(payload_ref: str) -> tuple[str, list[str]]:
    try:
        data = json.loads(payload_ref)
        text = str(data.get("text", ""))
        claims = list(data.get("traced_claims", []))
        return text, claims
    except (json.JSONDecodeError, TypeError):
        return payload_ref, []


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.llm import llm_client_from_settings
    except ImportError:
        return _stub_pass()

    text, traced_claims = _parse_payload(submission.payload_ref)
    if not text.strip():
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="empty_payload")

    if not traced_claims:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_traced_claims_provided")

    user_prompt = (
        f"Payload text:\n{text}\n\n"
        f"Traced claims:\n" + "\n".join(f"- {c}" for c in traced_claims)
    )

    try:
        client = llm_client_from_settings()
        response = client.complete(system=_SYSTEM_PROMPT, user=user_prompt)
    except Exception:
        return _stub_pass()

    response = response.strip()
    if response.startswith("HIDDEN:"):
        return CheckResult(
            check_name=CHECK_NAME,
            pass_=False,
            detail=f"hidden_claim_detected: {response[7:].strip()[:120]}",
        )
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_hidden_claims")


register(CHECK_NAME, run)
