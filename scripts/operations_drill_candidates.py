#!/usr/bin/env python3
"""Print a quarterly-drill sheet: N alerts at random with their procedures.

The drill is the meta-method applied to the runbook itself. We pick a
small random subset of the alerts the firm has documented, print the
trigger and the first-five-minute response for each, and leave blank
"gap log" lines for the operator to fill in while walking the procedure.

Usage:

    python scripts/operations_drill_candidates.py [--count 3] [--seed N]

The seed is reported in the header so a drill is reproducible (and so
two operators can drill the same alerts independently and then compare
notes). Omitting ``--seed`` lets ``random.SystemRandom`` choose one and
print it.

This script reads ``docs/operations/Runbook.md``. It does not modify any
file; the operator is expected to copy the printed sheet into a new
postmortem file (``docs/operations/postmortems/YYYY-MM-DD_drill-…md``)
and fill in the gap-log entries during the drill.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNBOOK_PATH = REPO_ROOT / "docs" / "operations" / "Runbook.md"
ALERT_RESPONSE_HEADING = "## Alert response"

_H3_RE = re.compile(r"^### +(?P<id>[A-Za-z0-9_\-]+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class AlertEntry:
    name: str
    body: str

    def field(self, label: str) -> str:
        """Return the first body block whose bullet starts with ``- **<label>:**``.

        The block ends at the next top-level bullet (``- **…``) or at the
        next heading. Returns the body verbatim, stripped — the prose
        in the runbook is the source of truth, no reformatting here.
        """
        pattern = re.compile(
            rf"^\s*-\s+\*\*{re.escape(label)}:\*\*(?P<rest>.*?)(?=^\s*-\s+\*\*|^\s*###|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(self.body)
        if m is None:
            return "(not specified in runbook)"
        return m.group("rest").strip()


def _alert_section(md: str) -> str:
    start = md.find(ALERT_RESPONSE_HEADING)
    if start == -1:
        return ""
    end = md.find("\n## ", start + len(ALERT_RESPONSE_HEADING))
    return md[start:end] if end != -1 else md[start:]


def parse_alerts(md: str) -> list[AlertEntry]:
    """Return alert entries in the runbook's source order."""
    section = _alert_section(md)
    if not section:
        return []
    heads = list(_H3_RE.finditer(section))
    out: list[AlertEntry] = []
    for i, m in enumerate(heads):
        name = m.group("id")
        body_start = m.end()
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(section)
        out.append(AlertEntry(name=name, body=section[body_start:body_end].strip()))
    return out


def pick_candidates(
    alerts: list[AlertEntry], count: int, seed: int
) -> list[AlertEntry]:
    """Deterministic random sample. Stable across Python versions for a
    given (alerts_order, count, seed)."""
    if count >= len(alerts):
        return list(alerts)
    rng = random.Random(seed)
    return rng.sample(alerts, count)


_FENCE = "─" * 64


def render_sheet(picks: list[AlertEntry], seed: int) -> str:
    today = datetime.now(tz=timezone.utc).date().isoformat()
    lines: list[str] = []
    lines.append(_FENCE)
    lines.append("Quarterly runbook drill")
    lines.append(_FENCE)
    lines.append(f"Date generated  : {today}")
    lines.append(f"Random seed     : {seed}")
    lines.append(f"Alerts picked   : {len(picks)}")
    lines.append("")
    lines.append("Protocol:")
    lines.append(
        "  1. For each alert below, WITHOUT re-reading the runbook,"
    )
    lines.append(
        "     write the first five minutes you would actually walk."
    )
    lines.append(
        "  2. Then compare your walk to the runbook excerpt printed"
    )
    lines.append(
        "     here. Log gaps under the 'Gap log' bullets."
    )
    lines.append(
        "  3. File the drill as docs/operations/postmortems/"
        f"{today}_drill-<short-slug>.md (severity: drill)."
    )
    lines.append("")
    for i, alert in enumerate(picks, start=1):
        lines.append(_FENCE)
        lines.append(f"[{i}/{len(picks)}]  {alert.name}")
        lines.append(_FENCE)
        lines.append("")
        lines.append("Trigger (from runbook):")
        for ln in alert.field("Trigger").splitlines():
            lines.append(f"  {ln}")
        lines.append("")
        lines.append("Severity:")
        for ln in alert.field("Severity").splitlines():
            lines.append(f"  {ln}")
        lines.append("")
        lines.append("First five minutes (from runbook):")
        for ln in alert.field("First five minutes").splitlines():
            lines.append(f"  {ln}")
        lines.append("")
        lines.append("Your walk (write before re-reading the runbook):")
        lines.append("  -")
        lines.append("  -")
        lines.append("  -")
        lines.append("")
        lines.append("Gap log (use labels: untested | stale | vague | missing):")
        lines.append("  -")
        lines.append("  -")
        lines.append("")
    lines.append(_FENCE)
    lines.append(
        "Done. Copy this sheet into a postmortem file and commit it; "
        "drills are auditable too."
    )
    lines.append(_FENCE)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="number of alerts to pick (default 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed for reproducibility; if omitted, one is "
        "drawn from SystemRandom and printed in the header.",
    )
    parser.add_argument(
        "--runbook",
        type=Path,
        default=RUNBOOK_PATH,
        help="path to Runbook.md (default: docs/operations/Runbook.md)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="just list the alert names found in the runbook, then exit.",
    )
    args = parser.parse_args(argv)

    if not args.runbook.is_file():
        print(f"runbook missing: {args.runbook}", file=sys.stderr)
        return 2

    md = args.runbook.read_text(encoding="utf-8")
    alerts = parse_alerts(md)
    if not alerts:
        print(
            f"no '### <alert>' headings found under '{ALERT_RESPONSE_HEADING}' "
            f"in {args.runbook}",
            file=sys.stderr,
        )
        return 2

    if args.list:
        for a in alerts:
            print(a.name)
        return 0

    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else random.SystemRandom().randint(
        0, 2**31 - 1
    )
    picks = pick_candidates(alerts, args.count, seed)
    sys.stdout.write(render_sheet(picks, seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
