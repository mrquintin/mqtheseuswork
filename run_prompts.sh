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
CHECKPOINT_AFTER=("01"        "02"      "09")
CHECKPOINT_FN=(   "ck_design" "ck_data" "ck_safety")

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
echo "${BOLD}Plan:${NC} $TOTAL prompts total (Codex CLI runner — Round 10 / Forecasts)"
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

# ----- Checkpoint functions --------------------------------------------------
# Each function returns 0 on pass, non-zero on fail. Output goes straight to
# the terminal (the user is watching this).

ck_design() {
  echo "${BOLD}Checkpoint:${NC} ck_design — verifying FORECASTS_DESIGN.md is complete"

  if [ ! -f "$REPO_ROOT/coding_prompts/FORECASTS_DESIGN.md" ]; then
    echo "${RED}  FAIL: coding_prompts/FORECASTS_DESIGN.md is missing${NC}"
    echo "        Prompt 01 didn't produce its deliverable."
    return 1
  fi
  echo "${GREEN}  ✓ FORECASTS_DESIGN.md exists${NC}"

  if grep -q '\*\*DECISION REQUIRED\*\*' "$REPO_ROOT/coding_prompts/FORECASTS_DESIGN.md"; then
    echo "${RED}  FAIL: FORECASTS_DESIGN.md has unresolved DECISION REQUIRED markers${NC}"
    echo "        Resolve those before running prompt 02."
    return 1
  fi
  echo "${GREEN}  ✓ no unresolved decision markers${NC}"

  for section in "Goals and non-goals" "Data model" "Route table" \
                 "Env-var matrix" "Trading-mode state machine" "Risk register"; do
    if ! grep -q -- "$section" "$REPO_ROOT/coding_prompts/FORECASTS_DESIGN.md"; then
      echo "${RED}  FAIL: missing required section: $section${NC}"
      return 1
    fi
  done
  echo "${GREEN}  ✓ all required sections present${NC}"

  return 0
}

ck_data() {
  echo "${BOLD}Checkpoint:${NC} ck_data — verifying the forecasts data layer migrates cleanly"

  # 1. Prisma migration directory exists.
  local mig_dir
  mig_dir=$(find "$REPO_ROOT/theseus-codex/prisma/migrations" \
              -maxdepth 1 -type d -name '*forecasts_data_model' 2>/dev/null | head -1)
  if [ -z "$mig_dir" ]; then
    echo "${RED}  FAIL: no prisma migration named *_forecasts_data_model found${NC}"
    return 1
  fi
  echo "${GREEN}  ✓ Prisma migration present:${NC} $(basename "$mig_dir")"

  # 2. Alembic revision exists.
  if [ ! -f "$REPO_ROOT/noosphere/alembic/versions/004_forecasts_data_model.py" ]; then
    echo "${RED}  FAIL: noosphere/alembic/versions/004_forecasts_data_model.py missing${NC}"
    return 1
  fi
  echo "${GREEN}  ✓ Alembic revision 004 present${NC}"

  # 3. Prisma schema parses + validates.
  #
  # SAFETY: `prisma format` and `prisma validate` are documented file-only
  # operations — they read schema.prisma and exit, no socket opened. Prisma 7
  # nevertheless requires DATABASE_URL to be SET at config-load time because
  # prisma.config.ts and the datasource block call env("DATABASE_URL") eagerly.
  #
  # We supply a guaranteed-NON-ROUTABLE URL so even if a future maintainer
  # mistakenly adds `prisma migrate` / `prisma db push` here, those commands
  # will fail-closed (no DNS, refused connect) rather than silently mutating
  # whatever Postgres happens to be on localhost:5432:
  #
  #   - `db.invalid` is a DNS-blackholed TLD per RFC 2606 §2.
  #   - Port 1 is privileged; no real DB is going to be bound there.
  #
  # DO NOT change this URL to localhost or any reachable host without first
  # auditing every command that runs under it.
  local STUB_DB_URL='postgresql://stub:stub@db.invalid:1/stub'

  if ! ( cd "$REPO_ROOT/theseus-codex" && \
         DATABASE_URL="$STUB_DB_URL" \
         npx --yes prisma format >/tmp/ck_data_prisma.log 2>&1 ); then
    echo "${RED}  FAIL: 'prisma format' failed${NC}"
    head -30 /tmp/ck_data_prisma.log | sed 's/^/    /'
    return 1
  fi
  echo "${GREEN}  ✓ prisma schema formats cleanly${NC}"

  # 3b. Prisma schema validates (catches relation/FK/index errors `format` misses).
  if ! ( cd "$REPO_ROOT/theseus-codex" && \
         DATABASE_URL="$STUB_DB_URL" \
         npx --yes prisma validate >/tmp/ck_data_prisma_validate.log 2>&1 ); then
    echo "${RED}  FAIL: 'prisma validate' failed${NC}"
    head -30 /tmp/ck_data_prisma_validate.log | sed 's/^/    /'
    return 1
  fi
  echo "${GREEN}  ✓ prisma schema validates cleanly${NC}"

  # 4. Forecasts SQLModel symbols on the noosphere store.
  for sym in StoredForecastMarket StoredForecastPrediction; do
    if ! grep -q "class $sym" "$REPO_ROOT/noosphere/noosphere/store.py"; then
      echo "${RED}  FAIL: $sym not present in noosphere/store.py${NC}"
      return 1
    fi
  done
  echo "${GREEN}  ✓ forecasts SQLModel classes present${NC}"

  return 0
}

ck_safety() {
  echo "${BOLD}Checkpoint:${NC} ck_safety — verifying live trading is OFF by default and gates are wired"

  local sf="$REPO_ROOT/noosphere/noosphere/forecasts/safety.py"
  if [ ! -f "$sf" ]; then
    echo "${RED}  FAIL: noosphere/noosphere/forecasts/safety.py missing${NC}"
    return 1
  fi
  echo "${GREEN}  ✓ safety.py present${NC}"

  # 1. Eight gate codes appear in safety.py.
  local missing=0
  for code in DISABLED NOT_CONFIGURED NOT_AUTHORIZED NOT_CONFIRMED \
              STAKE_OVER_CEILING DAILY_LOSS_OVER_CEILING \
              KILL_SWITCH_ENGAGED INSUFFICIENT_BALANCE; do
    if ! grep -q "\"$code\"" "$sf"; then
      echo "${RED}  FAIL: gate code '$code' not present in safety.py${NC}"
      missing=$((missing + 1))
    fi
  done
  [ "$missing" -gt 0 ] && return 1
  echo "${GREEN}  ✓ all 8 gate codes present${NC}"

  # 2. paper_bet_engine has zero live-client imports.
  if grep -qE 'polymarket_live|kalshi_live|_polymarket_live_client|_kalshi_live_client' \
       "$REPO_ROOT/noosphere/noosphere/forecasts/paper_bet_engine.py" 2>/dev/null; then
    echo "${RED}  FAIL: paper_bet_engine.py imports a live exchange client${NC}"
    return 1
  fi
  echo "${GREEN}  ✓ paper_bet_engine has no live client imports${NC}"

  # 3. FORECASTS_LIVE_TRADING_ENABLED is read in safety.py.
  if ! grep -q 'FORECASTS_LIVE_TRADING_ENABLED' "$sf"; then
    echo "${RED}  FAIL: safety.py does not read FORECASTS_LIVE_TRADING_ENABLED${NC}"
    return 1
  fi
  echo "${GREEN}  ✓ live-trading flag wired${NC}"

  # 4. Default env produces a DISABLED gate failure.
  #
  # We try the strong check first (run the code), then a grep fallback if no
  # Python with `noosphere` importable is on this machine. Both must agree
  # that the DISABLED branch exists; the strong check additionally proves it
  # actually fires under empty env.
  #
  # Probe order for the interpreter:
  #   1. .venv/currents/bin/python  — the project venv Codex itself uses.
  #   2. .venv/bin/python           — alternate venv name.
  #   3. python3                    — system python3 (macOS default).
  #   4. python                     — last resort (Linux distros, rare on macOS).
  local PYTHON=""
  for candidate in \
      "$REPO_ROOT/.venv/currents/bin/python" \
      "$REPO_ROOT/.venv/bin/python" \
      "$REPO_ROOT/noosphere/.venv/bin/python" \
      "$(command -v python3 2>/dev/null)" \
      "$(command -v python  2>/dev/null)"; do
    [ -z "$candidate" ] && continue
    [ -x "$candidate" ] || continue
    if ( cd "$REPO_ROOT/noosphere" && "$candidate" -c "import noosphere.forecasts.safety" ) >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done

  if [ -n "$PYTHON" ]; then
    echo "  python: $PYTHON"
    if ! ( cd "$REPO_ROOT/noosphere" && \
           env -u FORECASTS_LIVE_TRADING_ENABLED \
               -u POLYMARKET_PRIVATE_KEY \
               -u KALSHI_API_KEY_ID \
           "$PYTHON" - >/tmp/ck_safety_self.log 2>&1 <<'PYEOF'
from noosphere.forecasts import safety as s
ctx = s.GateContext(
    live_trading_enabled=False,
    polymarket_configured=False, kalshi_configured=False,
    max_stake_usd=0.0, max_daily_loss_usd=0.0,
    kill_switch_engaged=False, daily_loss_usd=0.0, live_balance_usd=0.0,
)
try:
    s.check_all_gates(prediction=None, bet=None, ctx=ctx)
except s.GateFailure as e:
    if e.code != "DISABLED":
        raise SystemExit(f"expected DISABLED, got {e.code}")
    raise SystemExit(0)
raise SystemExit("expected GateFailure, none raised")
PYEOF
    ); then
      echo "${RED}  FAIL: default-env self-check did not refuse with DISABLED${NC}"
      head -20 /tmp/ck_safety_self.log | sed 's/^/    /'
      return 1
    fi
    echo "${GREEN}  ✓ default env refuses live trading (DISABLED) — strong check${NC}"
  else
    # Grep fallback: confirm safety.py contains the DISABLED branch with a
    # check tied to the live-trading flag. Weaker (doesn't prove it executes)
    # but never a false negative on a missing venv.
    echo "${YELLOW}  no python with noosphere importable — using source-level fallback${NC}"
    if ! grep -B2 -A6 'live_trading_enabled' "$sf" | grep -q '"DISABLED"'; then
      echo "${RED}  FAIL: safety.py: no DISABLED branch tied to live_trading_enabled flag${NC}"
      return 1
    fi
    echo "${GREEN}  ✓ DISABLED branch present and tied to live_trading_enabled — fallback check${NC}"
  fi

  return 0
}

# Look up the checkpoint function for a given prompt number, if any.
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

# ----- Run -------------------------------------------------------------------
OVERALL_START=$(date +%s)
RAN=0; OK=0; FAIL=0

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  name=$(basename "$f" .txt)
  num="${name%%_*}"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$num))" -lt "$((10#$FROM))" ]; then continue; fi
  if [ "$TO"   -gt 0 ] && [ "$((10#$num))" -gt "$((10#$TO))"   ]; then continue; fi

  RAN=$((RAN+1))
  ts=$(date +%Y%m%d-%H%M%S)
  text_log="$LOG_DIR/${ts}_${name}.log"

  # Make signal handler aware of where we are.
  CURRENT_PROMPT_NUM="$num"
  CURRENT_PROMPT_NAME="$name"

  echo
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  echo "${BOLD}${BLUE}▶ ${name}${NC}   ${BLUE}log: ${text_log}${NC}"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"

  prompt_start=$(date +%s)
  run_codex_with_retry "$f" "$text_log" "$num"
  rc=$?
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
echo
echo "${BOLD}Summary:${NC} ran $RAN, ok $OK, fail $FAIL, total ${OVERALL_ELAPSED}s"
echo "Logs in ${LOG_DIR}"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
