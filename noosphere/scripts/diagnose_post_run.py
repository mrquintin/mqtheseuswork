"""Post-run diagnostic: figure out why proposals aren't visible in the UI.

Runs three checks:

1. Confirms which DATABASE_URL the script just wrote to, and compares it
   against the URL that Vercel uses for the deployed Next.js app. If
   they differ, the script's writes are landing in a DB that the
   deployment doesn't read from.

2. Counts how many rows in the Prisma `Conclusion` table currently
   have a script-written proposal (domainOfApplicability set) or
   refusal sentinel (rationale starts with the marker). Tells you
   whether persistence actually happened.

3. Pulls 5 sample rows with proposals and prints their full state, so
   you can eyeball what's there and compare to what the triage UI
   should be displaying.

Usage:
    python noosphere/scripts/diagnose_post_run.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text  # noqa: E402


_REFUSAL_SENTINEL_PREFIX = "[NO_PRINCIPLE_EXTRACTABLE]"


def _redact(url: str) -> str:
    """Hide the password but keep host/db visible for comparison."""
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def _read_db_url_from_file(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        m = re.match(r'^DATABASE_URL\s*=\s*"?([^"\n]+)"?\s*$', line)
        if m:
            return m.group(1)
    return None


def main() -> int:
    # ── Check 1: which DB does the script see vs. which DB is in Vercel ──
    print("=" * 70)
    print("CHECK 1: DATABASE_URL comparison")
    print("=" * 70)
    script_url = database_url_from_env()
    print(f"Script will use:      {_redact(script_url)}")
    for label, path in [
        ("theseus-codex/.env", _REPO_ROOT / "theseus-codex" / ".env"),
        ("current_events_api/.env", _REPO_ROOT / "current_events_api" / ".env"),
        (".vercel/.env.production.local",
         _REPO_ROOT / ".vercel" / ".env.production.local"),
        (".env", _REPO_ROOT / ".env"),
    ]:
        url = _read_db_url_from_file(path)
        if url is None:
            print(f"{label:40s} (file not found or no DATABASE_URL)")
        else:
            same = url.strip().rstrip("'\"") == script_url.strip().rstrip("'\"")
            marker = "MATCHES script" if same else "DIFFERS from script"
            print(f"{label:40s} {_redact(url)}  [{marker}]")
    print()

    # ── Check 2: did writes land? ────────────────────────────────────────
    print("=" * 70)
    print("CHECK 2: state of Prisma Conclusion table")
    print("=" * 70)
    store = Store.from_database_url(script_url)
    with store.engine.connect() as conn:
        total = conn.execute(text('SELECT count(*) FROM "Conclusion"')).scalar()
        with_proposal = conn.execute(
            text(
                'SELECT count(*) FROM "Conclusion" '
                'WHERE "domainOfApplicability" IS NOT NULL '
                'AND "domainOfApplicability" != \'\''
            )
        ).scalar()
        with_refusal = conn.execute(
            text('SELECT count(*) FROM "Conclusion" WHERE rationale LIKE :pat'),
            {"pat": f"{_REFUSAL_SENTINEL_PREFIX}%"},
        ).scalar()
        principle_kind_set = conn.execute(
            text('SELECT count(*) FROM "Conclusion" WHERE "principleKind" IS NOT NULL')
        ).scalar()
        first_person_with_proposal = conn.execute(
            text(
                'SELECT count(*) FROM "Conclusion" '
                'WHERE "principleKind" IS NULL '
                'AND "domainOfApplicability" IS NOT NULL '
                "AND (LOWER(text) LIKE 'i %' OR LOWER(text) LIKE 'i''%' "
                "  OR LOWER(text) LIKE 'we %' OR LOWER(text) LIKE 'we''%' "
                "  OR LOWER(text) LIKE 'my %' OR LOWER(text) LIKE 'our %')"
            )
        ).scalar()
    print(f"Total Conclusion rows                        : {total}")
    print(f"Rows w/ script-written proposal (domain set) : {with_proposal}")
    print(f"Rows w/ refusal sentinel in rationale        : {with_refusal}")
    print(f"Rows w/ principleKind set (already accepted) : {principle_kind_set}")
    print(f"FIRST-PERSON rows w/ proposal (triage UI's   ")
    print(f"  visible subset)                            : {first_person_with_proposal}")
    print()

    if with_proposal == 0 and with_refusal == 0:
        print("*** No script writes detected anywhere in the Conclusion table.")
        print("    Either the script didn't run, or it wrote to a different DB.")
        print("    Check CHECK 1 above for DATABASE_URL mismatches.")
        print()

    # ── Check 3: sample rows with proposals ──────────────────────────────
    print("=" * 70)
    print("CHECK 3: sample 5 rows with proposals (eyeball check)")
    print("=" * 70)
    with store.engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT id, text, rationale, "domainOfApplicability", '
            '       "quantifiableProxies", "decisionExamples", "updatedAt" '
            'FROM "Conclusion" '
            'WHERE "domainOfApplicability" IS NOT NULL '
            'AND "domainOfApplicability" != \'\' '
            'ORDER BY "updatedAt" DESC NULLS LAST '
            'LIMIT 5'
        )).fetchall()
    if not rows:
        print("No rows with proposals found — see CHECK 2 above.")
    else:
        for r in rows:
            print(f"\nid          : {r[0]}")
            print(f"text        : {(r[1] or '')[:120]}")
            print(f"rationale   : {(r[2] or '')[:200]}")
            print(f"domain      : {(r[3] or '')[:160]}")
            print(f"proxies     : {(r[4] or '')[:100]}")
            print(f"examples    : {(r[5] or '')[:100]}")
            print(f"updatedAt   : {r[6]}")

    print()
    print("=" * 70)
    print("Interpretation guide:")
    print("=" * 70)
    print("If CHECK 1 shows DATABASE_URL differs between script and Vercel:")
    print("  → Writes went to the wrong DB. The deployment can't see them.")
    print("    Fix: re-source the correct .env, re-run.")
    print()
    print("If CHECK 2 shows zero proposals/refusals:")
    print("  → Writes didn't happen at all. Script bug to debug.")
    print()
    print("If CHECK 2 shows proposals but the triage UI shows nothing:")
    print("  → Writes landed but UI is filtering them out. Most likely")
    print("    cause: triage UI only shows first-person rows (top 200 by")
    print("    createdAt, then JS-filtered to first-person). Non-first-person")
    print("    proposals are in the DB but invisible to that specific UI.")
    print("    The /principles public page won't show anything until you")
    print("    Accept proposals (which sets principleKind).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
