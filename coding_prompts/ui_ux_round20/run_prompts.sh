#!/usr/bin/env bash
# UI UX Round 20 runner: UI cleanup plus algorithmic market infrastructure.
#
# Sequentially runs the numbered prompts in this directory via Claude Code CLI.
# Uses Claude Code's existing subscription login (`claude -p`), not an API key.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROMPTS_DIR="$SCRIPT_DIR"
LOG_DIR="$REPO_ROOT/.claude_code_runs/ui_ux_round20"
FORMATTER="$REPO_ROOT/format_stream_claude.py"
MODEL="claude-opus-4-7"
FROM=0
TO=0
ONLY=""
CONTINUE_ON_FAIL=0
DRY_RUN=0

usage() {
  sed -n '1,34p' "$0"
}

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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:-}"; shift 2 ;;
    --to) TO="${2:-}"; shift 2 ;;
    --only) ONLY="$(normalize_prompt_num --only "${2:-}")"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --continue) CONTINUE_ON_FAIL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

if ! is_uint "$FROM" || ! is_uint "$TO"; then
  echo "error: --from and --to must be prompt numbers" >&2
  exit 2
fi

FROM_N=$((10#$FROM))
TO_N=$((10#$TO))
if [ "$FROM_N" -gt 0 ] && [ "$TO_N" -gt 0 ] && [ "$FROM_N" -gt "$TO_N" ]; then
  echo "error: --from $FROM is greater than --to $TO" >&2
  exit 2
fi

if [ "$DRY_RUN" -eq 0 ] && ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found in PATH." >&2
  echo "Install Claude Code and run 'claude /login'. This runner does not use an Anthropic API key." >&2
  exit 3
fi

if [ "$DRY_RUN" -eq 0 ] && ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for the stream formatter." >&2
  exit 3
fi

if [ ! -f "$FORMATTER" ]; then
  echo "ERROR: missing stream formatter at $FORMATTER" >&2
  exit 3
fi

mkdir -p "$LOG_DIR"

PROMPTS=()
while IFS= read -r prompt; do
  PROMPTS+=("$prompt")
done < <(find "$PROMPTS_DIR" -maxdepth 1 -type f -name '[0-9][0-9]_*.txt' | sort)

should_run() {
  local num="$1"
  if [ -n "$ONLY" ] && [ "$num" != "$ONLY" ]; then return 1; fi
  if [ "$FROM_N" -gt 0 ] && [ "$((10#$num))" -lt "$FROM_N" ]; then return 1; fi
  if [ "$TO_N" -gt 0 ] && [ "$((10#$num))" -gt "$TO_N" ]; then return 1; fi
  return 0
}

SELECTED=0
for prompt in "${PROMPTS[@]}"; do
  base="$(basename "$prompt" .txt)"
  num="${base%%_*}"
  if should_run "$num"; then SELECTED=$((SELECTED + 1)); fi
done

if [ -t 1 ]; then
  BLUE=$'\033[0;34m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
  RED=$'\033[0;31m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
  BLUE=""; GREEN=""; YELLOW=""; RED=""; BOLD=""; NC=""
fi

echo "${BOLD}Plan:${NC} ${#PROMPTS[@]} UI UX Round 20 prompts total (${SELECTED} selected)"
echo "${BOLD}Model:${NC} $MODEL"
for prompt in "${PROMPTS[@]}"; do
  base="$(basename "$prompt" .txt)"
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

CLAUDE_ARGS=(
  -p
  --permission-mode bypassPermissions
  --output-format stream-json
  --verbose
  --include-partial-messages
  --model "$MODEL"
)

on_signal() {
  echo
  echo "${RED}${BOLD}Interrupted.${NC}"
  if [ -n "${CURRENT_PROMPT_NUM:-}" ]; then
    echo "${RED}Resume with: $0 --from ${CURRENT_PROMPT_NUM}${NC}"
  fi
  exit 130
}
trap on_signal INT TERM

run_prompt() {
  local prompt="$1"
  local index="$2"
  local total="$3"
  local base num stamp raw log status
  base="$(basename "$prompt" .txt)"
  num="${base%%_*}"
  stamp="$(date +%Y%m%d_%H%M%S)"
  raw="$LOG_DIR/${stamp}_${base}.raw.jsonl"
  log="$LOG_DIR/${stamp}_${base}.log"
  CURRENT_PROMPT_NUM="$num"

  echo
  echo "${BLUE}${BOLD}== [$index/$total] $base ==${NC}"
  echo "Prompt: $prompt"
  echo "Raw log: $raw"
  echo "Rendered log: $log"

  (
    cd "$REPO_ROOT" || exit 1
    unset ANTHROPIC_API_KEY
    unset CLAUDE_API_KEY
    unset CLAUDE_CODE_API_KEY
    claude "${CLAUDE_ARGS[@]}" < "$prompt"
  ) > "$raw"
  status=$?

  python3 "$FORMATTER" < "$raw" | tee "$log"
  if [ "$status" -ne 0 ]; then
    echo "${RED}${BOLD}Prompt failed:${NC} $base (exit $status)"
    if [ "$CONTINUE_ON_FAIL" -eq 0 ]; then
      echo "Resume with: $0 --from $num"
      exit "$status"
    fi
  else
    echo "${GREEN}${BOLD}Prompt complete:${NC} $base"
  fi
}

idx=0
for prompt in "${PROMPTS[@]}"; do
  base="$(basename "$prompt" .txt)"
  num="${base%%_*}"
  if should_run "$num"; then
    idx=$((idx + 1))
    run_prompt "$prompt" "$idx" "$SELECTED"
  fi
done

echo
echo "${GREEN}${BOLD}All selected UI UX Round 20 prompts complete.${NC}"
