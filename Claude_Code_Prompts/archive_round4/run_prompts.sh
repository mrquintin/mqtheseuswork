#!/usr/bin/env bash
# Sequentially run every prompt in Claude_Code_Prompts/ via `claude -p`,
# streaming each session's events to the terminal as a compact live summary,
# and saving the full raw stream-json log to .claude_code_runs/ for later review.
#
# Usage:
#   ./run_prompts.sh                  # run all prompts, halt on first failure
#   ./run_prompts.sh --from 5         # start at prompt 05 (skip already-done)
#   ./run_prompts.sh --only 03        # run only prompt 03
#   ./run_prompts.sh --continue       # keep going on prompt failure instead of halting
#   ./run_prompts.sh --dry-run        # show plan only
#
# Requires:
#   claude  (the Claude Code CLI, in $PATH)
#   python3
#   jq      (optional; only used if format_stream_events.py is missing)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$REPO_ROOT/Claude_Code_Prompts"
LOG_DIR="$REPO_ROOT/.claude_code_runs"
FORMATTER="$REPO_ROOT/format_stream_events.py"

FROM=0
ONLY=""
CONTINUE_ON_FAIL=0
DRY_RUN=0
SKIP_PERMS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --continue) CONTINUE_ON_FAIL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-perms) SKIP_PERMS=1; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1"; exit 2 ;;
  esac
done

command -v claude >/dev/null || { echo "claude CLI not found in PATH"; exit 3; }
command -v python3 >/dev/null || { echo "python3 required"; exit 3; }
[[ -d "$PROMPTS_DIR" ]] || { echo "$PROMPTS_DIR does not exist"; exit 3; }
[[ -f "$FORMATTER" ]] || { echo "$FORMATTER missing (expected beside this script)"; exit 3; }

mkdir -p "$LOG_DIR"

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

# Assemble prompt list in sorted order (portable: works on macOS bash 3.2).
PROMPTS=()
while IFS= read -r _line; do
  PROMPTS+=("$_line")
done < <(ls "$PROMPTS_DIR"/[0-9][0-9]_*.txt 2>/dev/null | sort)
TOTAL=${#PROMPTS[@]}
[[ $TOTAL -gt 0 ]] || { echo "no prompts found in $PROMPTS_DIR"; exit 3; }

echo -e "${BOLD}Plan:${NC} $TOTAL prompts"
for f in "${PROMPTS[@]}"; do
  n=$(basename "$f" .txt)
  num="${n%%_*}"
  if [[ -n "$ONLY" && "$num" != "$ONLY" ]]; then continue; fi
  if [[ -n "$FROM" && "$FROM" -gt 0 && "$((10#$num))" -lt "$((10#$FROM))" ]]; then
    echo -e "  ${YELLOW}skip${NC} $n"
    continue
  fi
  echo "  run  $n"
done

if [[ $DRY_RUN -eq 1 ]]; then
  echo -e "${YELLOW}Dry-run: not executing.${NC}"
  exit 0
fi

OVERALL_START=$(date +%s)
RAN=0; OK=0; FAIL=0

for f in "${PROMPTS[@]}"; do
  name=$(basename "$f" .txt)
  num="${name%%_*}"
  if [[ -n "$ONLY" && "$num" != "$ONLY" ]]; then continue; fi
  if [[ -n "$FROM" && "$FROM" -gt 0 && "$((10#$num))" -lt "$((10#$FROM))" ]]; then continue; fi

  RAN=$((RAN+1))
  ts=$(date +%Y%m%d-%H%M%S)
  raw_log="$LOG_DIR/${ts}_${name}.raw.jsonl"
  text_log="$LOG_DIR/${ts}_${name}.log"

  echo
  echo -e "${BLUE}──────────────────────────────────────────────────────────────${NC}"
  echo -e "${BOLD}${BLUE}▶ ${name}${NC}   ${BLUE}raw log: ${raw_log}${NC}"
  echo -e "${BLUE}──────────────────────────────────────────────────────────────${NC}"

  prompt_start=$(date +%s)
  EXTRA_ARGS=(--output-format stream-json --verbose --model claude-opus-4-7)
  if [[ $SKIP_PERMS -eq 1 ]]; then
    EXTRA_ARGS+=(--dangerously-skip-permissions)
  fi

  # Pipeline: claude emits NDJSON → tee preserves raw → formatter prints summary → tee preserves text
  # PIPESTATUS[0] captures claude's exit code.
  set +e
  claude -p "$(cat "$f")" "${EXTRA_ARGS[@]}" 2>&1 \
    | tee "$raw_log" \
    | python3 -u "$FORMATTER" \
    | tee "$text_log"
  rc=${PIPESTATUS[0]}
  set -e

  prompt_end=$(date +%s)
  elapsed=$((prompt_end - prompt_start))

  if [[ $rc -ne 0 ]]; then
    FAIL=$((FAIL+1))
    echo -e "${RED}${BOLD}✗ ${name} failed (exit $rc, ${elapsed}s)${NC}"
    echo -e "${RED}   raw: $raw_log${NC}"
    if [[ $CONTINUE_ON_FAIL -eq 0 ]]; then
      echo -e "${RED}Halting. Inspect the log and fix before resuming with --from ${num}${NC}"
      break
    else
      echo -e "${YELLOW}Continuing anyway (--continue set).${NC}"
    fi
  else
    OK=$((OK+1))
    echo -e "${GREEN}✓ ${name} complete (${elapsed}s)${NC}"
  fi
done

OVERALL_END=$(date +%s)
OVERALL_ELAPSED=$((OVERALL_END - OVERALL_START))
echo
echo -e "${BOLD}Summary:${NC} ran $RAN, ok $OK, fail $FAIL, total ${OVERALL_ELAPSED}s"
echo -e "Logs in ${LOG_DIR}"

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
