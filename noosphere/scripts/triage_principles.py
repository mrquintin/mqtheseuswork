"""Triage script for draft Principles. Flips drafts to accepted (and
thus public on /principles) or rejected.

For drafts in the Prisma `Principle` table to appear on /principles:
  - status         = 'accepted'
  - publicVisible  = true
  - domainsJson    != '[]'  (already satisfied by every script-produced draft)

This script handles the first two flips. Rejected drafts are kept in
the table as a record but never become public.

USAGE
=====

    # List every pending draft (id + first 100 chars of text):
    python noosphere/scripts/triage_principles.py list

    # Show full details for one draft:
    python noosphere/scripts/triage_principles.py show prn_xxx

    # Accept one or more drafts:
    python noosphere/scripts/triage_principles.py accept prn_xxx prn_yyy

    # Accept ALL pending drafts (bulk):
    python noosphere/scripts/triage_principles.py accept --all

    # Reject a draft (kept in DB, never appears on /principles):
    python noosphere/scripts/triage_principles.py reject prn_xxx

    # Walk drafts interactively, one at a time:
    python noosphere/scripts/triage_principles.py interactive
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text  # noqa: E402

print = functools.partial(print, flush=True)  # noqa: A001


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_drafts(engine, *, status: str = "draft") -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT id, text, "domainsJson", "convictionScore", '
            '       "domainBreadth", "clusterConclusionIds", status '
            'FROM "Principle" '
            'WHERE status = :status '
            'ORDER BY "convictionScore" DESC NULLS LAST'
        ), {"status": status}).fetchall()
    return [
        {
            "id": r[0],
            "text": r[1] or "",
            "domains": json.loads(r[2] or "[]"),
            "conviction": float(r[3] or 0),
            "domain_breadth": int(r[4] or 0),
            "cluster_size": len(json.loads(r[5] or "[]")),
            "status": r[6],
        }
        for r in rows
    ]


def _fetch_one(engine, principle_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text(
            'SELECT id, text, "domainsJson", "convictionScore", '
            '       "domainBreadth", "clusterConclusionIds", '
            '       "citedConclusionIds", status, "triageReason", '
            '       "createdAt" '
            'FROM "Principle" WHERE id = :id'
        ), {"id": principle_id}).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "text": row[1] or "",
        "domains": json.loads(row[2] or "[]"),
        "conviction": float(row[3] or 0),
        "domain_breadth": int(row[4] or 0),
        "cluster_conclusion_ids": json.loads(row[5] or "[]"),
        "cited_conclusion_ids": json.loads(row[6] or "[]"),
        "status": row[7],
        "triage_reason": row[8] or "",
        "created_at": row[9],
    }


def _accept(engine, principle_id: str) -> bool:
    """Flip a draft to status='accepted', publicVisible=true."""
    with engine.connect() as conn:
        ts = _utcnow()
        result = conn.execute(text(
            'UPDATE "Principle" SET '
            "  status = 'accepted', "
            '  "publicVisible" = true, '
            '  "reviewedAt" = :ts, '
            '  "publishedAt" = :ts, '
            '  "updatedAt" = :ts '
            "WHERE id = :id AND status = 'draft'"
        ), {"id": principle_id, "ts": ts})
        conn.commit()
        return result.rowcount > 0


def _reject(engine, principle_id: str) -> bool:
    with engine.connect() as conn:
        ts = _utcnow()
        result = conn.execute(text(
            'UPDATE "Principle" SET '
            "  status = 'rejected', "
            '  "publicVisible" = false, '
            '  "reviewedAt" = :ts, '
            '  "updatedAt" = :ts '
            "WHERE id = :id AND status = 'draft'"
        ), {"id": principle_id, "ts": ts})
        conn.commit()
        return result.rowcount > 0


def cmd_list(engine) -> int:
    drafts = _fetch_drafts(engine)
    if not drafts:
        print("No pending drafts.")
        return 0
    print(f"\n{len(drafts)} draft Principle(s) pending triage "
          f"(ordered by conviction):\n")
    for d in drafts:
        domains_str = ", ".join(d["domains"][:3]) or "(no domains)"
        if len(d["domains"]) > 3:
            domains_str += f" (+{len(d['domains']) - 3} more)"
        print(f"  {d['id']}  conv={d['conviction']:.3f}  "
              f"breadth={d['domain_breadth']}  "
              f"cluster={d['cluster_size']}")
        print(f"    domains: {domains_str}")
        print(f"    text   : {d['text'][:120]}{'...' if len(d['text']) > 120 else ''}")
        print()
    return 0


def cmd_show(engine, principle_id: str) -> int:
    d = _fetch_one(engine, principle_id)
    if d is None:
        print(f"No Principle with id {principle_id}")
        return 1
    print(f"\nid                  : {d['id']}")
    print(f"status              : {d['status']}")
    print(f"conviction          : {d['conviction']:.3f}")
    print(f"domain breadth      : {d['domain_breadth']}")
    print(f"cluster size        : {len(d['cluster_conclusion_ids'])}")
    print(f"created at          : {d['created_at']}")
    print(f"triage reason       : {d['triage_reason'] or '(none)'}")
    print(f"\ndomains:")
    for dom in d["domains"]:
        print(f"  - {dom}")
    print(f"\ncited conclusion ids ({len(d['cited_conclusion_ids'])}):")
    for cid in d["cited_conclusion_ids"][:5]:
        print(f"  - {cid}")
    if len(d["cited_conclusion_ids"]) > 5:
        print(f"  ... and {len(d['cited_conclusion_ids']) - 5} more")
    print(f"\ntext:\n  {d['text']}\n")
    return 0


def cmd_accept(engine, ids: list[str], accept_all: bool) -> int:
    if accept_all:
        drafts = _fetch_drafts(engine)
        ids = [d["id"] for d in drafts]
        if not ids:
            print("No pending drafts to accept.")
            return 0
        print(f"About to accept all {len(ids)} pending draft(s).")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return 1
    accepted = 0
    failed = []
    for pid in ids:
        ok = _accept(engine, pid)
        if ok:
            accepted += 1
            print(f"  accepted: {pid}")
        else:
            failed.append(pid)
            print(f"  FAILED  : {pid} (not in draft status, or doesn't exist)")
    print(f"\n{accepted} accepted; {len(failed)} failed.")
    return 0 if not failed else 1


def cmd_reject(engine, ids: list[str]) -> int:
    rejected = 0
    for pid in ids:
        ok = _reject(engine, pid)
        if ok:
            rejected += 1
            print(f"  rejected: {pid}")
        else:
            print(f"  FAILED  : {pid}")
    print(f"\n{rejected} rejected.")
    return 0


def cmd_interactive(engine) -> int:
    drafts = _fetch_drafts(engine)
    if not drafts:
        print("No pending drafts.")
        return 0
    print(f"\n{len(drafts)} pending draft(s). Press 'q' to quit at any prompt.\n")
    for i, d in enumerate(drafts, start=1):
        print(f"\n{'=' * 70}")
        print(f"[{i}/{len(drafts)}] {d['id']}  conv={d['conviction']:.3f}")
        print(f"domains: {', '.join(d['domains'])}")
        print(f"cluster size: {d['cluster_size']}")
        print(f"\n{d['text']}")
        print(f"\n{'=' * 70}")
        while True:
            choice = input("  [a]ccept / [r]eject / [s]kip / [q]uit: ").strip().lower()
            if choice in ("a", "accept"):
                _accept(engine, d["id"])
                print("  -> accepted")
                break
            if choice in ("r", "reject"):
                _reject(engine, d["id"])
                print("  -> rejected")
                break
            if choice in ("s", "skip", ""):
                print("  -> skipped (left as draft)")
                break
            if choice in ("q", "quit"):
                print("Quitting. Remaining drafts left as draft.")
                return 0
            print("  (unrecognized — type a / r / s / q)")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List pending draft Principles.")
    show_p = sub.add_parser("show", help="Show full details of one draft.")
    show_p.add_argument("id")
    acc_p = sub.add_parser("accept", help="Accept one or more drafts.")
    acc_p.add_argument("ids", nargs="*")
    acc_p.add_argument("--all", action="store_true",
                       help="Accept every pending draft (asks for confirmation).")
    rej_p = sub.add_parser("reject", help="Reject one or more drafts.")
    rej_p.add_argument("ids", nargs="+")
    sub.add_parser("interactive",
                   help="Walk drafts one at a time, prompting accept/reject/skip.")

    args = p.parse_args(argv)
    store = Store.from_database_url(database_url_from_env())
    engine = store.engine

    if args.cmd == "list":
        return cmd_list(engine)
    if args.cmd == "show":
        return cmd_show(engine, args.id)
    if args.cmd == "accept":
        if not args.all and not args.ids:
            print("ERROR: pass at least one id, or --all.")
            return 2
        return cmd_accept(engine, args.ids, args.all)
    if args.cmd == "reject":
        return cmd_reject(engine, args.ids)
    if args.cmd == "interactive":
        return cmd_interactive(engine)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
