#!/usr/bin/env python3
"""Bulk re-extract every legacy Conclusion through the new
principle-shaped extractor. Writes proposed principles directly to
the Prisma `Conclusion` table — the same one the triage UI at
`/(authed)/extractor/re-extract` reads from.

WHAT IT DOES
============

1. Lists every Prisma `Conclusion` row whose `principleKind` is NULL
   (i.e., every legacy row that pre-dates the principle contract).
   By default this is the wide scope — every conclusion needs a
   principle-shaped rewrite. Use ``--first-person-only`` to restrict
   to the obviously-broken subset whose text opens with I / we / my /
   our (much faster, much narrower scope).
2. For each row, runs ``PrincipleExtractor`` against the conclusion's
   text. (Most legacy rows have no ``sourceSpan``; the conclusion
   text is the best available input.)
3. On PROPOSED: writes the proposed principle text into ``rationale``
   AND populates ``domainOfApplicability``, ``quantifiableProxies``,
   ``decisionExamples``, ``sourceSpan`` on the same row. Leaves
   ``principleKind`` NULL so the row stays in the triage queue until
   the founder accepts it via the UI.
4. On NO_PRINCIPLE_EXTRACTABLE: writes a sentinel string
   ``[NO_PRINCIPLE_EXTRACTABLE: <reason>]`` into ``rationale`` so
   re-runs of the script can skip already-refused rows.

WHAT IT DOES NOT DO
===================

* Touch live trading. The extractor is a read pipeline.
* Set ``principleKind`` directly — that would hide the row from the
  triage queue before the founder confirms.
* Overwrite ``text``. The new principle proposal goes into
  ``rationale``; the original conclusion text stays intact until the
  founder clicks Accept in the triage UI.

USAGE
=====

    cd ~/Desktop/Theseus
    source .venv-currents/bin/activate
    set -a
    source .vercel/.env.production.local   # gets ANTHROPIC_API_KEY
    source theseus-codex/.env              # ensures Prisma DATABASE_URL
    set +a

    # Print queue status (no LLM calls):
    python noosphere/scripts/reextract_corpus.py --status

    # Dry-run 5 random conclusions:
    python noosphere/scripts/reextract_corpus.py --sample 5 --dry-run

    # Full corpus rebuild, end-to-end (writes proposals to triage queue):
    python noosphere/scripts/reextract_corpus.py --all

    # Narrow scope — only first-person legacy:
    python noosphere/scripts/reextract_corpus.py --all --first-person-only

    # Single conclusion by id (for debugging):
    python noosphere/scripts/reextract_corpus.py --conclusion c_xxx --dry-run
"""

from __future__ import annotations

import argparse
import functools
import json
import random
import sys
import time

# Stream progress to stdout immediately so the user can `tail -f` the
# output of a long --all run rather than waiting for line buffering.
print = functools.partial(print, flush=True)  # noqa: A001 (intentional shadow)
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Bootstrap PYTHONPATH so the script works whether or not the package
# is pip-installed in the active venv.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))
sys.path.insert(0, str(_REPO_ROOT / "current_events_api"))


# ── Imports after sys.path bootstrap ───────────────────────────────────────
from noosphere.claim_extractor import PrincipleExtractor  # noqa: E402
from noosphere.conclusions import is_first_person_conclusion  # noqa: E402
from noosphere.models import Chunk  # noqa: E402
from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text  # noqa: E402


# ── Sentinel used to mark NO_PRINCIPLE_EXTRACTABLE refusals ────────────────
_REFUSAL_SENTINEL_PREFIX = "[NO_PRINCIPLE_EXTRACTABLE]"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkRow:
    id: str
    text: str
    source_span: Optional[str]
    rationale: Optional[str]
    organization_id: str


@dataclass
class ReextractResult:
    conclusion_id: str
    status: str   # "PROPOSED", "NO_PRINCIPLE_EXTRACTABLE", "SKIPPED", "ERROR"
    old_text: str = ""
    proposed_text: str = ""
    domain: str = ""
    proxies: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    refusal_reasons: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "conclusion_id": self.conclusion_id,
            "status": self.status,
            "old_text": self.old_text[:200],
            "proposed_text": self.proposed_text[:300],
            "domain": self.domain[:200],
            "proxies": self.proxies,
            "examples": self.examples,
            "refusal_reasons": self.refusal_reasons,
            "reason": self.reason,
        }


# ── Worklist queries against the Prisma Conclusion table ──────────────────
def fetch_worklist(
    engine: Any,
    *,
    first_person_only: bool,
    since: Optional[datetime],
    only_id: Optional[str],
    skip_already_refused: bool,
    skip_already_proposed: bool,
    from_id: Optional[str] = None,
) -> list[WorkRow]:
    """Fetch the re-extraction worklist from the Prisma Conclusion table.

    Auto-resume semantics (skip_already_refused + skip_already_proposed):

    * skip_already_refused: skip rows whose rationale starts with the
      NO_PRINCIPLE_EXTRACTABLE sentinel. These were processed by a
      previous run and the extractor returned no principle for them.
    * skip_already_proposed: skip rows whose ``domainOfApplicability``
      column is non-NULL. The script writes that column only when it
      successfully extracts a principle, so non-NULL = "already
      processed". Founder triage on the UI does not write that column,
      so this is a reliable script-side watermark.

    With both flags on (the default), running ``--all`` after a crash
    will pick up exactly where the previous run stopped: every row that
    was processed (either proposed-or-refused) is skipped; every row
    that wasn't is processed.

    ``from_id`` lets the operator manually resume from a specific
    conclusion id — useful if the operator knows the script crashed
    just before processing row X and wants to confirm by name.
    """
    where_parts = ['"principleKind" IS NULL']
    params: dict[str, Any] = {}
    if only_id is not None:
        where_parts.append('id = :id')
        params["id"] = only_id
    if since is not None:
        where_parts.append('"createdAt" >= :since')
        params["since"] = since
    if skip_already_refused:
        where_parts.append("(rationale IS NULL OR rationale NOT LIKE :refusal_pattern)")
        params["refusal_pattern"] = f"{_REFUSAL_SENTINEL_PREFIX}%"
    if skip_already_proposed:
        where_parts.append('("domainOfApplicability" IS NULL OR "domainOfApplicability" = \'\')')
    where_clause = " AND ".join(where_parts)
    # Stable order so manual --from resume points are deterministic.
    sql = text(
        f'SELECT id, text, "sourceSpan", rationale, "organizationId" '
        f'FROM "Conclusion" WHERE {where_clause} '
        f'ORDER BY "createdAt" ASC, id ASC'
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    out: list[WorkRow] = [
        WorkRow(
            id=r[0],
            text=r[1] or "",
            source_span=r[2],
            rationale=r[3],
            organization_id=r[4] or "",
        )
        for r in rows
    ]
    if first_person_only:
        out = [r for r in out if is_first_person_conclusion(r.text)]
    if from_id is not None:
        # Drop everything before the named row in the deterministic ordering.
        cut = next((i for i, r in enumerate(out) if r.id == from_id), None)
        if cut is None:
            print(f"WARNING: --from {from_id} not found in worklist; processing nothing.")
            return []
        out = out[cut:]
    return out


def status_summary(engine: Any) -> dict:
    with engine.connect() as conn:
        total = conn.execute(text('SELECT count(*) FROM "Conclusion"')).scalar()
        legacy = conn.execute(
            text('SELECT count(*) FROM "Conclusion" WHERE "principleKind" IS NULL')
        ).scalar()
        first_person_total = conn.execute(text('SELECT id, text FROM "Conclusion"')).fetchall()
        n_first_person = sum(1 for _, t in first_person_total if is_first_person_conclusion(t or ""))
        refused = conn.execute(
            text(
                'SELECT count(*) FROM "Conclusion" WHERE rationale LIKE :pat'
            ),
            {"pat": f"{_REFUSAL_SENTINEL_PREFIX}%"},
        ).scalar()
        principle_set = conn.execute(
            text('SELECT count(*) FROM "Conclusion" WHERE "principleKind" IS NOT NULL')
        ).scalar()
        proposed = conn.execute(
            text(
                'SELECT count(*) FROM "Conclusion" '
                'WHERE "principleKind" IS NULL '
                'AND "domainOfApplicability" IS NOT NULL '
                'AND "domainOfApplicability" != \'\''
            )
        ).scalar()
    return {
        "total_conclusions": total,
        "legacy_principleKind_null": legacy,
        "first_person_text": n_first_person,
        "marked_NO_PRINCIPLE_EXTRACTABLE": refused,
        "proposal_ready_for_triage": proposed,
        "already_principle_shaped": principle_set,
    }


# ── Extractor + Prisma writes ─────────────────────────────────────────────
def _chunk_from_row(row: WorkRow) -> Optional[Chunk]:
    """Build a Chunk the principle extractor can read.

    Prefer the verbatim source_span if the legacy row has one; fall
    back to the conclusion's own text otherwise. Both paths produce a
    valid (if asymmetric) extractor input.
    """
    text_in = (row.source_span or "").strip()
    if not text_in:
        text_in = (row.text or "").strip()
    if not text_in:
        return None
    return Chunk(
        artifact_id="",
        start_offset=0,
        end_offset=len(text_in),
        text=text_in,
        metadata={"reextract_source_conclusion_id": row.id},
    )


def _persist_proposal(
    engine: Any,
    row: WorkRow,
    proposed_text: str,
    domain: str,
    proxies: list[str],
    examples: list[str],
    source_span: Optional[str],
) -> None:
    """Write a fresh proposal into the Prisma Conclusion row.

    Targets columns: rationale, domainOfApplicability, quantifiableProxies,
    decisionExamples, sourceSpan, updatedAt. Leaves principleKind NULL
    so the row stays in the triage queue.
    """
    sql = text(
        'UPDATE "Conclusion" SET '
        '  rationale = :rationale, '
        '  "domainOfApplicability" = :domain, '
        '  "quantifiableProxies" = :proxies, '
        '  "decisionExamples" = :examples, '
        '  "sourceSpan" = COALESCE("sourceSpan", :source_span), '
        '  "updatedAt" = :ts '
        'WHERE id = :id'
    )
    with engine.connect() as conn:
        # domain is the script-side resume watermark. Persist None
        # rather than "" when the extractor returned no domain, so the
        # "skip already-proposed" filter (domain IS NOT NULL) works
        # correctly. An empty domain on a proposal is rare but possible.
        domain_value: Optional[str] = (domain or "").strip()[:300] or None
        conn.execute(sql, {
            "id": row.id,
            "rationale": proposed_text,
            "domain": domain_value,
            "proxies": json.dumps(proxies[:5]),
            "examples": json.dumps(examples[:3]),
            "source_span": source_span,
            "ts": _utcnow(),
        })
        conn.commit()


def _persist_refusal(engine: Any, row: WorkRow, reasons: list[str]) -> None:
    """Mark the row as refused so re-runs can skip it."""
    reason_text = "; ".join(r for r in reasons if r)[:500] or "extractor produced no principle"
    sentinel = f"{_REFUSAL_SENTINEL_PREFIX} {reason_text}"
    sql = text(
        'UPDATE "Conclusion" SET '
        '  rationale = :rationale, '
        '  "updatedAt" = :ts '
        'WHERE id = :id'
    )
    with engine.connect() as conn:
        conn.execute(sql, {
            "id": row.id,
            "rationale": sentinel,
            "ts": _utcnow(),
        })
        conn.commit()


def reextract_row(
    engine: Any,
    row: WorkRow,
    extractor: PrincipleExtractor,
    *,
    dry_run: bool,
) -> ReextractResult:
    # Note: we used to have an early-return here for rows already marked
    # NO_PRINCIPLE_EXTRACTABLE. That logic was redundant with the
    # worklist filter (which already skips refused rows by default), and
    # actively broken when ``--include-already-refused`` was passed —
    # it caused refused rows to skip the LLM call even when the user
    # explicitly asked for them to be re-processed. The right place to
    # decide whether to skip is in ``fetch_worklist``, not here.

    chunk = _chunk_from_row(row)
    if chunk is None:
        return ReextractResult(
            row.id, "SKIPPED",
            old_text=row.text,
            reason="row has neither source_span nor text",
        )
    try:
        proposals, refusals = extractor.extract(chunk)
    except Exception as exc:
        return ReextractResult(
            row.id, "ERROR",
            old_text=row.text,
            reason=repr(exc),
        )

    refusal_reasons = [r.reason or "no reason given" for r in refusals]

    if not proposals:
        if not dry_run:
            _persist_refusal(engine, row, refusal_reasons)
        return ReextractResult(
            row.id, "NO_PRINCIPLE_EXTRACTABLE",
            old_text=row.text,
            refusal_reasons=refusal_reasons,
            reason="extractor produced no principle-shaped rewrite for this span",
        )

    primary = proposals[0]
    proposed_text = primary.text.strip()
    domain = (primary.domain_of_applicability or "").strip()
    proxies = [p.strip() for p in (primary.quantifiable_proxies or []) if p.strip()][:5]
    examples = [e.strip() for e in (primary.decision_examples or []) if e.strip()][:3]
    source_span = primary.source_span

    if dry_run:
        return ReextractResult(
            row.id, "PROPOSED",
            old_text=row.text,
            proposed_text=proposed_text,
            domain=domain,
            proxies=proxies,
            examples=examples,
            refusal_reasons=refusal_reasons,
            reason=f"dry-run; {len(proposals)} proposal(s); not persisted",
        )

    _persist_proposal(engine, row, proposed_text, domain, proxies, examples, source_span)

    return ReextractResult(
        row.id, "PROPOSED",
        old_text=row.text,
        proposed_text=proposed_text,
        domain=domain,
        proxies=proxies,
        examples=examples,
        refusal_reasons=refusal_reasons,
        reason=f"{len(proposals)} proposal(s); wrote first to Prisma Conclusion row",
    )


# ── CLI ───────────────────────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--conclusion", type=str,
                   help="Re-extract a single conclusion by id")
    g.add_argument("--artifact", type=str,
                   help="(legacy alias for --conclusion)")
    g.add_argument("--sample", type=int,
                   help="Re-extract N random conclusions from the worklist")
    g.add_argument("--all", action="store_true",
                   help="Re-extract every conclusion in the worklist")
    g.add_argument("--status", action="store_true",
                   help="Print triage queue counts and exit")

    p.add_argument("--dry-run", action="store_true",
                   help="Print what would happen; persist nothing")
    p.add_argument("--first-person-only", action="store_true",
                   help="Narrow the worklist to legacy rows whose text opens "
                        "with I / we / my / our (the worst offenders).")
    p.add_argument("--since", type=str, default=None,
                   help="Restrict to conclusions created on or after YYYY-MM-DD")
    p.add_argument("--max", type=int, default=None,
                   help="Stop after re-extracting this many conclusions")
    p.add_argument("--sleep-between", type=float, default=0.0,
                   help="Pause (seconds) between conclusions; respects token budget")
    p.add_argument("--include-already-refused", action="store_true",
                   help="Re-process rows previously marked NO_PRINCIPLE_EXTRACTABLE. "
                        "Default behavior is to skip them.")
    p.add_argument("--include-already-proposed", action="store_true",
                   help="Re-process rows that already received a principle "
                        "proposal in an earlier run (i.e. domainOfApplicability "
                        "is non-NULL). Default behavior is to skip them, which "
                        "is what makes the script resume-on-crash.")
    p.add_argument("--reprocess-all", action="store_true",
                   help="Disable all auto-skip behavior — equivalent to setting "
                        "both --include-already-refused and "
                        "--include-already-proposed. Use only when intentionally "
                        "re-running the extractor over already-processed rows "
                        "(e.g. after editing the system prompt).")
    p.add_argument("--from", dest="from_id", type=str, default=None,
                   help="Resume from a specific conclusion id (advances past it "
                        "in the deterministic worklist order). Useful for manual "
                        "checkpointing.")

    args = p.parse_args(argv)

    store = Store.from_database_url(database_url_from_env())
    engine = store.engine

    if args.status:
        print(json.dumps(status_summary(engine), indent=2))
        return 0

    since: Optional[datetime] = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    only_id = args.conclusion or args.artifact or None
    from_id = args.from_id if args.from_id else None   # treat "" as None

    skip_refused = not (args.include_already_refused or args.reprocess_all)
    skip_proposed = not (args.include_already_proposed or args.reprocess_all)

    worklist = fetch_worklist(
        engine,
        first_person_only=args.first_person_only,
        since=since,
        only_id=only_id,
        skip_already_refused=skip_refused,
        skip_already_proposed=skip_proposed,
        from_id=from_id,
    )

    # Use `is not None` rather than truthiness so that --sample 0 and
    # --max 0 are honored as "process 0 rows" rather than silently
    # falling through to "process all rows" (the truthy-check would
    # treat 0 as "not set").
    if args.sample is not None and not only_id:
        random.shuffle(worklist)
        worklist = worklist[: args.sample]
    elif args.max is not None and not only_id:
        worklist = worklist[: args.max]

    print(f"\nplanning to re-extract {len(worklist)} conclusion(s); "
          f"first_person_only={args.first_person_only}; "
          f"dry_run={args.dry_run}; "
          f"skip_refused={skip_refused}; "
          f"skip_proposed={skip_proposed}")
    if not worklist:
        print("nothing to do under these filters.")
        # If skip filters were active, hint at how to widen.
        if skip_refused or skip_proposed:
            print("(if you intended to re-process already-handled rows, "
                  "re-run with --reprocess-all)")
        return 0

    extractor = PrincipleExtractor()

    results: list[ReextractResult] = []
    for i, row in enumerate(worklist, start=1):
        print(f"\n[{i}/{len(worklist)}] {row.id}")
        print(f"  old text: {(row.text or '')[:160]}")
        try:
            res = reextract_row(engine, row, extractor, dry_run=args.dry_run)
        except KeyboardInterrupt:
            print("\nInterrupted. Re-run later — already-persisted proposals are kept.")
            return 130
        except Exception as exc:
            res = ReextractResult(row.id, "ERROR", old_text=row.text, reason=repr(exc))
        print(f"  -> {res.status}")
        if res.proposed_text:
            print(f"     proposal: {res.proposed_text[:200]}")
        if res.domain:
            print(f"     domain  : {res.domain[:160]}")
        if res.reason:
            print(f"     reason  : {res.reason[:200]}")
        if res.refusal_reasons:
            for r in res.refusal_reasons[:1]:
                print(f"     refusal : {r[:200]}")
        results.append(res)
        if args.sleep_between > 0:
            time.sleep(args.sleep_between)

    out_path = Path("docs/runs") / f"reextract_corpus_{int(_utcnow().timestamp())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([r.to_dict() for r in results], indent=2))
    print(f"\nfull log: {out_path}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"summary: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
