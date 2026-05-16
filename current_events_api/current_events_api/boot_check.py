"""Boot-time env-var check for Theseus services.

Run at FastAPI startup and at scheduler startup. If any var required
for the current MODE is missing/invalid, refuse to start with a loud,
structured message naming the var(s) — never a 500-on-first-request
mystery.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Mapping

from noosphere.core.env_validation import (
    Mode,
    Status,
    ValidationReport,
    parse_mode,
    validate_env,
)


log = logging.getLogger("theseus.boot_check")


class BootCheckError(SystemExit):
    """Raised when required env vars are missing — exits non-zero."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__(1)


def _emit_failure(report: ValidationReport, *, service: str) -> None:
    """Print one structured-log line plus a human-readable banner."""
    failures = report.failures()
    payload = {
        "event": "boot_check_failed",
        "service": service,
        "mode": report.mode.value,
        "missing": [
            {
                "var": r.var_name,
                "status": r.status.value,
                "message": r.message,
            }
            for r in failures
        ],
    }
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.stderr.write(
        f"\n!! Theseus {service} refused to start: "
        f"{len(failures)} required env vars failed in mode "
        f"{report.mode.value!r}.\n"
    )
    for r in failures:
        sys.stderr.write(f"   - {r.var_name}: {r.status.value} ({r.message})\n")
    sys.stderr.write("   Fix the variables above and restart.\n\n")


def _emit_success(report: ValidationReport, *, service: str) -> None:
    payload = {
        "event": "boot_check_ok",
        "service": service,
        "mode": report.mode.value,
        "vars_validated": len(report.rows),
    }
    log.info("boot_check_ok", extra={"payload": payload})
    sys.stderr.write(json.dumps(payload) + "\n")


def _emit_skip(*, service: str, reason: str) -> None:
    """Loud, structured note that the check was bypassed.

    Used by the smoke harness and other test-mode contexts that boot
    the app without a real env. The log line names the bypass so a
    production deployment cannot silently inherit it (operators watch
    for `boot_check_skipped` in startup logs).
    """
    payload = {
        "event": "boot_check_skipped",
        "service": service,
        "reason": reason,
    }
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.stderr.write(
        f"\n.. Theseus {service} boot check SKIPPED ({reason}). "
        "This is only safe in test / smoke contexts. If you see this "
        "in production, the smoke harness leaked into a prod deploy.\n\n"
    )


def run_boot_check(
    *,
    service: str,
    env: Mapping[str, str] | None = None,
    exit_on_failure: bool = True,
) -> ValidationReport | None:
    """Validate env vars for the current MODE.

    If anything required fails and ``exit_on_failure`` is True, write
    a structured error to stderr and raise ``BootCheckError`` (exits
    with code 1). Otherwise return the report for the caller to act on.

    The check is bypassed (returns None and logs a loud skip line)
    when the calling environment sets ``THESEUS_BOOT_CHECK=skip``.
    This is the smoke-harness / test-mode escape hatch. Production
    deployments never set that var; the loud log line ensures a
    misconfigured prod deploy doesn't silently inherit the bypass.
    """
    src = env or os.environ
    if src.get("THESEUS_BOOT_CHECK", "").strip().lower() == "skip":
        reason = src.get("THESEUS_BOOT_CHECK_REASON", "THESEUS_BOOT_CHECK=skip")
        _emit_skip(service=service, reason=reason)
        return None

    raw_mode = src.get("THESEUS_MODE")
    try:
        mode = parse_mode(raw_mode)
    except ValueError as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "event": "boot_check_failed",
                    "service": service,
                    "error": str(exc),
                }
            )
            + "\n"
        )
        if exit_on_failure:
            raise SystemExit(1) from exc
        # Fall back to default mode.
        mode = Mode.ALGORITHMS_ONLY

    report = validate_env(mode, env=env)
    if report.failures():
        _emit_failure(report, service=service)
        if exit_on_failure:
            raise BootCheckError(report)
        return report
    _emit_success(report, service=service)
    return report
