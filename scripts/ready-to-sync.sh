#!/usr/bin/env bash
# scripts/ready-to-sync.sh
#
# Single-command pre-sync gate. Runs every check Round 19b prompts 19–26
# introduced (and a few from before) and emits ONE pass/fail verdict.
# sync-to-github.sh invokes this before any push; on failure the sync
# refuses, and the operator is pointed at the structured report for the
# failing step.
#
# Gate steps (each must pass for the gate to pass):
#   1. Migration linearity + parity              (scripts/check_migration_linearity.py)
#   2. Import cycles + type contracts            (scripts/check_no_import_cycles.py && generate_api_types.py --check)
#   3. End-to-end smoke harness                  (scripts/smoke/run.sh)
#   4. Algorithm pipeline integration            (pytest tests/integration -m integration -q)
#   5. Env-var validation                        (noosphere env validate --mode full)
#   6. Sandbox + safety regression               (pytest tests/safety -q)
#   7. Bug-replay regression catalog             (pytest tests/regression -q)
#   8. CI workflow + tooling + doc freshness     (check_ci_workflow_integrity.py && check_doc_freshness.py)
#
# Flags:
#   --from N          resume from step N forward
#   --only N          run only step N
#   --skip N[,M,...]  bypass step(s); recorded in docs/verification/ready_to_sync_skips.log
#   --skip-reason "…" reason logged alongside skips (default: "unspecified")
#   --no-color        disable TTY colors
#   -h | --help       this message
#
# Exit codes:
#   0  every selected step passed (the gate PASSED)
#   1  one or more steps failed (the gate FAILED)
#   2  invalid arguments
#   130 SIGINT during a step
#
# The gate is read-only: it writes only its own structured log
# (docs/verification/ready_to_sync/<timestamp>/REPORT.md and per-step
# stdout/stderr) and, when --skip is used, an entry in
# docs/verification/ready_to_sync_skips.log.

set -u
set -o pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# ── colors ────────────────────────────────────────────────────────────────────
USE_COLOR=1
for arg in "$@"; do
  case "$arg" in --no-color) USE_COLOR=0 ;; esac
done
if [ -t 1 ] && [ "$USE_COLOR" = 1 ]; then
  C_RESET=$'\033[0m'; C_GREEN=$'\033[1;32m'; C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'; C_BLUE=$'\033[1;34m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""; C_DIM=""; C_BOLD=""
fi

# ── argument parsing ──────────────────────────────────────────────────────────
FROM_STEP=1
ONLY_STEP=""
SKIP_STEPS=""
SKIP_REASON="unspecified"
PRINT_HELP=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --from)
      [ "$#" -ge 2 ] || { echo "ready-to-sync: --from requires a value" >&2; exit 2; }
      FROM_STEP="$2"; shift 2 ;;
    --from=*)
      FROM_STEP="${1#--from=}"; shift ;;
    --only)
      [ "$#" -ge 2 ] || { echo "ready-to-sync: --only requires a value" >&2; exit 2; }
      ONLY_STEP="$2"; shift 2 ;;
    --only=*)
      ONLY_STEP="${1#--only=}"; shift ;;
    --skip)
      [ "$#" -ge 2 ] || { echo "ready-to-sync: --skip requires a value" >&2; exit 2; }
      SKIP_STEPS="$2"; shift 2 ;;
    --skip=*)
      SKIP_STEPS="${1#--skip=}"; shift ;;
    --skip-reason)
      [ "$#" -ge 2 ] || { echo "ready-to-sync: --skip-reason requires a value" >&2; exit 2; }
      SKIP_REASON="$2"; shift 2 ;;
    --skip-reason=*)
      SKIP_REASON="${1#--skip-reason=}"; shift ;;
    --no-color) shift ;;
    -h|--help) PRINT_HELP=1; shift ;;
    *) echo "ready-to-sync: unknown argument '$1' (try --help)" >&2; exit 2 ;;
  esac
done

if [ "$PRINT_HELP" = 1 ]; then
  sed -n '1,40p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

# Step metadata. Index matches the 1-based step number.
STEP_NAMES=(
  "migration-linearity"
  "import-cycles-and-types"
  "smoke-harness"
  "integration-pipeline"
  "env-validate"
  "safety-regression"
  "bug-replay"
  "ci-tooling-docs"
)
STEP_DESCS=(
  "Migration linearity + parity"
  "Import cycles + type contracts"
  "End-to-end smoke harness"
  "Algorithm pipeline integration"
  "Env-var validation"
  "Sandbox + safety regression"
  "Bug-replay regression catalog"
  "CI workflow + tooling + doc freshness"
)
# Per-step budget in seconds (over-budget = warning, not failure).
STEP_BUDGETS=(60 30 240 60 5 60 60 30)
TOTAL_STEPS=${#STEP_NAMES[@]}

validate_step_index() {
  local n="$1"
  case "$n" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$n" -ge 1 ] && [ "$n" -le "$TOTAL_STEPS" ]
}

if ! validate_step_index "$FROM_STEP"; then
  echo "ready-to-sync: --from must be 1..$TOTAL_STEPS" >&2; exit 2
fi
if [ -n "$ONLY_STEP" ] && ! validate_step_index "$ONLY_STEP"; then
  echo "ready-to-sync: --only must be 1..$TOTAL_STEPS" >&2; exit 2
fi

# Build the skip set (space-separated).
SKIP_SET=""
if [ -n "$SKIP_STEPS" ]; then
  # split on commas
  IFS=',' read -r -a _skips <<<"$SKIP_STEPS"
  for s in "${_skips[@]}"; do
    s="${s// /}"
    [ -z "$s" ] && continue
    if ! validate_step_index "$s"; then
      echo "ready-to-sync: --skip values must be 1..$TOTAL_STEPS (got '$s')" >&2
      exit 2
    fi
    SKIP_SET="$SKIP_SET $s "
  done
fi

is_skipped() {
  case "$SKIP_SET" in *" $1 "*) return 0 ;; esac
  return 1
}

# ── output directories ────────────────────────────────────────────────────────
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="docs/verification/ready_to_sync/${TIMESTAMP}"
mkdir -p "$REPORT_DIR"
REPORT_MD="$REPORT_DIR/REPORT.md"
SKIPS_LOG="docs/verification/ready_to_sync_skips.log"

# ── progress bar ──────────────────────────────────────────────────────────────
# Same style as run_prompts.sh: filled/empty blocks. Width is 8 cells.
make_progress_bar() {
  local cur="$1" tot="$2" width=8
  local filled=$(( cur * width / tot ))
  local empty=$(( width - filled ))
  local bar="" i
  for ((i=0; i<filled; i++)); do bar="${bar}▰"; done
  for ((i=0; i<empty;  i++)); do bar="${bar}▱"; done
  printf '%s' "$bar"
}

fmt_elapsed() {
  local s="$1"
  local m=$(( s / 60 ))
  local r=$(( s % 60 ))
  if [ "$m" -gt 0 ]; then
    printf '%dm %02ds' "$m" "$r"
  else
    printf '%ds' "$s"
  fi
}

# ── SIGINT handling ───────────────────────────────────────────────────────────
INTERRUPTED=0
CURRENT_STEP=0
on_sigint() {
  INTERRUPTED=1
  echo ""
  echo "${C_YELLOW}ready-to-sync: SIGINT received during step $CURRENT_STEP "\
"(${STEP_NAMES[CURRENT_STEP-1]:-unknown}).${C_RESET}"
  if [ "$CURRENT_STEP" -ge 1 ] && [ "$CURRENT_STEP" -le "$TOTAL_STEPS" ]; then
    echo "  Resume command:  ./scripts/ready-to-sync.sh --from ${CURRENT_STEP}"
  fi
  exit 130
}
trap on_sigint INT

# ── header ────────────────────────────────────────────────────────────────────
filter_summary="all steps"
if [ -n "$ONLY_STEP" ]; then
  filter_summary="only step $ONLY_STEP (${STEP_NAMES[ONLY_STEP-1]})"
elif [ "$FROM_STEP" -gt 1 ]; then
  filter_summary="from step $FROM_STEP forward"
fi
if [ -n "$SKIP_SET" ]; then
  filter_summary="$filter_summary; skipping:$SKIP_SET"
fi

bar70=$(printf '═%.0s' $(seq 1 70))
echo "${C_BOLD}${C_BLUE}${bar70}${C_RESET}"
echo "${C_BOLD}${C_BLUE}  READY-TO-SYNC GATE  ·  $TIMESTAMP  ·  $filter_summary${C_RESET}"
echo "${C_BOLD}${C_BLUE}${bar70}${C_RESET}"
echo ""

# ── step result tracking ──────────────────────────────────────────────────────
declare -a STEP_STATUS    # PASS / FAIL / SKIP / NOTRUN
declare -a STEP_ELAPSED
declare -a STEP_LOGS
declare -a STEP_OVERBUDGET
for ((i=0; i<TOTAL_STEPS; i++)); do
  STEP_STATUS[i]="NOTRUN"
  STEP_ELAPSED[i]=0
  STEP_LOGS[i]=""
  STEP_OVERBUDGET[i]=0
done

# Run a single step. Args: step_index (1-based), description, command string.
# Returns 0 on success, non-zero on failure.
run_step() {
  local idx="$1"; local desc="$2"; local cmd="$3"
  local i=$(( idx - 1 ))
  local budget="${STEP_BUDGETS[i]}"
  local logfile="$REPORT_DIR/step${idx}_${STEP_NAMES[i]}.log"
  STEP_LOGS[i]="$logfile"
  CURRENT_STEP="$idx"

  local bar
  bar=$(make_progress_bar "$((idx - 1))" "$TOTAL_STEPS")
  printf "${C_BOLD}[%d/%d]${C_RESET} %s  %-38s  ${C_DIM}(budget %ss)${C_RESET}\n" \
    "$idx" "$TOTAL_STEPS" "$bar" "$desc" "$budget"
  printf "       ${C_DIM}\$ %s${C_RESET}\n" "$cmd"

  local start end elapsed status
  start=$(date +%s)
  # Use bash -c so the gate script can express pipelines, &&, etc., per step.
  # Tee stdout+stderr to the per-step log so we keep an artifact AND the
  # operator sees streaming output in their terminal.
  bash -c "$cmd" >"$logfile" 2>&1
  status=$?
  end=$(date +%s)
  elapsed=$(( end - start ))
  STEP_ELAPSED[i]="$elapsed"

  local over=0
  if [ "$elapsed" -gt "$budget" ]; then over=1; STEP_OVERBUDGET[i]=1; fi

  if [ "$status" -eq 0 ]; then
    STEP_STATUS[i]="PASS"
    if [ "$over" = 1 ]; then
      printf "       ${C_GREEN}✓ PASS${C_RESET}  %s   ${C_YELLOW}(over budget by $((elapsed - budget))s)${C_RESET}\n\n" \
        "$(fmt_elapsed "$elapsed")"
    else
      printf "       ${C_GREEN}✓ PASS${C_RESET}  %s\n\n" "$(fmt_elapsed "$elapsed")"
    fi
    return 0
  else
    STEP_STATUS[i]="FAIL"
    printf "       ${C_RED}✗ FAIL${C_RESET}  %s   exit=%d   log: %s\n\n" \
      "$(fmt_elapsed "$elapsed")" "$status" "$logfile"
    # Inline the last 20 lines so the operator doesn't have to open the file
    # for the common case of a single obvious error.
    if [ -s "$logfile" ]; then
      echo "       ${C_DIM}--- last 20 lines of log ---${C_RESET}"
      tail -n 20 "$logfile" | sed 's/^/       | /'
      echo ""
    fi
    return "$status"
  fi
}

mark_skipped() {
  local idx="$1"
  local i=$(( idx - 1 ))
  STEP_STATUS[i]="SKIP"
  printf "${C_BOLD}[%d/%d]${C_RESET}            %-38s  ${C_YELLOW}○ SKIP${C_RESET}  (--skip)\n\n" \
    "$idx" "$TOTAL_STEPS" "${STEP_DESCS[i]}"
}

mark_notrun() {
  local idx="$1"
  local i=$(( idx - 1 ))
  STEP_STATUS[i]="NOTRUN"
  printf "${C_BOLD}[%d/%d]${C_RESET}            %-38s  ${C_DIM}─ NOT RUN${C_RESET}  (filter)\n\n" \
    "$idx" "$TOTAL_STEPS" "${STEP_DESCS[i]}"
}

# Decide whether a step is selected by the filter flags.
is_selected() {
  local idx="$1"
  if [ -n "$ONLY_STEP" ]; then
    [ "$idx" = "$ONLY_STEP" ]
    return $?
  fi
  [ "$idx" -ge "$FROM_STEP" ]
}

# ── log any skips to the audit log ────────────────────────────────────────────
log_skip_audit() {
  local idx="$1"
  local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local op="${USER:-unknown}"
  local head; head="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  local branch; branch="$(git branch --show-current 2>/dev/null || echo unknown)"
  mkdir -p "$(dirname "$SKIPS_LOG")"
  # JSON-Lines so the log is machine-readable. Keep one line per skip event.
  printf '{"ts":"%s","step":%d,"step_name":"%s","operator":"%s","branch":"%s","head":"%s","reason":"%s"}\n' \
    "$ts" "$idx" "${STEP_NAMES[idx-1]}" "$op" "$branch" "$head" \
    "$(printf '%s' "$SKIP_REASON" | sed 's/"/\\"/g')" \
    >> "$SKIPS_LOG"
}

# ── step command definitions ──────────────────────────────────────────────────
# Each step has its own command line. Kept inline so the script is self-
# contained and so a step can be re-run in isolation with --only N.
#
# Tests (and the rare emergency where the operator wants to swap out one
# step's invocation) can override any step by exporting
# READY_TO_SYNC_CMD_<N> in the environment. Production never sets these.
step_cmd() {
  local override
  override="$(eval "printf '%s' \"\${READY_TO_SYNC_CMD_$1:-}\"")"
  if [ -n "$override" ]; then
    printf '%s' "$override"
    return 0
  fi
  case "$1" in
    1) echo "python3 scripts/check_migration_linearity.py" ;;
    2) echo "python3 scripts/check_no_import_cycles.py && python3 scripts/generate_api_types.py --check" ;;
    3) echo "./scripts/smoke/run.sh" ;;
    4) echo "python3 -m pytest tests/integration -m integration -q --no-header" ;;
    5) echo "python3 -m noosphere.cli env validate --mode full" ;;
    6) echo "python3 -m pytest tests/safety -q --no-header" ;;
    7) echo "python3 -m pytest tests/regression -q --no-header" ;;
    8) echo "python3 scripts/check_ci_workflow_integrity.py && python3 scripts/check_doc_freshness.py" ;;
    *) return 1 ;;
  esac
}

# ── execute the gate ──────────────────────────────────────────────────────────
gate_status=0
first_failed_step=0
GATE_START=$(date +%s)

for ((step=1; step<=TOTAL_STEPS; step++)); do
  if ! is_selected "$step"; then
    mark_notrun "$step"
    continue
  fi
  if is_skipped "$step"; then
    mark_skipped "$step"
    log_skip_audit "$step"
    continue
  fi
  cmd="$(step_cmd "$step")"
  desc="${STEP_DESCS[step-1]}"
  if ! run_step "$step" "$desc" "$cmd"; then
    gate_status=1
    first_failed_step="$step"
    break  # halt immediately; do not "soldier on" through failures.
  fi
done

GATE_END=$(date +%s)
GATE_ELAPSED=$(( GATE_END - GATE_START ))

# ── report ────────────────────────────────────────────────────────────────────
write_report() {
  {
    echo "# Ready-to-Sync Gate Report"
    echo ""
    echo "- **Timestamp (UTC):** $TIMESTAMP"
    echo "- **Branch:** $(git branch --show-current 2>/dev/null || echo unknown)"
    echo "- **HEAD:** $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    echo "- **Operator:** ${USER:-unknown}"
    echo "- **Filter:** $filter_summary"
    echo "- **Elapsed:** $(fmt_elapsed "$GATE_ELAPSED")"
    if [ "$gate_status" = 0 ]; then
      echo "- **Verdict:** ✅ PASS"
    else
      echo "- **Verdict:** ❌ FAIL at step $first_failed_step (${STEP_NAMES[first_failed_step-1]})"
    fi
    echo ""
    echo "## Steps"
    echo ""
    echo "| # | Step | Status | Elapsed | Budget | Log |"
    echo "|---|------|--------|---------|--------|-----|"
    for ((i=0; i<TOTAL_STEPS; i++)); do
      local s=$(( i + 1 ))
      local status="${STEP_STATUS[i]}"
      local elapsed="$(fmt_elapsed "${STEP_ELAPSED[i]}")"
      local budget="${STEP_BUDGETS[i]}s"
      local log="${STEP_LOGS[i]:-—}"
      local emoji
      case "$status" in
        PASS)   emoji="✅ PASS" ;;
        FAIL)   emoji="❌ FAIL" ;;
        SKIP)   emoji="○ SKIP" ;;
        NOTRUN) emoji="─ NOTRUN" ;;
        *)      emoji="$status" ;;
      esac
      if [ "${STEP_OVERBUDGET[i]:-0}" = 1 ]; then
        emoji="$emoji (over)"
      fi
      [ -n "$log" ] && [ "$log" != "—" ] && log="\`$(basename "$log")\`"
      echo "| $s | ${STEP_DESCS[i]} | $emoji | $elapsed | $budget | $log |"
    done
    echo ""
    if [ -n "$SKIP_SET" ]; then
      echo "## Skips"
      echo ""
      echo "Reason recorded: \`$SKIP_REASON\`. See \`$SKIPS_LOG\` for the audit entry."
      echo ""
    fi
    # Aggregate over-budget warnings into a single block at the bottom.
    local any_over=0
    for ((i=0; i<TOTAL_STEPS; i++)); do
      if [ "${STEP_OVERBUDGET[i]:-0}" = 1 ]; then any_over=1; break; fi
    done
    if [ "$any_over" = 1 ]; then
      echo "## Perf warnings"
      echo ""
      for ((i=0; i<TOTAL_STEPS; i++)); do
        if [ "${STEP_OVERBUDGET[i]:-0}" = 1 ]; then
          local s=$(( i + 1 ))
          echo "- Step $s (${STEP_NAMES[i]}): $(fmt_elapsed "${STEP_ELAPSED[i]}") vs budget ${STEP_BUDGETS[i]}s"
        fi
      done
      echo ""
    fi
    if [ "$gate_status" != 0 ]; then
      echo "## Failure"
      echo ""
      echo "Step $first_failed_step (${STEP_NAMES[first_failed_step-1]}) failed."
      echo ""
      echo "Inspect the per-step log:"
      echo ""
      echo "    less ${STEP_LOGS[first_failed_step-1]}"
      echo ""
      echo "After fixing, resume the gate with:"
      echo ""
      echo "    ./scripts/ready-to-sync.sh --from $first_failed_step"
    fi
  } > "$REPORT_MD"
}
write_report

# ── final banner ──────────────────────────────────────────────────────────────
echo "${C_DIM}Report: $REPORT_MD${C_RESET}"
echo "${C_DIM}Per-step logs in: $REPORT_DIR${C_RESET}"
echo ""

if [ "$gate_status" = 0 ]; then
  bar=$(make_progress_bar "$TOTAL_STEPS" "$TOTAL_STEPS")
  echo "${C_GREEN}${C_BOLD}✓ Gate PASSED.  Safe to sync.${C_RESET}  $bar   $(fmt_elapsed "$GATE_ELAPSED")"
  exit 0
else
  echo "${C_RED}${C_BOLD}✗ Gate FAILED at step $first_failed_step:${C_RESET}  ${STEP_DESCS[first_failed_step-1]}"
  echo "  See:    ${STEP_LOGS[first_failed_step-1]}"
  echo "  Resume: ./scripts/ready-to-sync.sh --from $first_failed_step"
  exit 1
fi
