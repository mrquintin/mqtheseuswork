#!/bin/bash
# Sequentially run every prompt in Claude_Code_Prompts/ via the OpenAI Codex CLI
# (`codex exec`), streaming each session's stdout to the terminal and saving the
# full text log to .codex_runs/<timestamp>_<prompt>.log for review.
#
# This is the Codex sibling of run_prompts.sh (which uses `claude -p`). The two
# scripts can coexist; pick whichever CLI you want for a given run. The prompt
# files in Claude_Code_Prompts/ are CLI-agnostic — they read as plain English
# instructions either tool can act on.
#
# Usage:
#   ./run_prompts_codex.sh                  # run all prompts, halt on first failure
#   ./run_prompts_codex.sh --from 5         # start at prompt 05
#   ./run_prompts_codex.sh --to 7           # stop after prompt 07 (inclusive)
#   ./run_prompts_codex.sh --from 3 --to 7  # 03 through 07 inclusive
#   ./run_prompts_codex.sh --only 03        # run only prompt 03
#   ./run_prompts_codex.sh --model gpt-5-codex   # override the model
#   ./run_prompts_codex.sh --continue       # keep going on prompt failure
#   ./run_prompts_codex.sh --dry-run        # show plan only
#
# Requires:
#   codex   (the OpenAI Codex CLI, in $PATH; install per https://github.com/openai/codex)
#
# Codex CLI non-interactive surface used here:
#   codex exec --full-auto [--model NAME] [-]
#     - `exec` runs Codex non-interactively (no TUI) and exits when done.
#     - `--full-auto` skips per-turn approval prompts so the script doesn't
#       block on each tool use (the analog of Claude Code's
#       --dangerously-skip-permissions flag — and it grants Codex the same
#       broad ability to read/write/run-bash inside the project sandbox).
#     - The prompt text is piped on stdin.
#
# If your installed Codex CLI uses different flag names, edit CODEX_EXEC_ARGS
# below — that array is the only Codex-specific surface area in this script.
#
# bash 3.2 compatible (macOS default ships bash 3.2 for licensing reasons; we
# avoid `mapfile`, associative arrays, and other bash 4+ features).

set -uo pipefail

# bash sanity — bail early if invoked under sh/dash.
if [ -z "${BASH_VERSION:-}" ]; then
  echo "ERROR: this script requires bash. Run:  bash $0" >&2
  exit 1
fi

# ----- Config ----------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$REPO_ROOT/Claude_Code_Prompts"
LOG_DIR="$REPO_ROOT/.codex_runs"
MODEL=""   # empty → let codex use its configured default; --model overrides

FROM=0
TO=0
ONLY=""
CONTINUE_ON_FAIL=0
DRY_RUN=0

# ----- Arg parsing -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)     FROM="$2"; shift 2 ;;
    --to)       TO="$2"; shift 2 ;;
    --only)     ONLY="$2"; shift 2 ;;
    --model)    MODEL="$2"; shift 2 ;;
    --continue) CONTINUE_ON_FAIL=1; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1"; exit 2 ;;
  esac
done

if [[ "$FROM" -gt 0 && "$TO" -gt 0 && "$((10#$FROM))" -gt "$((10#$TO))" ]]; then
  echo "error: --from $FROM is greater than --to $TO"; exit 2
fi

# ----- Pre-flight ------------------------------------------------------------
if ! command -v codex >/dev/null 2>&1; then
  echo "ERROR: 'codex' CLI not found in PATH." >&2
  echo "Install: see https://github.com/openai/codex" >&2
  exit 3
fi

[[ -d "$PROMPTS_DIR" ]] || { echo "$PROMPTS_DIR does not exist"; exit 3; }
mkdir -p "$LOG_DIR"

# stdbuf keeps tee flushing line-by-line so progress appears in real time.
# macOS doesn't ship stdbuf; coreutils provides gstdbuf. If neither is present,
# we run unbuffered via the codex CLI's own behavior.
if command -v stdbuf >/dev/null 2>&1; then
  LINEBUF=(stdbuf -oL -eL)
elif command -v gstdbuf >/dev/null 2>&1; then
  LINEBUF=(gstdbuf -oL -eL)
else
  LINEBUF=()
fi

# ----- Build the codex exec arg list -----------------------------------------
# Edit this array if your Codex CLI version uses different flags. Everything
# Codex-specific is here so the rest of the script stays portable.
CODEX_EXEC_ARGS=(exec --full-auto)
if [ -n "$MODEL" ]; then
  CODEX_EXEC_ARGS+=(--model "$MODEL")
fi

# ----- Collect prompts -------------------------------------------------------
PROMPTS=()
while IFS= read -r _line; do
  PROMPTS+=("$_line")
done < <(ls "$PROMPTS_DIR"/[0-9][0-9]_*.txt 2>/dev/null | sort)
TOTAL=${#PROMPTS[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "no numbered prompts found at the top level of $PROMPTS_DIR"
  echo "(prior rounds are archived under $PROMPTS_DIR/archive_round*/)"
  echo "drop new NN_*.txt files into $PROMPTS_DIR and re-run."
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
[ -n "$MODEL" ] && echo "${BOLD}Model:${NC} $MODEL (overriding codex default)"
[ -z "$MODEL" ] && echo "${BOLD}Model:${NC} (codex default — pass --model to override)"
if [ "$FROM" -gt 0 ] || [ "$TO" -gt 0 ] || [ -n "$ONLY" ]; then
  filter=""
  [ -n "$ONLY" ] && filter="$filter only=$ONLY"
  [ "$FROM" -gt 0 ] && filter="$filter from=$FROM"
  [ "$TO" -gt 0 ] && filter="$filter to=$TO"
  echo "${BOLD}Filter:${NC}$filter"
fi

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  n=$(basename "$f" .txt)
  num="${n%%_*}"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$num))" -lt "$((10#$FROM))" ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  if [ "$TO" -gt 0 ] && [ "$((10#$num))" -gt "$((10#$TO))" ]; then echo "  ${YELLOW}skip${NC} $n"; continue; fi
  echo "  run  $n"
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "${YELLOW}Dry-run: not executing.${NC}"
  exit 0
fi

# ----- Run -------------------------------------------------------------------
OVERALL_START=$(date +%s)
RAN=0; OK=0; FAIL=0

for f in ${PROMPTS[@]+"${PROMPTS[@]}"}; do
  name=$(basename "$f" .txt)
  num="${name%%_*}"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then continue; fi
  if [ "$FROM" -gt 0 ] && [ "$((10#$num))" -lt "$((10#$FROM))" ]; then continue; fi
  if [ "$TO" -gt 0 ] && [ "$((10#$num))" -gt "$((10#$TO))" ]; then continue; fi

  RAN=$((RAN+1))
  ts=$(date +%Y%m%d-%H%M%S)
  text_log="$LOG_DIR/${ts}_${name}.log"

  echo
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  echo "${BOLD}${BLUE}▶ ${name}${NC}   ${BLUE}log: ${text_log}${NC}"
  echo "${BLUE}──────────────────────────────────────────────────────────────${NC}"

  prompt_start=$(date +%s)

  # Pipeline: cat prompt → codex (with line-buffering if available) → tee log.
  # PIPESTATUS[1] is codex's exit code (0=cat, 1=codex, 2=tee).
  cat "$f" \
    | ${LINEBUF[@]+"${LINEBUF[@]}"} codex ${CODEX_EXEC_ARGS[@]+"${CODEX_EXEC_ARGS[@]}"} - 2>&1 \
    | tee "$text_log"
  rc=${PIPESTATUS[1]}

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
  fi
done

OVERALL_END=$(date +%s)
OVERALL_ELAPSED=$((OVERALL_END - OVERALL_START))
echo
echo "${BOLD}Summary:${NC} ran $RAN, ok $OK, fail $FAIL, total ${OVERALL_ELAPSED}s"
echo "Logs in ${LOG_DIR}"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
