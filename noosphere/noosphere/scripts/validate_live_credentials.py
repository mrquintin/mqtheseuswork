#!/usr/bin/env python3
"""
Validate the env vars required for Theseus operation. Read-only.

USAGE: python -m noosphere.scripts.validate_live_credentials [--mode MODE] [--strict]

Modes: algorithms-only | synthesizer | full | live-trading.
``--mode`` overrides ``THESEUS_MODE``. Defaults to ``algorithms-only``.

The script never prints, logs, or returns any secret value. Each row
either succeeds (``OK``) or fails with a redacted reason
(``MISSING`` / ``OUT_OF_RANGE`` / ``INVALID_ENUM`` / ``TYPE_MISMATCH``).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from noosphere.core.env_validation import (
    Mode,
    Status,
    ValidationReport,
    parse_mode,
    validate_env,
)


_STATUS_GLYPH = {
    Status.PASS: "OK ",
    Status.OPTIONAL_MISSING: ".. ",
    Status.MISSING: "X  ",
    Status.OUT_OF_RANGE: "X  ",
    Status.INVALID_ENUM: "X  ",
    Status.TYPE_MISMATCH: "X  ",
}


def render_report(report: ValidationReport) -> str:
    lines: list[str] = []
    lines.append(f"Theseus env validation — mode: {report.mode.value}")
    lines.append("")
    name_w = max((len(r.var_name) for r in report.rows), default=20)
    for row in report.rows:
        glyph = _STATUS_GLYPH.get(row.status, "?  ")
        req = "REQ" if row.required else "opt"
        val = row.masked_value if row.masked_value is not None else "(unset)"
        lines.append(
            f"  {glyph} {row.var_name:<{name_w}}  {req}  "
            f"{row.status.value:<16} {val}"
        )
        if row.status not in {Status.PASS, Status.OPTIONAL_MISSING}:
            lines.append(f"        -> {row.message}")
    lines.append("")
    failures = report.failures()
    if failures:
        lines.append(
            f"RESULT: {len(failures)} required failures — refuse to boot."
        )
    else:
        green = sum(1 for r in report.rows if r.status == Status.PASS)
        lines.append(f"RESULT: {green}/{len(report.rows)} green.")
    lines.append(f"Mode determined: {report.mode.value}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m noosphere.scripts.validate_live_credentials",
        description="Validate Theseus environment variables (read-only).",
    )
    parser.add_argument(
        "--mode",
        default=None,
        help=(
            "Override THESEUS_MODE. One of: "
            "algorithms-only | synthesizer | full | live-trading."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit code 2 if any optional row is also missing.",
    )
    args = parser.parse_args(argv)

    raw_mode = args.mode or os.environ.get("THESEUS_MODE")
    try:
        mode = parse_mode(raw_mode)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    report = validate_env(mode)
    print(render_report(report))
    if report.failures():
        return 1
    if args.strict and any(
        r.status == Status.OPTIONAL_MISSING for r in report.rows
    ):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - direct CLI entry
    raise SystemExit(main())
