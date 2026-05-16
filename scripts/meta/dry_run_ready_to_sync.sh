#!/usr/bin/env bash
# scripts/meta/dry_run_ready_to_sync.sh
#
# Exercise the ready-to-sync gate's plumbing end-to-end WITHOUT running
# the (slow, side-effectful) real step commands. Every step is overridden
# to ``true`` via READY_TO_SYNC_CMD_<N>, so the gate's argument parsing,
# header/banner, per-step run_step block, REPORT.md emitter, and final
# verdict all execute. The script then:
#
#   1. Asserts the gate exited 0.
#   2. Parses the per-step rows out of REPORT.md.
#   3. Confirms each row has the expected structured fields:
#        { step_name, duration_s, status ∈ {PASS,WARN,FAIL}, details? }
#   4. Emits a JSON-Lines summary to stdout (one object per step) plus a
#      single verdict object.
#
# Usage:
#   scripts/meta/dry_run_ready_to_sync.sh                # uses a fresh tempdir
#   scripts/meta/dry_run_ready_to_sync.sh /path/to/workdir
#
# Exit codes:
#   0  every step ran AND every row passed schema validation
#   1  gate exited non-zero, or a row failed schema validation
#   2  bad arguments / environment

set -u
set -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/ready-to-sync.sh"

if [ ! -x "$GATE" ]; then
  echo "dry_run_ready_to_sync: gate not executable: $GATE" >&2
  exit 2
fi

WORKDIR="${1:-}"
if [ -z "$WORKDIR" ]; then
  WORKDIR="$(mktemp -d -t ready_to_sync_dryrun.XXXXXX)"
  cleanup() { rm -rf "$WORKDIR"; }
  trap cleanup EXIT
else
  mkdir -p "$WORKDIR"
fi

# Initialise an isolated git repo so the gate's `git rev-parse` succeeds.
(
  cd "$WORKDIR"
  git init -q
  git -c user.email=dry@dry -c user.name=dry \
      commit -q --allow-empty -m "dry-run init"
)

# Override every step to a no-op `true`. The gate's plumbing still runs.
DRY_ENV=(
  "READY_TO_SYNC_CMD_1=true"
  "READY_TO_SYNC_CMD_2=true"
  "READY_TO_SYNC_CMD_3=true"
  "READY_TO_SYNC_CMD_4=true"
  "READY_TO_SYNC_CMD_5=true"
  "READY_TO_SYNC_CMD_6=true"
  "READY_TO_SYNC_CMD_7=true"
  "READY_TO_SYNC_CMD_8=true"
)

GATE_LOG="$WORKDIR/.gate.stdout"
GATE_ERR="$WORKDIR/.gate.stderr"

(
  cd "$WORKDIR"
  env "${DRY_ENV[@]}" "$GATE" --no-color
) > "$GATE_LOG" 2> "$GATE_ERR"
GATE_RC=$?

if [ "$GATE_RC" -ne 0 ]; then
  echo "{\"event\":\"dry_run_failed\",\"reason\":\"gate_exited_$GATE_RC\"}" >&2
  cat "$GATE_LOG" >&2
  exit 1
fi

# Find the freshest REPORT.md the gate emitted.
REPORT_DIR="$(find "$WORKDIR/docs/verification/ready_to_sync" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n1)"
if [ -z "$REPORT_DIR" ] || [ ! -f "$REPORT_DIR/REPORT.md" ]; then
  echo "{\"event\":\"dry_run_failed\",\"reason\":\"no_report_md_emitted\"}" >&2
  exit 1
fi

# Validate the schema. The current gate writes REPORT.md as a Markdown
# table with columns:
#   | # | Step | Status | Elapsed | Budget | Log |
# This dry-run translates each row into the JSON shape the prompt asks
# for: { step_name, duration_s, status, details? }.
python3 - "$REPORT_DIR/REPORT.md" <<'PY'
import json, re, sys
report = open(sys.argv[1], "r", encoding="utf-8").read()
rows: list[dict] = []
# Skip the header + separator lines; pick rows that start with `| <int> |`.
row_re = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M)
for m in row_re.finditer(report):
    idx, step, status, elapsed, budget, log = m.groups()
    # Reduce the gate's emoji-status to {PASS, FAIL, WARN}.
    norm = "FAIL"
    s = status.upper()
    if "PASS" in s and "OVER" in s:
        norm = "WARN"  # over-budget but passed
    elif "PASS" in s:
        norm = "PASS"
    elif "FAIL" in s:
        norm = "FAIL"
    elif "SKIP" in s or "NOTRUN" in s:
        norm = "WARN"
    # Parse duration like "2s" or "1m 03s" → seconds.
    secs = 0
    mm = re.match(r"(?:(\d+)m\s*)?(\d+)s", elapsed.strip())
    if mm:
        m_, s_ = mm.groups()
        secs = (int(m_) if m_ else 0) * 60 + int(s_)
    row = {
        "step_name": step.strip(),
        "duration_s": secs,
        "status": norm,
    }
    log_clean = log.strip().strip("`")
    if log_clean and log_clean != "—":
        row["details"] = log_clean
    rows.append(row)

if not rows:
    print(json.dumps({"event": "dry_run_failed", "reason": "no_rows_parsed"}))
    sys.exit(1)

errors: list[str] = []
allowed = {"PASS", "WARN", "FAIL"}
for r in rows:
    if not r.get("step_name"):
        errors.append("missing step_name")
    if not isinstance(r.get("duration_s"), int):
        errors.append("duration_s not int: %r" % r.get("duration_s"))
    if r.get("status") not in allowed:
        errors.append("bad status: %r" % r.get("status"))

if errors:
    print(json.dumps({"event": "dry_run_failed", "reason": "schema", "errors": errors}))
    sys.exit(1)

# Emit one JSON-Lines record per row.
for r in rows:
    print(json.dumps(r, sort_keys=True))
# Verdict object at the end.
print(json.dumps({
    "event": "dry_run_ok",
    "steps": len(rows),
    "all_pass": all(r["status"] == "PASS" for r in rows),
}, sort_keys=True))
PY
PY_RC=$?

if [ "$PY_RC" -ne 0 ]; then
  echo "dry_run_ready_to_sync: schema validation failed" >&2
  exit 1
fi

exit 0
