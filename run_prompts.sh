#!/bin/bash
# Active prompt batch runner — sequentially run every active top-level numbered
# prompt in coding_prompts/ via the OpenAI Codex CLI (`codex exec`). Streams
# each session's stdout to the terminal AND saves the full text log to
# .codex_runs/<timestamp>_<prompt>.log for review. The current batch's
# scope and dependencies are documented in coding_prompts/README.md.
#
# This uses the installed Codex CLI's existing login/subscription auth. It does
# NOT read or require an OpenAI API key, and it scrubs OpenAI API-key env vars
# before invoking Codex. If needed, run `codex auth login` once.
#
# Usage:
#   ./run_prompts.sh
#   ./run_prompts.sh --from 3
#   ./run_prompts.sh --to 5
#   ./run_prompts.sh --from 2 --to 6
#   ./run_prompts.sh --only 04
#   ./run_prompts.sh --model gpt-5.3-codex
#   ./run_prompts.sh --continue
#   ./run_prompts.sh --dry-run

set -uo pipefail

if [ -z "${BASH_VERSION:-}" ]; then
  echo "ERROR: this script requires bash. Run: bash $0" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$REPO_ROOT/coding_prompts"
LOG_DIR="$REPO_ROOT/.codex_runs"
MODEL=""
FROM=0
TO=0
ONLY=""
FROM_N=0
TO_N=0
CONTINUE_ON_FAIL=0
DRY_RUN=0
CURRENT_PROMPT_NUM=""
CURRENT_PROMPT_NAME=""

on_signal() {
  local signal="$1"
  echo
  if [ -n "${CURRENT_PROMPT_NUM:-}" ]; then
    echo "${RED:-}${BOLD:-}── Interrupted (${signal}) during prompt ${CURRENT_PROMPT_NUM} (${CURRENT_PROMPT_NAME}). ──${NC:-}"
    echo "${RED:-}Resume with: ./run_prompts.sh --from ${CURRENT_PROMPT_NUM}${NC:-}"
  else
    echo "${RED:-}${BOLD:-}── Interrupted (${signal}) before any prompt started. ──${NC:-}"
  fi
  case "$signal" in
    INT) exit 130 ;;
    TERM) exit 143 ;;
    *) exit 1 ;;
  esac
}
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) case "${2-}" in ''|--*) echo "error: --from requires a value" >&2; exit 2 ;; esac; FROM="$2"; shift 2 ;;
    --to) case "${2-}" in ''|--*) echo "error: --to requires a value" >&2; exit 2 ;; esac; TO="$2"; shift 2 ;;
    --only) case "${2-}" in ''|--*) echo "error: --only requires a value" >&2; exit 2 ;; esac; ONLY="$2"; shift 2 ;;
    --model) case "${2-}" in ''|--*) echo "error: --model requires a value" >&2; exit 2 ;; esac; MODEL="$2"; shift 2 ;;
    --continue) CONTINUE_ON_FAIL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1"; exit 2 ;;
  esac
done

is_uint() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

normalize_prompt_num() {
  local label="$1"
  local value="$2"
  if ! is_uint "$value"; then
    echo "error: $label must be a prompt number, got '$value'" >&2
    exit 2
  fi
  printf "%02d" "$((10#$value))"
}

if ! is_uint "$FROM"; then
  echo "error: --from must be a prompt number, got '$FROM'" >&2
  exit 2
fi
if ! is_uint "$TO"; then
  echo "error: --to must be a prompt number, got '$TO'" >&2
  exit 2
fi

FROM_N=$((10#$FROM))
TO_N=$((10#$TO))

if [ -n "$ONLY" ]; then
  ONLY="$(normalize_prompt_num --only "$ONLY")"
fi

if [ "$FROM_N" -gt 0 ] && [ "$TO_N" -gt 0 ] && [ "$FROM_N" -gt "$TO_N" ]; then
  echo "error: --from $FROM is greater than --to $TO"
  exit 2
fi

if [ "$DRY_RUN" -eq 0 ] && ! command -v codex >/dev/null 2>&1; then
  echo "ERROR: 'codex' CLI not found in PATH." >&2
  echo "Install it and run 'codex auth login'. This runner does not use an API key." >&2
  exit 3
fi

[[ -d "$PROMPTS_DIR" ]] || { echo "$PROMPTS_DIR does not exist"; exit 3; }
mkdir -p "$LOG_DIR"

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

PROMPTS=()
while IFS= read -r line; do
  PROMPTS+=("$line")
done < <(find "$PROMPTS_DIR" -maxdepth 1 -type f -name '[0-9][0-9]_*.txt' | sort)

if [ "${#PROMPTS[@]}" -eq 0 ]; then
  echo "no numbered prompts found at the top level of $PROMPTS_DIR"
  exit 0
fi

if [ -t 1 ]; then
  BLUE=$'\033[0;34m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
  RED=$'\033[0;31m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
  BLUE=""; GREEN=""; YELLOW=""; RED=""; BOLD=""; NC=""
fi

make_progress_bar() {
  local cur="$1" tot="$2" width="${3:-10}"
  if [ "$tot" -le 0 ]; then echo ""; return; fi
  local filled=$((cur * width / tot))
  local empty=$((width - filled))
  local bar="" i
  for i in $(seq 1 "$filled" 2>/dev/null); do bar="${bar}▰"; done
  for i in $(seq 1 "$empty" 2>/dev/null); do bar="${bar}▱"; done
  echo "$bar"
}

should_run() {
  local num="$1"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then return 1; fi
  if [ "$FROM_N" -gt 0 ] && [ "$((10#$num))" -lt "$FROM_N" ]; then return 1; fi
  if [ "$TO_N" -gt 0 ] && [ "$((10#$num))" -gt "$TO_N" ]; then return 1; fi
  return 0
}

SELECTED=0
for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  base=$(basename "$f" .txt)
  num="${base%%_*}"
  if should_run "$num"; then SELECTED=$((SELECTED + 1)); fi
done

echo "${BOLD}Plan:${NC} ${#PROMPTS[@]} active prompts total (${SELECTED} selected; Codex CLI login runner)"
[ -n "$MODEL" ] && echo "${BOLD}Model:${NC} $MODEL"
[ -z "$MODEL" ] && echo "${BOLD}Model:${NC} (codex default - pass --model to override)"
if [ "$FROM_N" -gt 0 ] || [ "$TO_N" -gt 0 ] || [ -n "$ONLY" ]; then
  filter=""
  [ -n "$ONLY" ] && filter="$filter only=$ONLY"
  [ "$FROM_N" -gt 0 ] && filter="$filter from=$FROM"
  [ "$TO_N" -gt 0 ] && filter="$filter to=$TO"
  echo "${BOLD}Filter:${NC}$filter"
fi

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  base=$(basename "$f" .txt)
  num="${base%%_*}"
  if should_run "$num"; then
    echo "  run  $base"
  else
    echo "  ${YELLOW}skip${NC} $base"
  fi
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "${YELLOW}Dry-run: not executing.${NC}"
  exit 0
fi

if [ "$SELECTED" -eq 0 ]; then
  echo "No prompts selected."
  exit 0
fi

heartbeat_loop() {
  local prompt_num="$1" prompt_name="$2" start_ts="$3"
  while sleep 30; do
    local now elapsed mins secs
    now=$(date +%s)
    elapsed=$((now - start_ts))
    mins=$((elapsed / 60))
    secs=$((elapsed % 60))
    printf "${BLUE}  ⏱  [%s] still running %s (%dm %02ds elapsed)${NC}\n" \
      "$prompt_num" "$prompt_name" "$mins" "$secs"
  done
}

parse_quota_reset_to_epoch() {
  local log="$1"
  local raw cleaned epoch
  raw=$(grep -oE "try again at [^.]+\\." "$log" 2>/dev/null \
    | tail -1 \
    | sed -E 's/^try again at //; s/\.[[:space:]]*$//')
  [ -z "$raw" ] && return 0
  cleaned=$(echo "$raw" | sed -E 's/([0-9]+)(st|nd|rd|th)/\1/g')
  epoch=$(date -j -f "%b %d, %Y %I:%M %p" "$cleaned" +%s 2>/dev/null \
    || date -d "$cleaned" +%s 2>/dev/null)
  [ -n "$epoch" ] && echo "$epoch"
}

run_codex_with_retry() {
  local prompt_file="$1"
  local log_path="$2"
  local num="$3"
  local quota_retries=0
  local transient_retries=0
  local max_quota_retries=4
  local max_transient_retries=2
  local rc reset_epoch now_epoch wait_s human_wait

  while :; do
    (
      unset OPENAI_API_KEY OPENAI_AUTH_TOKEN OPENAI_BASE_URL OPENAI_ORG_ID OPENAI_PROJECT
      {
        echo "You are operating in /Users/michaelquintin/Desktop/Theseus."
        echo "First inspect current code and tests. If the prompt's requested work is already implemented, verify it and make only necessary repair edits. Do not duplicate landed work. Do not use or ask for an OpenAI API key; rely on the Codex CLI login session running this prompt."
        echo
        cat "$prompt_file"
      } | "${LINEBUF[@]}" codex "${CODEX_EXEC_ARGS[@]}" -
    ) 2>&1 | tee "$log_path"
    rc=${PIPESTATUS[0]}

    if [ "$rc" -eq 0 ]; then
      return 0
    fi

    if grep -qE "(hit your usage limit|usage limit reached|rate limit|quota exceeded)" "$log_path"; then
      quota_retries=$((quota_retries + 1))
      if [ "$quota_retries" -gt "$max_quota_retries" ]; then
        echo "${RED}Quota cap hit ${max_quota_retries} times for prompt $num - giving up.${NC}"
        echo "${RED}Resume manually with: ./run_prompts.sh --from $num${NC}"
        return "$rc"
      fi

      reset_epoch=$(parse_quota_reset_to_epoch "$log_path")
      now_epoch=$(date +%s)
      if [ -n "$reset_epoch" ] && [ "$reset_epoch" -gt "$now_epoch" ]; then
        wait_s=$((reset_epoch - now_epoch + 90))
        if [ "$wait_s" -gt 90000 ]; then
          echo "${RED}Parsed reset window is >25h away (sanity bound) - refusing to sleep.${NC}"
          echo "${RED}Wait manually, then resume with: ./run_prompts.sh --from $num${NC}"
          return "$rc"
        fi
        human_wait=$((wait_s / 60))
        echo
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        echo "${YELLOW}Codex daily quota exhausted on prompt ${num}.${NC}"
        echo "${YELLOW}Waiting ${wait_s}s (about ${human_wait} min, including a 90s buffer), then retrying.${NC}"
        echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}. Ctrl-C to abort.${NC}"
        echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
        sleep "$wait_s"
        continue
      fi

      echo
      echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
      echo "${YELLOW}Codex quota error detected, but reset time could not be parsed.${NC}"
      echo "${YELLOW}Sleeping 60 minutes as a conservative fallback, then retrying.${NC}"
      echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}.${NC}"
      echo "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
      sleep 3600
      continue
    fi

    if grep -qE "(auth login|authentication required|please run.*login|invalid api key)" "$log_path"; then
      echo "${RED}Codex reports an auth problem. Run 'codex auth login' and retry.${NC}"
      return "$rc"
    fi

    transient_retries=$((transient_retries + 1))
    if [ "$transient_retries" -gt "$max_transient_retries" ]; then
      echo "${RED}Codex returned exit $rc after ${max_transient_retries} retries - treating as real failure.${NC}"
      return "$rc"
    fi
    echo "${YELLOW}Codex returned exit $rc with no quota signature - treating as transient.${NC}"
    echo "${YELLOW}Retrying in 30s (attempt ${transient_retries}/${max_transient_retries}).${NC}"
    sleep 30
  done
}

run_prompt() {
  local prompt="$1"
  local index="$2"
  local total="$3"
  local base num stamp log status start elapsed bar pct total_elapsed total_mins hb
  base=$(basename "$prompt" .txt)
  num="${base%%_*}"
  stamp=$(date +"%Y%m%d-%H%M%S")
  log="$LOG_DIR/${stamp}_${base}.log"
  CURRENT_PROMPT_NUM="$num"
  CURRENT_PROMPT_NAME="$base"

  bar=$(make_progress_bar "$((index - 1))" "$total" 12)
  pct=$(((index - 1) * 100 / (total == 0 ? 1 : total)))
  total_elapsed=$(($(date +%s) - OVERALL_START))
  total_mins=$((total_elapsed / 60))

  echo
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  printf "${BOLD}${BLUE}[%d/%d]${NC} ${BLUE}%s${NC}  ${BOLD}${BLUE}%3d%%${NC}   ${BLUE}batch so far: %dm${NC}\n" \
    "$index" "$total" "$bar" "$pct" "$total_mins"
  printf "${BOLD}${BLUE}▶ %s${NC}   ${BLUE}log: %s${NC}\n" "$base" "$log"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"

  start=$(date +%s)

  heartbeat_loop "$num" "$base" "$start" &
  hb=$!
  disown "$hb" 2>/dev/null || true

  run_codex_with_retry "$prompt" "$log" "$num"
  status=$?

  kill "$hb" >/dev/null 2>&1 || true
  wait "$hb" >/dev/null 2>&1 || true

  elapsed=$(($(date +%s) - start))
  if [ "$status" -eq 0 ]; then
    echo "${GREEN}✓ ${base} complete (${elapsed}s)${NC}"
  else
    echo "${RED}${BOLD}✗ ${base} failed (exit ${status}, ${elapsed}s)${NC}"
    echo "${RED}   log: $log${NC}"
    echo "${RED}Halting. Inspect the log and resume with --from ${num}${NC}"
  fi
  return "$status"
}

OVERALL_START=$(date +%s)
ran=0
failed=0
ok=0
for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  base=$(basename "$f" .txt)
  num="${base%%_*}"
  if ! should_run "$num"; then continue; fi
  ran=$((ran + 1))
  if ! run_prompt "$f" "$ran" "$SELECTED"; then
    failed=$((failed + 1))
    if [ "$CONTINUE_ON_FAIL" -eq 0 ]; then
      break
    fi
  else
    ok=$((ok + 1))
  fi
done

CURRENT_PROMPT_NUM=""
CURRENT_PROMPT_NAME=""

OVERALL_END=$(date +%s)
OVERALL_ELAPSED=$((OVERALL_END - OVERALL_START))
total_mins=$((OVERALL_ELAPSED / 60))
total_secs=$((OVERALL_ELAPSED % 60))
final_bar=""
if [ "$SELECTED" -gt 0 ]; then
  final_bar=$(make_progress_bar "$ok" "$SELECTED" 12)
fi

echo
if [ "$failed" -eq 0 ]; then
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  printf "${GREEN}${BOLD}✓ Active batch complete${NC}        %s   ${GREEN}%d/%d ok${NC}   ${BLUE}%dm %02ds${NC}\n" \
    "$final_bar" "$ok" "$SELECTED" "$total_mins" "$total_secs"
  echo "${BLUE}Logs:${NC} $LOG_DIR"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
else
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  printf "${RED}${BOLD}✗ Active batch halted${NC}          %s   ${RED}%d/%d ran, %d fail${NC}   ${BLUE}%dm %02ds${NC}\n" \
    "$final_bar" "$ran" "$SELECTED" "$failed" "$total_mins" "$total_secs"
  echo "${BLUE}Logs:${NC} $LOG_DIR"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  exit 1
fi
