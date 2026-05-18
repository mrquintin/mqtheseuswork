"""Bulk-promote all script-generated principle proposals into the
canonical `text` field of their Conclusion rows. Also clean up the
NO_PRINCIPLE_EXTRACTABLE sentinel strings written to `rationale` on
refused rows.

WHY THIS EXISTS
===============

`reextract_corpus.py --all` wrote the new principle-shaped proposals
into `Conclusion.rationale`, not `Conclusion.text`. That kept the
proposals visible in the triage UI as agent suggestions, but it
meant the downstream pipelines (distillation, search, /principles
visibility) still see the original first-person text in `text`.

This script flips the corpus to the new state, irreversibly:

  * For every row where the script wrote a proposal (i.e.
    `domainOfApplicability IS NOT NULL`):
      - `text` is replaced with the proposed principle text
        (currently in `rationale`).
      - `rationale` is cleared to empty string.
      - `principleKind` is set to the default 'HEURISTIC' (override
        per-row later if needed).
      - `normalizedText` is recomputed from the new text so dedup
        and search still work.
      - `updatedAt` is bumped.

  * For every row marked NO_PRINCIPLE_EXTRACTABLE (i.e. rationale
    starts with the sentinel):
      - `rationale` is cleared to empty string.
      - `updatedAt` is bumped.
      - Original `text` is left intact — the row stays in the corpus
        as a legacy conclusion, just no longer falsely flagged as
        having an agent proposal.

This script does NOT touch `principleKind` on refused rows, so the
distillation pipeline will still ignore them as legacy non-principle
material.

USAGE
=====

    # Sanity check — print what would change, write nothing:
    python noosphere/scripts/promote_proposals.py --dry-run

    # Commit the promotion + cleanup:
    python noosphere/scripts/promote_proposals.py --commit

    # After this completes, run distillation to produce Principles:
    noosphere principles distill --threshold 0.18 --min-cluster-size 4

DEFAULTS
========

* principleKind defaults to 'HEURISTIC'. To use a different default,
  pass --default-kind RULE (or CRITERION, MECHANISM, DEFINITION,
  FORMULA, ALGORITHM).
* The script is NOT reversible. If you want a snapshot first, run:
    pg_dump --table=public.\\"Conclusion\\" $DATABASE_URL > backup.sql
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text  # noqa: E402


_REFUSAL_SENTINEL_PREFIX = "[NO_PRINCIPLE_EXTRACTABLE]"
_VALID_KINDS = {"RULE", "CRITERION", "MECHANISM", "HEURISTIC",
                "DEFINITION", "FORMULA", "ALGORITHM"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(s: str) -> str:
    """Match Prisma's `normalizedText` recipe:
    LOWER(TRIM(REGEXP_REPLACE(text, '\\s+', ' ')))"""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Show what would change; commit nothing.")
    g.add_argument("--commit", action="store_true",
                   help="Actually commit the changes to the database.")

    p.add_argument("--default-kind", default="HEURISTIC",
                   choices=sorted(_VALID_KINDS),
                   help="Default principleKind for promoted rows "
                        "(default: HEURISTIC).")
    p.add_argument("--promote-only", action="store_true",
                   help="Only promote proposals; do NOT clean up refusal "
                        "sentinels. Use if you want to handle refusals "
                        "separately.")
    p.add_argument("--clean-refusals-only", action="store_true",
                   help="Only clean up refusal sentinels; do NOT promote "
                        "proposals. Use if you want to handle promotion "
                        "separately.")

    args = p.parse_args(argv)
    if args.promote_only and args.clean_refusals_only:
        print("ERROR: --promote-only and --clean-refusals-only are exclusive.")
        return 2

    do_promote = not args.clean_refusals_only
    do_clean = not args.promote_only

    store = Store.from_database_url(database_url_from_env())

    with store.engine.connect() as conn:
        # ── Count what we're about to touch ─────────────────────────────
        n_to_promote = conn.execute(text(
            'SELECT count(*) FROM "Conclusion" '
            'WHERE "domainOfApplicability" IS NOT NULL '
            "AND \"domainOfApplicability\" != '' "
            'AND "principleKind" IS NULL'
        )).scalar()
        n_to_clean = conn.execute(text(
            'SELECT count(*) FROM "Conclusion" WHERE rationale LIKE :pat'
        ), {"pat": f"{_REFUSAL_SENTINEL_PREFIX}%"}).scalar()

        print("=" * 70)
        print(f"Rows queued for promotion (proposal → text): {n_to_promote}")
        print(f"Rows queued for refusal-sentinel cleanup    : {n_to_clean}")
        print(f"Default principleKind for promoted rows     : {args.default_kind}")
        print(f"Will promote                                : {do_promote}")
        print(f"Will clean refusals                         : {do_clean}")
        print("=" * 70)

        # ── Show samples before committing ──────────────────────────────
        if do_promote and n_to_promote > 0:
            print("\nSample of 3 rows about to be promoted:")
            rows = conn.execute(text(
                'SELECT id, text, rationale, "domainOfApplicability" '
                'FROM "Conclusion" '
                'WHERE "domainOfApplicability" IS NOT NULL '
                "AND \"domainOfApplicability\" != '' "
                'AND "principleKind" IS NULL '
                "LIMIT 3"
            )).fetchall()
            for r in rows:
                print(f"\n  id     : {r[0]}")
                print(f"  OLD text   : {(r[1] or '')[:140]}")
                print(f"  NEW text   : {(r[2] or '')[:140]}")
                print(f"  domain     : {(r[3] or '')[:120]}")

        if do_clean and n_to_clean > 0:
            print("\nSample of 3 rows about to have rationale cleared:")
            rows = conn.execute(text(
                'SELECT id, text, rationale FROM "Conclusion" '
                "WHERE rationale LIKE :pat LIMIT 3"
            ), {"pat": f"{_REFUSAL_SENTINEL_PREFIX}%"}).fetchall()
            for r in rows:
                print(f"\n  id            : {r[0]}")
                print(f"  text (kept)   : {(r[1] or '')[:140]}")
                print(f"  rationale to  : (cleared from){(r[2] or '')[:100]}...")

        # ── Dry-run exits here ──────────────────────────────────────────
        if args.dry_run:
            print("\n--dry-run: no writes performed.")
            return 0

        # ── COMMIT PATH ─────────────────────────────────────────────────
        # Promotion: must be done row-by-row because normalizedText is
        # derived from the new text per-row. We use a single transaction
        # for the whole batch so a mid-batch failure rolls back cleanly.

        promoted = 0
        cleaned = 0

        backup_records: list[dict] = []

        if do_promote and n_to_promote > 0:
            print(f"\nPromoting {n_to_promote} rows...")
            to_promote = conn.execute(text(
                'SELECT id, text, rationale, "domainOfApplicability" '
                'FROM "Conclusion" '
                'WHERE "domainOfApplicability" IS NOT NULL '
                "AND \"domainOfApplicability\" != '' "
                'AND "principleKind" IS NULL'
            )).fetchall()

            for r in to_promote:
                row_id = r[0]
                old_text = r[1] or ""
                new_text = (r[2] or "").strip()
                domain = r[3] or ""
                if not new_text:
                    print(f"  skip {row_id} — rationale is empty")
                    continue
                norm = _normalize_text(new_text)
                # Sidecar record: lets you recover the original text per
                # row without needing a full pg_dump. Written to
                # docs/runs/promotion_<ts>.json after the loop completes.
                backup_records.append({
                    "id": row_id,
                    "old_text": old_text,
                    "new_text": new_text,
                    "domain": domain,
                    "principleKind_set_to": args.default_kind,
                })
                conn.execute(text(
                    'UPDATE "Conclusion" SET '
                    '  text = :new_text, '
                    '  "normalizedText" = :norm, '
                    "  rationale = '', "
                    '  "principleKind" = :kind, '
                    '  "updatedAt" = :ts '
                    'WHERE id = :id'
                ), {
                    "id": row_id,
                    "new_text": new_text,
                    "norm": norm,
                    "kind": args.default_kind,
                    "ts": _utcnow(),
                })
                promoted += 1
                if promoted % 50 == 0:
                    print(f"  ... promoted {promoted}/{n_to_promote}")

        if do_clean and n_to_clean > 0:
            print(f"\nClearing refusal sentinels on {n_to_clean} rows...")
            result = conn.execute(text(
                'UPDATE "Conclusion" SET '
                "  rationale = '', "
                '  "updatedAt" = :ts '
                'WHERE rationale LIKE :pat'
            ), {
                "pat": f"{_REFUSAL_SENTINEL_PREFIX}%",
                "ts": _utcnow(),
            })
            cleaned = result.rowcount

        conn.commit()
        print(f"\nCommitted: {promoted} promoted, {cleaned} cleaned.")

        # Write the sidecar backup BEFORE post-commit verification so a
        # later crash doesn't lose the original text values.
        if backup_records:
            backup_path = (_REPO_ROOT / "docs" / "runs" /
                           f"promotion_{int(_utcnow().timestamp())}.json")
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(json.dumps(backup_records, indent=2))
            print(f"\nSidecar backup of pre-promotion text: {backup_path}")
            print(f"  (use this to recover original `text` per row if needed)")

        # ── Post-commit verification ────────────────────────────────────
        print("\nPost-commit state check:")
        new_pkind_set = conn.execute(text(
            'SELECT count(*) FROM "Conclusion" '
            'WHERE "principleKind" IS NOT NULL'
        )).scalar()
        residual_sentinels = conn.execute(text(
            'SELECT count(*) FROM "Conclusion" WHERE rationale LIKE :pat'
        ), {"pat": f"{_REFUSAL_SENTINEL_PREFIX}%"}).scalar()
        print(f"  Conclusion rows with principleKind set : {new_pkind_set}")
        print(f"  Conclusion rows still carrying sentinel: {residual_sentinels}")

    print("\nNext step: run `noosphere principles distill` to cluster the")
    print("now-rebuilt conclusions into Principle entities. Those Principles")
    print("are what the /principles page actually displays.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
