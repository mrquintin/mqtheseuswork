#!/usr/bin/env bash
#
# backfill_aim_method_fit.sh — operational harness for Round 18 prompt 31.
#
# Re-scores every existing Conclusion's Aim-Method Fit under the deterministic
# five-level rubric introduced in prompt 31
# (noosphere/noosphere/inquiry/aim_method_fit.py). It does NOT re-implement
# any scoring logic — the rubric lives in noosphere.inquiry.aim_method_fit,
# the MQS scorer in noosphere.evaluation.mqs, and the DB plumbing is reused
# from noosphere.cli_commands.mqs. This script is the run wrapper, the
# pre-flight gate, the tier-drop triage memo, and the report writer.
#
#   A. Pre-flight  — confirm the modules import, the rubric is loadable, and
#                    the Codex store is reachable with the MQS schema. A hard
#                    failure GATES the run; nothing is written.
#   B. Re-score    — for every Conclusion that already has an MQS row,
#                    recompute the full MQS (only Aim-Method Fit and the
#                    composite move; the other sub-scorers are unchanged and
#                    deterministic under the stub judge). Compare the new
#                    composite tier against the stored one.
#   C. Triage      — any conclusion whose composite DROPS A TIER on re-score
#                    is an entry in the founder's queue. These are written
#                    into the report under "Founder queue".
#   D. Apply       — with --write, upsert the recomputed MethodologyQualityScore
#                    rows (idempotent on conclusionId). Default is dry-run:
#                    nothing is persisted.
#   E. Publish     — append a summary to
#                    docs/runs/aim_method_fit_backfill_<stamp>.md
#                    (or ..._dryrun.md for a dry run).
#
# Usage:
#   backfill_aim_method_fit.sh [options]
#
# Options:
#   --organization-slug SLUG   Restrict to one tenant (default: all orgs)
#   --limit N                  Max conclusions to scan (default: 5000)
#   --write                    Persist recomputed MQS rows (default: dry-run)
#   -h, --help                 Show this help
#
# Exit codes:
#   0  completed (or dry-run completed)
#   2  bad usage
#   3  pre-flight GATED — run did not start; nothing was written
#
set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOOSPHERE_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$NOOSPHERE_DIR")"
RUNS_DIR="$REPO_ROOT/docs/runs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DRIVER="${TMPDIR:-/tmp}/aim_method_fit_backfill_driver_$$.py"
trap 'rm -f "$DRIVER"' EXIT

# ── Defaults / args ────────────────────────────────────────────────────
ORG_SLUG=""
LIMIT="5000"
WRITE="0"

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --organization-slug) ORG_SLUG="${2:-}"; shift 2 ;;
    --limit) LIMIT="${2:-}"; shift 2 ;;
    --write) WRITE="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "$WRITE" = "1" ]; then
  REPORT="$RUNS_DIR/aim_method_fit_backfill_${STAMP}.md"
  MODE="write"
else
  REPORT="$RUNS_DIR/aim_method_fit_backfill_${STAMP}_dryrun.md"
  MODE="dry-run"
fi

export PYTHONPATH="$NOOSPHERE_DIR${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"

echo "── Aim-Method Fit backfill (${MODE}) ──────────────────────────────"
echo "stamp:        $STAMP"
echo "organization: ${ORG_SLUG:-<all>}"
echo "limit:        $LIMIT"
echo "report:       $REPORT"
echo

# ── A. Pre-flight ──────────────────────────────────────────────────────
echo "A. Pre-flight…"
if ! "$PYTHON" - <<'PREFLIGHT'
import sys
try:
    from noosphere.inquiry.aim_method_fit import WORKED_EXAMPLES, score_aim_method_fit
    from noosphere.inquiry.question_typology import QUESTION_TYPES
    from noosphere.evaluation.mqs import composite_tier, tier_rank, score_conclusion
    from noosphere.cli_commands.mqs import (
        _open_codex, _profiles_for_conclusion, _forecast_count_for_conclusion,
        _dissent_count, _upsert_mqs_row,
    )
except Exception as exc:  # noqa: BLE001
    print(f"  IMPORT FAILED: {exc}", file=sys.stderr)
    sys.exit(1)
# The rubric must be self-consistent before we score anything against it.
bad = []
for we in WORKED_EXAMPLES:
    r = score_aim_method_fit(we.question_text, we.topic_hint, [we.method_view()])
    if r.level != we.level or r.worked_example_agrees is False:
        bad.append(we.id)
if bad:
    print(f"  RUBRIC INCONSISTENT: worked examples disagree: {bad}", file=sys.stderr)
    sys.exit(1)
try:
    conn, _ = _open_codex()
    conn.close()
except Exception as exc:  # noqa: BLE001
    print(f"  CODEX UNREACHABLE: {exc}", file=sys.stderr)
    sys.exit(1)
print(f"  modules import OK; {len(WORKED_EXAMPLES)} worked examples consistent; "
      f"{len(QUESTION_TYPES)} question types; Codex reachable.")
PREFLIGHT
then
  echo "  pre-flight GATED — run did not start; nothing was written." >&2
  exit 3
fi
echo

# ── B–E. Re-score, triage, apply, publish ──────────────────────────────
echo "B. Re-scoring…"
cat > "$DRIVER" <<'DRIVER_PY'
import json
import os
import sys
from datetime import datetime, timezone

from noosphere.cli_commands.mqs import (
    _open_codex, _profiles_for_conclusion, _forecast_count_for_conclusion,
    _dissent_count, _upsert_mqs_row,
)
from noosphere.evaluation.mqs import (
    MqsInput, StubMqsJudge, composite_tier, score_conclusion, tier_rank,
)

ORG_SLUG = os.environ.get("AMF_ORG_SLUG", "")
LIMIT = int(os.environ.get("AMF_LIMIT", "5000"))
WRITE = os.environ.get("AMF_WRITE", "0") == "1"
REPORT = os.environ["AMF_REPORT"]
STAMP = os.environ["AMF_STAMP"]

conn, real_dict_cursor = _open_codex()
try:
    cur = conn.cursor(cursor_factory=real_dict_cursor)

    organization_id = None
    if ORG_SLUG:
        cur.execute('SELECT id FROM "Organization" WHERE slug = %s', (ORG_SLUG,))
        row = cur.fetchone()
        if not row:
            print(f"  organization slug not found: {ORG_SLUG}", file=sys.stderr)
            sys.exit(2)
        organization_id = row["id"] if isinstance(row, dict) else row[0]

    # Only conclusions that ALREADY have an MQS row — this is a re-score.
    cur.execute(
        '''SELECT c.id, c."organizationId", c.text, c.rationale, c."topicHint",
                  c."dissentClaimIds",
                  m.composite AS old_composite,
                  m."aimMethodFit" AS old_aim_method_fit
             FROM "Conclusion" c
             JOIN "MethodologyQualityScore" m ON m."conclusionId" = c.id
            WHERE (%s IS NULL OR c."organizationId" = %s)
            ORDER BY c."createdAt" ASC
            LIMIT %s''',
        (organization_id, organization_id, LIMIT),
    )
    rows = list(cur.fetchall())

    judge = StubMqsJudge()
    now = datetime.now(timezone.utc)

    rescored = 0
    skipped_no_profile = 0
    amf_changed = 0
    tier_drops = []   # founder queue
    tier_gains = 0

    for c in rows:
        cid = c["id"]
        org_id = c["organizationId"]
        profiles = _profiles_for_conclusion(
            cur, organization_id=org_id, conclusion_id=cid
        )
        if not profiles:
            skipped_no_profile += 1
            continue

        new = score_conclusion(
            MqsInput(
                conclusion_id=cid,
                conclusion_text=c.get("text") or "",
                rationale=c.get("rationale") or "",
                topic_hint=c.get("topicHint") or "",
                profiles=profiles,
                forecast_count=_forecast_count_for_conclusion(cur, conclusion_id=cid),
                has_check_back_date=False,
                dissent_claim_count=_dissent_count(c.get("dissentClaimIds")),
            ),
            judge=judge,
            model_name="stub",
        )
        rescored += 1

        old_amf = float(c.get("old_aim_method_fit") or 0.0)
        new_amf = float(new.aim_method_fit.score)
        if abs(new_amf - old_amf) > 1e-9:
            amf_changed += 1

        old_composite = float(c.get("old_composite") or 0.0)
        old_tier = composite_tier(old_composite)
        new_tier = composite_tier(new.composite)
        if tier_rank(new_tier) < tier_rank(old_tier):
            tier_drops.append(
                {
                    "conclusion_id": cid,
                    "organization_id": org_id,
                    "old_composite": round(old_composite, 4),
                    "new_composite": round(float(new.composite), 4),
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                    "old_aim_method_fit": round(old_amf, 4),
                    "new_aim_method_fit": round(new_amf, 4),
                    "fit_level": new.aim_method_fit.evidence.get("level"),
                    "fit_relation": new.aim_method_fit.evidence.get("relation"),
                    "question_type": new.aim_method_fit.evidence.get("question_type"),
                }
            )
        elif tier_rank(new_tier) > tier_rank(old_tier):
            tier_gains += 1

        if WRITE:
            _upsert_mqs_row(
                cur, organization_id=org_id, conclusion_id=cid,
                score=new, now=now,
            )

    if WRITE:
        conn.commit()
    else:
        conn.rollback()

    summary = {
        "stamp": STAMP,
        "mode": "write" if WRITE else "dry-run",
        "organization": ORG_SLUG or "<all>",
        "scanned": len(rows),
        "rescored": rescored,
        "skipped_no_profile": skipped_no_profile,
        "aim_method_fit_changed": amf_changed,
        "tier_drops": len(tier_drops),
        "tier_gains": tier_gains,
    }

    # ── Report ─────────────────────────────────────────────────────────
    lines = []
    lines.append(f"# Aim-Method Fit backfill — {STAMP}")
    lines.append("")
    lines.append(f"Mode: **{summary['mode']}**  ·  Organization: {summary['organization']}")
    lines.append("")
    lines.append("Re-scores every Conclusion's Aim-Method Fit under the prompt-31 "
                 "deterministic rubric (`noosphere.inquiry.aim_method_fit`).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Conclusions scanned: {summary['scanned']}")
    lines.append(f"- Re-scored: {summary['rescored']}")
    lines.append(f"- Skipped (no methodology profile): {summary['skipped_no_profile']}")
    lines.append(f"- Aim-Method Fit sub-score changed: {summary['aim_method_fit_changed']}")
    lines.append(f"- Composite tier drops (→ founder queue): {summary['tier_drops']}")
    lines.append(f"- Composite tier gains: {summary['tier_gains']}")
    lines.append("")
    lines.append("## Founder queue — conclusions that dropped a composite tier")
    lines.append("")
    if not tier_drops:
        lines.append("_No conclusion dropped a tier on re-score._")
    else:
        lines.append("Each row needs founder review: the prompt-31 rubric scored "
                     "its Aim-Method Fit lower than the prior MQS, enough to move "
                     "the gating composite down a tier.")
        lines.append("")
        lines.append("| Conclusion | Org | Composite | Tier | Aim-Method Fit | Fit level | Relation | Question type |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for d in tier_drops:
            lines.append(
                f"| `{d['conclusion_id']}` | `{d['organization_id']}` "
                f"| {d['old_composite']} → {d['new_composite']} "
                f"| {d['old_tier']} → {d['new_tier']} "
                f"| {d['old_aim_method_fit']} → {d['new_aim_method_fit']} "
                f"| {d['fit_level']} | {d['fit_relation']} | {d['question_type']} |"
            )
    lines.append("")
    if not WRITE:
        lines.append("_Dry run — no MethodologyQualityScore rows were written. "
                     "Re-run with `--write` to persist._")
        lines.append("")

    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2))
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
DRIVER_PY

AMF_ORG_SLUG="$ORG_SLUG" AMF_LIMIT="$LIMIT" AMF_WRITE="$WRITE" \
AMF_REPORT="$REPORT" AMF_STAMP="$STAMP" \
  "$PYTHON" "$DRIVER"

echo
echo "Report written: $REPORT"
if [ "$WRITE" = "1" ]; then
  echo "MethodologyQualityScore rows updated."
else
  echo "Dry run — no rows written. Re-run with --write to persist."
fi
