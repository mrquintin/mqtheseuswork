#!/bin/bash
# Round 10 — sequentially run every prompt in coding_prompts/ via the
# OpenAI Codex CLI (`codex exec`). Streams each session's stdout to the
# terminal AND saves the full text log to .codex_runs/<timestamp>_<prompt>.log
# for review.
#
# This script uses the installed `codex` CLI's existing auth (your ChatGPT/
# Codex subscription) — it does NOT read any OpenAI API key. If you have not
# yet signed in, run `codex auth login` once before invoking this script.
#
# Usage:
#   ./run_prompts.sh                       # run all prompts, halt on first failure
#   ./run_prompts.sh --from 5              # start at prompt 05
#   ./run_prompts.sh --to 9                # stop after prompt 09 (inclusive)
#   ./run_prompts.sh --from 3 --to 9       # 03 through 09 inclusive
#   ./run_prompts.sh --only 09             # run only prompt 09
#   ./run_prompts.sh --model gpt-5-codex   # override the model
#   ./run_prompts.sh --continue            # keep going on prompt failure
#   ./run_prompts.sh --dry-run             # show plan only
#   ./run_prompts.sh --skip-checkpoints    # skip between-phase verification
#
# Checkpoints:
#   After prompt 01 → ck_design   (FORECASTS_DESIGN.md exists, no decision markers)
#   After prompt 02 → ck_data     (Prisma migration + alembic revision present)
#   After prompt 09 → ck_safety   (default env yields PAPER_ONLY; 8 gates present)
#
# A failed checkpoint halts the batch with a resume hint. Skip with
# --skip-checkpoints if you have a reason (rare; they're cheap).
#
# Codex non-interactive surface used:
#   codex exec --full-auto [--model NAME] [-]
#
# bash 3.2 compatible (macOS default ships bash 3.2 for licensing reasons; we
# avoid `mapfile`, associative arrays, and other bash 4+ features).

set -uo pipefail

if [ -z "${BASH_VERSION:-}" ]; then
  echo "ERROR: this script requires bash. Run:  bash $0" >&2
  exit 1
fi

# ----- Config ----------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$REPO_ROOT/coding_prompts"
LOG_DIR="$REPO_ROOT/.codex_runs"
MODEL=""

# Tracks which prompt we're currently inside, so SIGINT/SIGTERM can tell the
# user where they are. Updated at the start of each prompt iteration.
CURRENT_PROMPT_NUM=""
CURRENT_PROMPT_NAME=""

# Trap handler: prints the resume hint and exits with a clean signal-style
# code. Without this, Ctrl-C during a sleep/retry left the user guessing.
on_signal() {
  local signal="$1"
  echo
  echo
  if [ -n "${CURRENT_PROMPT_NUM:-}" ]; then
    echo "${RED:-}${BOLD:-}── Interrupted (${signal}) during prompt ${CURRENT_PROMPT_NUM} (${CURRENT_PROMPT_NAME}). ──${NC:-}"
    echo "${RED:-}Resume with:  ./run_prompts.sh --from ${CURRENT_PROMPT_NUM}${NC:-}"
  else
    echo "${RED:-}${BOLD:-}── Interrupted (${signal}) before any prompt started. ──${NC:-}"
  fi
  echo
  # 130 = killed by SIGINT (POSIX convention); 143 = SIGTERM.
  case "$signal" in
    INT)  exit 130 ;;
    TERM) exit 143 ;;
    *)    exit 1   ;;
  esac
}
trap 'on_signal INT'  INT
trap 'on_signal TERM' TERM

FROM=0
TO=0
ONLY=""
CONTINUE_ON_FAIL=0
DRY_RUN=0
SKIP_CHECKPOINTS=0

# ----- Checkpoints (parallel arrays — bash 3.2 has no associative arrays) ---
# Round 11 ships with no per-prompt checkpoints. Prompts produce ops scripts
# and docs; their own Definition-of-Done assertions are sufficient. Earlier-
# round checkpoint functions (ck_design, ck_data, ck_safety) are preserved in
# git history under archive_round10/ for reference.
CHECKPOINT_AFTER=()
CHECKPOINT_FN=()

# ----- Arg parsing -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)              FROM="$2"; shift 2 ;;
    --to)                TO="$2"; shift 2 ;;
    --only)              ONLY="$2"; shift 2 ;;
    --model)             MODEL="$2"; shift 2 ;;
    --continue)          CONTINUE_ON_FAIL=1; shift ;;
    --dry-run)           DRY_RUN=1; shift ;;
    --skip-checkpoints)  SKIP_CHECKPOINTS=1; shift ;;
    -h|--help)           sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1"; exit 2 ;;
  esac
done

if [[ "$FROM" -gt 0 && "$TO" -gt 0 && "$((10#$FROM))" -gt "$((10#$TO))" ]]; then
  echo "error: --from $FROM is greater than --to $TO"; exit 2
fi

# ----- Pre-flight ------------------------------------------------------------
if ! command -v codex >/dev/null 2>&1; then
  echo "ERROR: 'codex' CLI not found in PATH." >&2
  echo "Install per https://github.com/openai/codex and run 'codex auth login'." >&2
  exit 3
fi

[[ -d "$PROMPTS_DIR" ]] || { echo "$PROMPTS_DIR does not exist"; exit 3; }
mkdir -p "$LOG_DIR"

# stdbuf keeps tee flushing line-by-line so progress appears in real time.
if command -v stdbuf >/dev/null 2>&1; then
  LINEBUF=(stdbuf -oL -eL)
elif command -v gstdbuf >/dev/null 2>&1; then
  LINEBUF=(gstdbuf -oL -eL)
else
  LINEBUF=()
fi

CODEX_EXEC_ARGS=(exec --full-auto)
if [ -n "$MODEL" ]; then
  CODEX_EXEC_ARGS+=(--model "$MODEL")
fi

# ----- Collect prompts (top-level only — _paused/ and archive_round*/ ignored)
PROMPTS=()
while IFS= read -r _line; do
  PROMPTS+=("$_line")
done < <(ls "$PROMPTS_DIR"/[0-9][0-9]_*.txt 2>/dev/null | sort)
TOTAL=${#PROMPTS[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "no numbered prompts found at the top level of $PROMPTS_DIR"
  echo "(prior rounds are archived under $PROMPTS_DIR/archive_round*/)"
  exit 0
fi

# ----- Color helpers ---------------------------------------------------------
if [ -t 1 ]; then
  BLUE=$'\033[0;34m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
  RED=$'\033[0;31m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
  BLUE=""; GREEN=""; YELLOW=""; RED=""; BOLD=""; NC=""
fi

# ----- Plan ------------------------------------------------------------------
echo "${BOLD}Plan:${NC} $TOTAL prompts total (Codex CLI runner)"
[ -n "$MODEL" ] && echo "${BOLD}Model:${NC} $MODEL"
[ -z "$MODEL" ] && echo "${BOLD}Model:${NC} (codex default — pass --model to override)"
if [ "$FROM" -gt 0 ] || [ "$TO" -gt 0 ] || [ -n "$ONLY" ]; then
  filter=""
  [ -n "$ONLY" ]   && filter="$filter only=$ONLY"
  [ "$FROM" -gt 0 ] && filter="$filter from=$FROM"
  [ "$TO" -gt 0 ]   && filter="$filter to=$TO"
  echo "${BOLD}Filter:${NC}$filter"
fi

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  n=$(basename "$f" .txt)
  num="${n%%_*}"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$num))" -lt "$((10#$FROM))" ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  if [ "$TO"   -gt 0 ] && [ "$((10#$num))" -gt "$((10#$TO))"   ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  echo "  run  $n"
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "${YELLOW}Dry-run: not executing.${NC}"
  exit 0
fi

# ----- Round 11 — pre-flight, progress bar, heartbeat ------------------------
# Round 11 has no per-prompt checkpoints. Instead it has:
#   - A single .env.live preflight that runs ONCE before any codex call.
#   - A progress bar header printed at the start of each prompt.
#   - A heartbeat that prints elapsed time every 30s during long codex calls.

# preflight_env_live — abort if .env.live is missing required fields.
# Reads only key NAMES, never values. Specifically: greps for `KEY=<non-empty>`.
preflight_env_live() {
  local f="$REPO_ROOT/.env.live"
  if [ ! -f "$f" ]; then
    echo
    echo "${RED}${BOLD}── .env.live not found at $f ──${NC}"
    echo "${RED}Round 11 requires a populated .env.live before any codex call.${NC}"
    echo
    echo "Setup:"
    echo "    cp .env.live.template .env.live"
    echo "    \$EDITOR .env.live          # fill in real values"
    echo
    echo "Then re-run:  ./run_prompts.sh"
    return 1
  fi

  # Required for any operation (paper or live).
  local required="DATABASE_URL ANTHROPIC_API_KEY FORECASTS_INGEST_ORG_ID FORECASTS_OPERATOR_SECRET"
  local missing=""
  local var
  for var in $required; do
    # Match VAR=<at least one non-quote, non-newline char>
    if ! grep -qE "^${var}=[^[:space:]\"']+" "$f"; then
      missing="$missing $var"
    fi
  done

  if [ -n "$missing" ]; then
    echo
    echo "${RED}${BOLD}── .env.live is present but missing required values ──${NC}"
    echo "${RED}Missing or empty:${NC}"
    for var in $missing; do echo "    - $var"; done
    echo
    echo "${YELLOW}This runner does not read or print the values themselves —${NC}"
    echo "${YELLOW}only checks that each KEY=<non-empty-value> line exists.${NC}"
    echo
    return 1
  fi

  echo "${GREEN}✓ .env.live present with all required fields populated${NC}"

  # Live-trading sanity: if the flag is true, check that the ceilings are non-zero.
  if grep -qE "^FORECASTS_LIVE_TRADING_ENABLED=true" "$f"; then
    local ceiling_problem=""
    if grep -qE "^FORECASTS_MAX_STAKE_USD=0" "$f"; then
      ceiling_problem="$ceiling_problem FORECASTS_MAX_STAKE_USD=0"
    fi
    if grep -qE "^FORECASTS_MAX_DAILY_LOSS_USD=0" "$f"; then
      ceiling_problem="$ceiling_problem FORECASTS_MAX_DAILY_LOSS_USD=0"
    fi
    if [ -n "$ceiling_problem" ]; then
      echo
      echo "${RED}${BOLD}── Live trading flag is true but ceilings are zero ──${NC}"
      echo "${RED}Misconfiguration:${ceiling_problem}${NC}"
      echo "${RED}Either set realistic ceilings or set FORECASTS_LIVE_TRADING_ENABLED=false.${NC}"
      return 1
    fi
    echo "${YELLOW}  ⚠  FORECASTS_LIVE_TRADING_ENABLED=true — operator rehearsal must be complete${NC}"
  fi

  return 0
}

# make_progress_bar <current> <total> [width=10]
# Echoes a Unicode block bar. Used in the per-prompt header.
make_progress_bar() {
  local cur="$1" tot="$2" width="${3:-10}"
  if [ "$tot" -le 0 ]; then echo ""; return; fi
  local filled=$(( cur * width / tot ))
  local empty=$(( width - filled ))
  local bar="" i
  for i in $(seq 1 "$filled" 2>/dev/null); do bar="${bar}▰"; done
  for i in $(seq 1 "$empty"  2>/dev/null); do bar="${bar}▱"; done
  echo "$bar"
}

# heartbeat_loop <prompt-num> <prompt-name> <start-epoch>
# Prints "still running (Nm Ns elapsed)" every 30s. Designed to be backgrounded
# and killed when the foreground codex call finishes.
heartbeat_loop() {
  local prompt_num="$1" prompt_name="$2" start_ts="$3"
  while sleep 30; do
    local now=$(date +%s)
    local elapsed=$((now - start_ts))
    local mins=$((elapsed / 60))
    local secs=$((elapsed % 60))
    printf "${BLUE}  ⏱  [%s] still running (%dm %02ds elapsed)${NC}\n" \
           "$prompt_num" "$mins" "$secs"
  done
}

# Look up the checkpoint function for a given prompt number, if any.
# Round 11 has no checkpoints (CHECKPOINT_AFTER is empty), so this always
# returns "". Kept for forward-compat with future rounds.
checkpoint_for() {
  local n="$1"
  local i
  for i in "${!CHECKPOINT_AFTER[@]}"; do
    if [ "${CHECKPOINT_AFTER[$i]}" = "$n" ]; then
      echo "${CHECKPOINT_FN[$i]}"
      return 0
    fi
  done
  echo ""
}


# ----- Codex invocation with retry -------------------------------------------
# Failures fall into three classes:
#   1. QUOTA — the user's Codex subscription daily cap is hit. Codex emits
#      "You've hit your usage limit … try again at <timestamp>". We parse the
#      timestamp, sleep until then + 90s buffer, and retry the SAME prompt.
#      Up to 4 quota-retries per prompt (the cap is daily, so 4 covers
#      multi-day saturation worst case).
#   2. TRANSIENT — non-zero exit with no quota signature. Could be a network
#      blip, a model-side timeout, an ephemeral codex internal error. We
#      retry up to 2 times with 30s backoff before declaring it real.
#   3. REAL — non-zero after retries exhausted, OR a recognized fatal pattern
#      (auth required, malformed prompt, etc.). Halt as before.
#
# parse_quota_reset_to_epoch <log-file>
#   Echoes a unix epoch on stdout if the log contains a parseable
#   "try again at …" line. Empty stdout otherwise. Handles BSD date (macOS)
#   and GNU date (Linux) transparently.
parse_quota_reset_to_epoch() {
  local log="$1"
  local raw cleaned epoch
  # Pull the last "try again at X" string. The message format observed:
  #   "… or try again at Apr 30th, 2026 1:06 AM."
  raw=$(grep -oE "try again at [^.]+\\." "$log" 2>/dev/null \
        | tail -1 \
        | sed -E 's/^try again at //; s/\.[[:space:]]*$//')
  [ -z "$raw" ] && return 0
  # Strip ordinal suffix on day (30th → 30).
  cleaned=$(echo "$raw" | sed -E 's/([0-9]+)(st|nd|rd|th)/\1/g')
  # Try BSD date first (macOS default); fall back to GNU date.
  epoch=$(date -j -f "%b %d, %Y %I:%M %p" "$cleaned" +%s 2>/dev/null \
          || date -d "$cleaned" +%s 2>/dev/null)
  [ -n "$epoch" ] && echo "$epoch"
}

# run_codex_with_retry <prompt-file> <log-path> <prompt-number>
# Returns the codex exit code (0 on eventual success).
run_codex_with_retry() {
  local prompt_file="$1"
  local log_path="$2"
  local num="$3"

  local quota_retries=0
  local transient_retries=0
  local max_quota_retries=4
  local max_transient_retries=2
  local rc

  while : ; do
    cat "$prompt_file" \
      | ${LINEBUF[@]+"${LINEBUF[@]}"} codex ${CODEX_EXEC_ARGS[@]+"${CODEX_EXEC_ARGS[@]}"} - 2>&1 \
      | tee "$log_path"
    rc=${PIPESTATUS[1]}

    if [ "$rc" -eq 0 ]; then
      return 0
    fi

    # ---- Quota-cap detection -----------------------------------------------
    if grep -qE "(hit your usage limit|usage limit reached|rate limit|quota exceeded)" "$log_path"; then
      quota_retries=$((quota_retries + 1))
      if [ "$quota_retries" -gt "$max_quota_retries" ]; then
        echo "${RED}Quota cap hit ${max_quota_retries} times for prompt $num — giving up.${NC}"
        echo "${RED}Resume manually with: ./run_prompts.sh --from $num${NC}"
        return "$rc"
      fi

      local reset_epoch now_epoch wait_s
      reset_epoch=$(parse_quota_reset_to_epoch "$log_path")
      now_epoch=$(date +%s)

      if [ -n "$reset_epoch" ] && [ "$reset_epoch" -gt "$now_epoch" ]; then
        wait_s=$(( reset_epoch - now_epoch + 90 ))
        # Sanity: refuse to sleep absurdly long. >24h means we parsed wrong.
        if [ "$wait_s" -gt 90000 ]; then
          echo "${RED}Parsed reset window is >25h away (sanity bound) — refusing to sleep.${NC}"
          echo "${RED}Wait it out manually, then: ./run_prompts.sh --from $num${NC}"
          return "$rc"
        fi
        local human_wait=$(( wait_s / 60 ))
        echo
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        echo "${YELLOW}Codex daily quota exhausted on prompt ${num}.${NC}"
        echo "${YELLOW}Quota window opens at the timestamp above; waiting ${wait_s}s${NC}"
        echo "${YELLOW}(≈${human_wait} min, including a 90s buffer) then retrying automatically.${NC}"
        echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}.${NC}"
        echo "${YELLOW}You can leave this terminal running. Ctrl-C to abort.${NC}"
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        sleep "$wait_s"
        continue
      else
        # Fallback when the timestamp couldn't be parsed.
        echo
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        echo "${YELLOW}Codex quota error detected, but reset time could not be parsed.${NC}"
        echo "${YELLOW}Sleeping 60 minutes as a conservative fallback, then retrying.${NC}"
        echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}.${NC}"
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        sleep 3600
        continue
      fi
    fi

    # ---- Recognized fatal patterns -----------------------------------------
    # These won't be fixed by retrying. Bail immediately.
    if grep -qE "(auth login|authentication required|please run.*login|invalid api key)" "$log_path"; then
      echo "${RED}Codex reports an auth problem. Run 'codex auth login' and retry.${NC}"
      return "$rc"
    fi

    # ---- Transient retry ---------------------------------------------------
    transient_retries=$((transient_retries + 1))
    if [ "$transient_retries" -gt "$max_transient_retries" ]; then
      echo "${RED}Codex returned exit $rc after ${max_transient_retries} retries — treating as real failure.${NC}"
      return "$rc"
    fi
    echo "${YELLOW}Codex returned exit $rc with no quota signature — treating as transient.${NC}"
    echo "${YELLOW}Retrying in 30s (attempt ${transient_retries}/${max_transient_retries}).${NC}"
    sleep 30
  done
}

# ----- Pre-flight: .env.live populated --------------------------------------
# Skip in dry-run mode (no codex calls happen so missing .env.live is fine).
if [ "$DRY_RUN" -eq 0 ]; then
  if ! preflight_env_live; then
    exit 1
  fi
fi

# ----- Run -------------------------------------------------------------------
OVERALL_START=$(date +%s)
RAN=0; OK=0; FAIL=0

# Compute how many prompts will actually run (for the progress bar).
PLAN_TOTAL=0
for _f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  _n=$(basename "$_f" .txt); _num="${_n%%_*}"
  if [ -n "$ONLY" ] && [ "$_num" != "$ONLY" ]; then continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$_num))" -lt "$((10#$FROM))" ]; then continue; fi
  if [ "$TO"   -gt 0 ] && [ "$((10#$_num))" -gt "$((10#$TO))"   ]; then continue; fi
  PLAN_TOTAL=$((PLAN_TOTAL + 1))
done
PLAN_INDEX=0

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  name=$(basename "$f" .txt)
  num="${name%%_*}"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$num))" -lt "$((10#$FROM))" ]; then continue; fi
  if [ "$TO"   -gt 0 ] && [ "$((10#$num))" -gt "$((10#$TO))"   ]; then continue; fi

  RAN=$((RAN+1))
  PLAN_INDEX=$((PLAN_INDEX+1))
  ts=$(date +%Y%m%d-%H%M%S)
  text_log="$LOG_DIR/${ts}_${name}.log"

  # Make signal handler aware of where we are.
  CURRENT_PROMPT_NUM="$num"
  CURRENT_PROMPT_NAME="$name"

  # Progress bar header.
  bar=$(make_progress_bar "$((PLAN_INDEX-1))" "$PLAN_TOTAL" 12)
  pct=$(( (PLAN_INDEX - 1) * 100 / (PLAN_TOTAL == 0 ? 1 : PLAN_TOTAL) ))
  total_elapsed=$(( $(date +%s) - OVERALL_START ))
  total_mins=$((total_elapsed / 60))

  echo
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  printf "${BOLD}${BLUE}[%d/%d]${NC} ${BLUE}%s${NC}  ${BOLD}${BLUE}%3d%%${NC}   ${BLUE}round so far: %dm${NC}\n" \
         "$PLAN_INDEX" "$PLAN_TOTAL" "$bar" "$pct" "$total_mins"
  printf "${BOLD}${BLUE}▶ %s${NC}   ${BLUE}log: %s${NC}\n" "$name" "$text_log"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"

  prompt_start=$(date +%s)

  # Start the heartbeat in the background. Kill it when codex finishes.
  heartbeat_loop "$num" "$name" "$prompt_start" &
  HB_PID=$!
  # Disown so the heartbeat doesn't keep us alive past EXIT.
  disown "$HB_PID" 2>/dev/null || true

  run_codex_with_retry "$f" "$text_log" "$num"
  rc=$?

  # Tear down the heartbeat. Use kill+wait so a stray "Terminated" message
  # is suppressed (it's noise; the user doesn't need to see it).
  kill "$HB_PID" 2>/dev/null
  wait "$HB_PID" 2>/dev/null

  prompt_end=$(date +%s)
  elapsed=$((prompt_end - prompt_start))

  if [ "$rc" -ne 0 ]; then
    FAIL=$((FAIL+1))
    echo "${RED}${BOLD}✗ ${name} failed (exit $rc, ${elapsed}s)${NC}"
    echo "${RED}   log: $text_log${NC}"
    if [ "$CONTINUE_ON_FAIL" -eq 0 ]; then
      echo "${RED}Halting. Inspect the log and resume with --from ${num}${NC}"
      break
    else
      echo "${YELLOW}Continuing (--continue set).${NC}"
    fi
  else
    OK=$((OK+1))
    echo "${GREEN}✓ ${name} complete (${elapsed}s)${NC}"

    ck_fn=$(checkpoint_for "$num")
    if [ -n "$ck_fn" ] && [ "$SKIP_CHECKPOINTS" -eq 0 ]; then
      echo
      echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
      if "$ck_fn"; then
        echo "${GREEN}${BOLD}✓ checkpoint $ck_fn passed${NC}"
      else
        echo "${RED}${BOLD}✗ checkpoint $ck_fn FAILED — halting before later prompts touch broken state${NC}"
        echo "${RED}  Fix the underlying issue, then resume with:  ./run_prompts.sh --from $((10#$num + 1))${NC}"
        FAIL=$((FAIL+1))
        break
      fi
      echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
    fi
  fi
done

# Clean exit — clear the trap-state so any final cleanup the user does (Ctrl-C
# at the summary line) doesn't print a misleading "interrupted in prompt X".
CURRENT_PROMPT_NUM=""
CURRENT_PROMPT_NAME=""

OVERALL_END=$(date +%s)
OVERALL_ELAPSED=$((OVERALL_END - OVERALL_START))
total_mins=$((OVERALL_ELAPSED / 60))
total_secs=$((OVERALL_ELAPSED % 60))

# Final progress bar reflects what actually ran (OK out of plan total).
final_bar=""
if [ "$PLAN_TOTAL" -gt 0 ]; then
  final_bar=$(make_progress_bar "$OK" "$PLAN_TOTAL" 12)
fi
echo
echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
if [ "$FAIL" -eq 0 ] && [ "$RAN" -gt 0 ]; then
  printf "${GREEN}${BOLD}✓ Round complete${NC}   %s   ${GREEN}%d/%d ok${NC}   ${BLUE}%dm %02ds${NC}\n" \
         "$final_bar" "$OK" "$PLAN_TOTAL" "$total_mins" "$total_secs"
elif [ "$RAN" -eq 0 ]; then
  echo "${YELLOW}No prompts matched the filter — nothing executed.${NC}"
else
  printf "${RED}${BOLD}✗ Round halted${NC}     %s   ${RED}%d/%d ran, %d fail${NC}   ${BLUE}%dm %02ds${NC}\n" \
         "$final_bar" "$RAN" "$PLAN_TOTAL" "$FAIL" "$total_mins" "$total_secs"
fi
echo "${BLUE}Logs:${NC} $LOG_DIR"
echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
