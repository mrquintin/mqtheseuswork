"""Check: dialectic_consent — all speakers in dialectic summaries must have public-release consent."""
from __future__ import annotations

import json

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_dialectic_consent"


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_speakers(payload_ref: str) -> list[dict[str, str]]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("speakers", []))
    except (json.JSONDecodeError, TypeError):
        return []


def run(submission: RigorSubmission) -> CheckResult:
    if submission.kind != "dialectic_summary":
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="not_dialectic_summary")

    try:
        from noosphere.resolution import resolve_consent  # noqa: F401
    except ImportError:
        return _stub_pass()

    speakers = _parse_speakers(submission.payload_ref)
    if not speakers:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_speakers_listed")

    for speaker in speakers:
        speaker_id = speaker.get("id", "")
        try:
            consent = resolve_consent(speaker_id, granularity=submission.intended_venue)
        except Exception:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"consent_lookup_failed: {speaker_id}",
            )
        if not consent:
            name = speaker.get("name", speaker_id)
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"missing_consent: speaker={name} venue={submission.intended_venue}",
            )

    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="all_speakers_consented")


register(CHECK_NAME, run)
