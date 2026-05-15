#!/bin/bash
# Active prompt batch runner -- sequentially run every active top-level
# numbered prompt in coding_prompts/ via the Claude Code CLI (`claude`).
#
# This uses the installed Claude Code CLI's existing login/subscription auth.
# It does NOT read or require an Anthropic API key, and it scrubs every
# Anthropic-related env var before invoking the CLI. If needed, run
# `claude /login` once.
#
# Streaming: invokes claude in `--output-format stream-json` mode and pipes
# the JSONL through `format_stream_claude.py` so you see tool calls and
# partial text in real time. The raw JSONL is preserved at
# .claude_code_runs/<timestamp>_<prompt>.raw.jsonl ; the human-readable
# rendering is at .claude_code_runs/<timestamp>_<prompt>.log .
#
# Usage:
#   ./run_prompts.sh
#   ./run_prompts.sh --from 3
#   ./run_prompts.sh --to 5
#   ./run_prompts.sh --from 2 --to 6
#   ./run_prompts.sh --only 04
#   ./run_prompts.sh --model claude-opus-4-7
#   ./run_prompts.sh --continue
#   ./run_prompts.sh --dry-run
#   ./run_prompts.sh --branch-mode
#
# --branch-mode (opt-in):
#   Each prompt runs on its own branch `auto/<round-suffix>/<NN>-<slug>`
#   created from current HEAD. On success the branch is pushed and (if
#   `gh` is on PATH) a draft PR is opened with the prompt's text as the
#   body. On failure the branch persists locally for inspection and the
#   runner halts as usual. Suppresses sync.sh auto-commits by exporting
#   THESEUS_RUNNER_BRANCH_MODE=1 — sync.sh checks that flag and skips.

set -uo pipefail

if [ -z "${BASH_VERSION:-}" ]; then
  echo "ERROR: this script requires bash. Run: bash $0" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$REPO_ROOT/coding_prompts"
LOG_DIR="$REPO_ROOT/.claude_code_runs"
FORMATTER="$REPO_ROOT/format_stream_claude.py"

# Default to Opus 4.7. Override with --model.
MODEL="claude-opus-4-7"

FROM=0
TO=0
ONLY=""
FROM_N=0
TO_N=0
CONTINUE_ON_FAIL=0
DRY_RUN=0
BRANCH_MODE=0
ROUND_SUFFIX=""
CURRENT_PROMPT_NUM=""
CURRENT_PROMPT_NAME=""
CURRENT_BRANCH=""

on_signal() {
  local signal="$1"
  echo
  if [ -n "${CURRENT_PROMPT_NUM:-}" ]; then
    echo "${RED:-}${BOLD:-}-- Interrupted (${signal}) during prompt ${CURRENT_PROMPT_NUM} (${CURRENT_PROMPT_NAME}). --${NC:-}"
    echo "${RED:-}Resume with: ./run_prompts.sh --from ${CURRENT_PROMPT_NUM}${NC:-}"
  else
    echo "${RED:-}${BOLD:-}-- Interrupted (${signal}) before any prompt started. --${NC:-}"
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
    --branch-mode) BRANCH_MODE=1; shift ;;
    --round-suffix) case "${2-}" in ''|--*) echo "error: --round-suffix requires a value" >&2; exit 2 ;; esac; ROUND_SUFFIX="$2"; shift 2 ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1"; exit 2 ;;
  esac
done

if [ "$BRANCH_MODE" -eq 1 ]; then
  export THESEUS_RUNNER_BRANCH_MODE=1
  if [ -z "$ROUND_SUFFIX" ]; then
    ROUND_SUFFIX=$(date +"%Y%m%d-%H%M")
  fi
fi

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

if [ "$DRY_RUN" -eq 0 ] && ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found in PATH." >&2
  echo "Install Claude Code (https://docs.claude.com/en/docs/claude-code) and run 'claude /login'." >&2
  echo "This runner does not use an Anthropic API key." >&2
  exit 3
fi

if [ "$DRY_RUN" -eq 0 ] && ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for the stream formatter." >&2
  exit 3
fi

[[ -d "$PROMPTS_DIR" ]] || { echo "$PROMPTS_DIR does not exist"; exit 3; }
[[ -f "$FORMATTER" ]] || { echo "$FORMATTER missing — re-pull the script set"; exit 3; }
mkdir -p "$LOG_DIR"

# Claude Code CLI args:
#   -p / --print                 headless single-shot mode (read prompt, run, exit)
#   --permission-mode bypassPermissions   approve all tool calls automatically
#                                (matches the spirit of `codex exec --full-auto`)
#   --output-format stream-json  emit JSONL events to stdout
#   --verbose                    required by stream-json
#   --include-partial-messages   stream text deltas as they arrive
#   --model                      pin the model. Default: claude-opus-4-7
CLAUDE_PRINT_ARGS=(
  -p
  --permission-mode bypassPermissions
  --output-format stream-json
  --verbose
  --include-partial-messages
  --model "$MODEL"
)

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
  for i in $(seq 1 "$filled" 2>/dev/null); do bar="${bar}#"; done
  for i in $(seq 1 "$empty" 2>/dev/null); do bar="${bar}-"; done
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

CLAUDE_VERSION="(claude --version unavailable)"
if [ "$DRY_RUN" -eq 0 ]; then
  CLAUDE_VERSION="$(claude --version 2>/dev/null || echo '(version probe failed)')"
fi

echo "${BOLD}Plan:${NC} ${#PROMPTS[@]} active prompts total (${SELECTED} selected; Claude Code CLI subscription runner)"
echo "${BOLD}Model:${NC} $MODEL"
echo "${BOLD}CLI:${NC} $CLAUDE_VERSION"
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
    printf "${BLUE}  [%s] still running %s (%dm %02ds elapsed)${NC}\n" \
      "$prompt_num" "$prompt_name" "$mins" "$secs"
  done
}

parse_quota_reset_to_epoch() {
  local log="$1"
  local raw cleaned epoch

  raw=$(grep -oiE "(try again at|available again at|resets at|next available at)[[:space:]]+[^.]+\\." "$log" 2>/dev/null \
    | tail -1 \
    | sed -E 's/^[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+//; s/^[^[:space:]]+[[:space:]]+//; s/\.[[:space:]]*$//')
  if [ -z "$raw" ]; then
    local mins
    mins=$(grep -oiE "available in[[:space:]]+[0-9]+[[:space:]]+(minute|min|hour|hr)" "$log" 2>/dev/null | tail -1 || true)
    if [ -n "$mins" ]; then
      local n unit
      n=$(echo "$mins" | grep -oE "[0-9]+")
      unit=$(echo "$mins" | grep -oiE "(minute|min|hour|hr)")
      case "$unit" in
        hour|hr) echo $(( $(date +%s) + n * 3600 )); return 0 ;;
        minute|min) echo $(( $(date +%s) + n * 60 )); return 0 ;;
      esac
    fi
    return 0
  fi
  cleaned=$(echo "$raw" | sed -E 's/([0-9]+)(st|nd|rd|th)/\1/g')
  epoch=$(date -j -f "%b %d, %Y %I:%M %p" "$cleaned" +%s 2>/dev/null \
    || date -d "$cleaned" +%s 2>/dev/null)
  [ -n "$epoch" ] && echo "$epoch"
}

# Run claude in stream-json mode. The raw JSONL is captured to <log>.raw.jsonl;
# the human-readable rendering goes to <log>.log AND to the terminal.
run_claude_with_retry() {
  local prompt_file="$1"
  local log_path="$2"
  local raw_path="$3"
  local num="$4"
  local quota_retries=0
  local transient_retries=0
  local max_quota_retries=4
  local max_transient_retries=2
  local rc reset_epoch now_epoch wait_s human_wait

  while :; do
    # Build the prompt envelope (founder context + prompt body) once and pipe
    # it into claude. Stream-json events come back on stdout; tee to the raw
    # log; the formatter renders them for the terminal AND writes a copy to
    # the human-readable log via tee.
    set -o pipefail
    (
      unset ANTHROPIC_API_KEY \
            ANTHROPIC_AUTH_TOKEN \
            ANTHROPIC_API_URL \
            ANTHROPIC_BASE_URL \
            ANTHROPIC_BEDROCK_BASE_URL \
            ANTHROPIC_VERTEX_BASE_URL \
            ANTHROPIC_DEFAULT_HAIKU_MODEL \
            ANTHROPIC_DEFAULT_SONNET_MODEL \
            ANTHROPIC_DEFAULT_OPUS_MODEL \
            ANTHROPIC_MODEL \
            CLAUDE_API_KEY \
            CLAUDE_CODE_USE_BEDROCK \
            CLAUDE_CODE_USE_VERTEX \
            AWS_BEARER_TOKEN_BEDROCK
      {
        echo "You are operating in /Users/michaelquintin/Desktop/Theseus."
        echo "First inspect current code and tests. If the prompt's requested work is already implemented, verify it and make only necessary repair edits. Do not duplicate landed work. Do not ask for or use an Anthropic API key; rely on the Claude Code CLI subscription session running this prompt."
        echo
        cat "$prompt_file"
      } | claude "${CLAUDE_PRINT_ARGS[@]}" 2>&1 \
        | tee "$raw_path" \
        | python3 "$FORMATTER" \
        | tee "$log_path"
    )
    rc=$?
    set +o pipefail

    if [ "$rc" -eq 0 ]; then
      return 0
    fi

    # Quota / rate-limit handling — search the raw JSONL since human log may
    # have already collapsed the message.
    if grep -qiE "(usage limit|rate limit|quota exceeded|too many requests|quota reached|reached your.* limit)" "$raw_path"; then
      quota_retries=$((quota_retries + 1))
      if [ "$quota_retries" -gt "$max_quota_retries" ]; then
        echo "${RED}Quota cap hit ${max_quota_retries} times for prompt $num - giving up.${NC}"
        echo "${RED}Resume manually with: ./run_prompts.sh --from $num${NC}"
        return "$rc"
      fi

      reset_epoch=$(parse_quota_reset_to_epoch "$raw_path")
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
        echo "${YELLOW}===============================================================${NC}"
        echo "${YELLOW}Claude Code quota exhausted on prompt ${num}.${NC}"
        echo "${YELLOW}Waiting ${wait_s}s (about ${human_wait} min, including a 90s buffer), then retrying.${NC}"
        echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}. Ctrl-C to abort.${NC}"
        echo "${YELLOW}===============================================================${NC}"
        sleep "$wait_s"
        continue
      fi

      echo
      echo "${YELLOW}===============================================================${NC}"
      echo "${YELLOW}Claude Code quota error detected, but reset time could not be parsed.${NC}"
      echo "${YELLOW}Sleeping 60 minutes as a conservative fallback, then retrying.${NC}"
      echo "${YELLOW}Quota retry ${quota_retries}/${max_quota_retries}.${NC}"
      echo "${YELLOW}===============================================================${NC}"
      sleep 3600
      continue
    fi

    if grep -qiE "(not.*logged in|please.*login|authentication required|invalid credentials|token expired|/login)" "$raw_path"; then
      echo "${RED}Claude Code reports an auth problem. Run 'claude /login' and retry.${NC}"
      return "$rc"
    fi

    transient_retries=$((transient_retries + 1))
    if [ "$transient_retries" -gt "$max_transient_retries" ]; then
      echo "${RED}Claude Code returned exit $rc after ${max_transient_retries} retries - treating as real failure.${NC}"
      return "$rc"
    fi
    echo "${YELLOW}Claude Code returned exit $rc with no quota signature - treating as transient.${NC}"
    echo "${YELLOW}Retrying in 30s (attempt ${transient_retries}/${max_transient_retries}).${NC}"
    sleep 30
  done
}

slugify_prompt_name() {
  # Take the part after the leading "NN_" and squash to a kebab slug.
  local base="$1"
  local rest="${base#*_}"
  echo "$rest" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
    | cut -c1-60
}

# Open the per-prompt branch. Echoes the branch name. Returns non-zero
# if the branch could not be created (dirty tree, name collision, etc).
branch_mode_enter() {
  local num="$1" base="$2"
  local slug branch
  slug=$(slugify_prompt_name "$base")
  branch="auto/${ROUND_SUFFIX}/${num}-${slug}"

  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "${RED}branch-mode: working tree dirty — commit or stash before running.${NC}" >&2
    return 1
  fi
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    echo "${RED}branch-mode: branch $branch already exists.${NC}" >&2
    return 1
  fi
  if ! git checkout -b "$branch" >/dev/null 2>&1; then
    echo "${RED}branch-mode: git checkout -b $branch failed.${NC}" >&2
    return 1
  fi
  echo "$branch"
  return 0
}

# On success: commit anything the prompt produced, push, open draft PR.
branch_mode_finalize() {
  local branch="$1" prompt_file="$2" num="$3" base="$4"
  local title

  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    git add -A
    THESEUS_SKIP_PRECOMMIT=1 git commit -m "[Round-${num}] ${base} (auto)" >/dev/null 2>&1 || {
      echo "${YELLOW}branch-mode: nothing to commit on $branch.${NC}"
    }
  else
    echo "${YELLOW}branch-mode: prompt produced no changes — branch $branch left as a marker.${NC}"
  fi

  if git config --get remote.origin.url >/dev/null 2>&1; then
    if ! git push -u origin "$branch" >/dev/null 2>&1; then
      echo "${YELLOW}branch-mode: git push failed for $branch; left local.${NC}"
      return 0
    fi
  else
    echo "${YELLOW}branch-mode: no origin remote — left $branch local only.${NC}"
    return 0
  fi

  if command -v gh >/dev/null 2>&1; then
    title="[Round-${num}] ${base}"
    if ! gh pr create --draft --title "$title" --body-file "$prompt_file" --head "$branch" >/dev/null 2>&1; then
      echo "${YELLOW}branch-mode: gh pr create failed for $branch.${NC}"
    else
      echo "${GREEN}branch-mode: draft PR opened for $branch.${NC}"
    fi
  else
    echo "${YELLOW}branch-mode: gh CLI not installed — no PR opened. Branch pushed.${NC}"
  fi
}

run_prompt() {
  local prompt="$1"
  local index="$2"
  local total="$3"
  local base num stamp log raw status start elapsed bar pct total_elapsed total_mins hb branch
  base=$(basename "$prompt" .txt)
  num="${base%%_*}"
  stamp=$(date +"%Y%m%d-%H%M%S")
  log="$LOG_DIR/${stamp}_${base}.log"
  raw="$LOG_DIR/${stamp}_${base}.raw.jsonl"
  CURRENT_PROMPT_NUM="$num"
  CURRENT_PROMPT_NAME="$base"
  branch=""

  if [ "$BRANCH_MODE" -eq 1 ]; then
    branch=$(branch_mode_enter "$num" "$base") || return 2
    CURRENT_BRANCH="$branch"
    echo "${BLUE}branch-mode: ${branch}${NC}"
  fi

  bar=$(make_progress_bar "$((index - 1))" "$total" 12)
  pct=$(((index - 1) * 100 / (total == 0 ? 1 : total)))
  total_elapsed=$(($(date +%s) - OVERALL_START))
  total_mins=$((total_elapsed / 60))

  echo
  echo "${BLUE}--------------------------------------------------------------${NC}"
  printf "${BOLD}${BLUE}[%d/%d]${NC} ${BLUE}%s${NC}  ${BOLD}${BLUE}%3d%%${NC}   ${BLUE}batch so far: %dm${NC}\n" \
    "$index" "$total" "$bar" "$pct" "$total_mins"
  printf "${BOLD}${BLUE}> %s${NC}   ${BLUE}log: %s${NC}\n" "$base" "$log"
  printf "${BLUE}  raw: %s${NC}\n" "$raw"
  echo "${BLUE}--------------------------------------------------------------${NC}"

  start=$(date +%s)

  heartbeat_loop "$num" "$base" "$start" &
  hb=$!
  disown "$hb" 2>/dev/null || true

  run_claude_with_retry "$prompt" "$log" "$raw" "$num"
  status=$?

  kill "$hb" >/dev/null 2>&1 || true
  wait "$hb" >/dev/null 2>&1 || true

  elapsed=$(($(date +%s) - start))
  if [ "$status" -eq 0 ]; then
    echo "${GREEN}OK ${base} complete (${elapsed}s)${NC}"
    if [ "$BRANCH_MODE" -eq 1 ] && [ -n "$branch" ]; then
      branch_mode_finalize "$branch" "$prompt" "$num" "$base"
    fi
  else
    echo "${RED}${BOLD}FAIL ${base} (exit ${status}, ${elapsed}s)${NC}"
    echo "${RED}   log: $log${NC}"
    echo "${RED}   raw: $raw${NC}"
    if [ "$BRANCH_MODE" -eq 1 ] && [ -n "$branch" ]; then
      echo "${RED}   branch: $branch (left local for inspection)${NC}"
    fi
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
  echo "${BLUE}--------------------------------------------------------------${NC}"
  printf "${GREEN}${BOLD}OK Active batch complete${NC}        %s   ${GREEN}%d/%d ok${NC}   ${BLUE}%dm %02ds${NC}\n" \
    "$final_bar" "$ok" "$SELECTED" "$total_mins" "$total_secs"
  echo "${BLUE}Logs:${NC} $LOG_DIR"
  echo "${BLUE}--------------------------------------------------------------${NC}"
else
  echo "${BLUE}--------------------------------------------------------------${NC}"
  printf "${RED}${BOLD}FAIL Active batch halted${NC}         %s   ${RED}%d/%d ran, %d fail${NC}   ${BLUE}%dm %02ds${NC}\n" \
    "$final_bar" "$ran" "$SELECTED" "$failed" "$total_mins" "$total_secs"
  echo "${BLUE}Logs:${NC} $LOG_DIR"
  echo "${BLUE}--------------------------------------------------------------${NC}"
  exit 1
fi
