#!/usr/bin/env python3
"""CI lint: fail if any email template embeds a tracking pixel.

The firm sends follow-digest and double-opt-in confirmation emails
without any open-tracking mechanism: no 1x1 pixel ``<img>``, no
``<iframe>``, no remote ``.gif``/``.png`` beacon, no Resend
``open_tracking`` flag. Open rate is measured only through the
voluntary opt-in "I read this" link (see
``noosphere/social/digest_builder.py`` and
``theseus-codex/src/app/api/public/digest-ack/[token]/route.ts``).

This script scans every file that builds or renders an email body and
fails the build if a tracking mechanism is present. Reusable
templates are the regression vector — a "small UI polish" PR that
adds an inline image to the digest body would silently revive
tracking. Catching it here is cheap; catching it after a send is not.

Run:
    python scripts/check_no_tracking_pixels.py [--root REPO_ROOT]

Exit code 0 = clean. Exit code 1 = at least one forbidden pattern.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that participate in building an outbound email body. Add new
# templates here when the firm adds new email kinds.
MAIL_PATHS: tuple[str, ...] = (
    "noosphere/noosphere/social/digest_builder.py",
    "theseus-codex/src/lib/subscriptions.ts",
    "theseus-codex/src/lib/responsesEmail.ts",
    "theseus-codex/src/lib/mail.ts",
)

# Patterns that indicate an open-tracking mechanism. The disclaimer
# string ("does not embed tracking pixels") obviously must remain
# allowed; it's matched explicitly so the lint doesn't flag itself.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"<\s*img\b", "<img> tag in an email body (potential tracking pixel)"),
    (r"<\s*iframe\b", "<iframe> tag in an email body"),
    (r"\b1x1\b", "1x1 marker (classic tracking pixel sizing)"),
    (r"open[_-]?track", "open-tracking flag/setting"),
    (r"open[_-]?rate[_-]?pixel", "explicit open-rate pixel reference"),
    (r"pixel\.gif|tracking\.gif|beacon\.gif", "tracking beacon image"),
    (r"<\s*meta[^>]+http-equiv=['\"]?refresh", "meta refresh redirect"),
)

ALLOWED_PHRASES: tuple[str, ...] = (
    "does not embed tracking pixels",
    "no tracking pixels",
    "rejects tracking pixels",
    "tracking pixel",  # bare token in prose/comments is fine
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    line: str
    pattern: str
    explanation: str


def _line_is_allowed(line: str) -> bool:
    lowered = line.lower()
    return any(phrase in lowered for phrase in ALLOWED_PHRASES)


def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    compiled = [(re.compile(p, re.IGNORECASE), p, expl) for p, expl in FORBIDDEN_PATTERNS]
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _line_is_allowed(line):
            continue
        for rx, raw, expl in compiled:
            if rx.search(line):
                findings.append(
                    Finding(
                        path=path,
                        line_no=line_no,
                        line=line.strip()[:200],
                        pattern=raw,
                        explanation=expl,
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="extra file to scan; may be passed more than once",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    targets = [root / p for p in MAIL_PATHS]
    targets.extend(Path(p).resolve() for p in args.path)

    all_findings: list[Finding] = []
    for target in targets:
        all_findings.extend(scan_file(target))

    if not all_findings:
        print(
            f"check_no_tracking_pixels: OK — scanned {len(targets)} file(s); "
            "no tracking-pixel patterns detected."
        )
        return 0

    print("check_no_tracking_pixels: FAILED", file=sys.stderr)
    for f in all_findings:
        rel = f.path.relative_to(root) if f.path.is_relative_to(root) else f.path
        print(
            f"  {rel}:{f.line_no}: {f.explanation}\n"
            f"    pattern: {f.pattern}\n"
            f"    line: {f.line}",
            file=sys.stderr,
        )
    print(
        "\nTracking pixels and remote beacons are forbidden in firm email. "
        "Open rate is measured via the opt-in 'I read this' link only. "
        "If you genuinely need to render an image in an email, update this "
        "lint with an explicit allowlist entry and a one-line rationale.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
