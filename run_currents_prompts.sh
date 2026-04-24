#!/usr/bin/env bash
# run_currents_prompts.sh
#
# Execute the 17-prompt Currents series via Claude Code, one prompt per session,
# billed to the logged-in Claude subscription (NOT an Anthropic API key).
#
# REQUIREMENTS
#   1. `claude` CLI installed.
#        npm install -g @anthropic-ai/claude-code
#   2. Logged in with a Claude subscription account, not an API key:
#        claude login         # choose "Claude subscription / claude.ai"
#      Verify with:
#        claude /status       # should show "subscription" not "api key"
#   3. ANTHROPIC_API_KEY must NOT be set in the shell. The script unsets it
#      defensively so a stray env var can't silently bill your API balance.
#
# USAGE
#   chmod +x run_currents_prompts.sh
#   ./run_currents_prompts.sh                 # all 17, in order
#   ./run_currents_prompts.sh 5               # only prompt 5
#   ./run_currents_prompts.sh 3 7             # prompts 3 through 7 inclusive
#   DRY_RUN=1 ./run_currents_prompts.sh       # print what would run, don't run
#
# BEHAVIOR
#   For each prompt file NN_*.txt found in Claude_Code_Prompts/ :
#     - prints a header with the prompt number, filename, and timestamp
#     - pipes the full prompt into `claude --print --verbose
#       --dangerously-skip-permissions`
#     - streams Claude's output to the terminal AND tees it to a log file
#     - on non-zero exit, asks whether to continue with the next prompt
#
#   Between prompts, each invocation is a FRESH Claude Code session. That is
#   deliberate — the prompts are designed to be self-contained (each starts by
#   reading the current repo state) and a fresh session prevents context decay
#   across the 17-step run.
#
# SAFETY NOTES
#   --dangerously-skip-permissions lets Claude Code edit files, run shell
#   commands, install packages, etc. without asking. That is necessary for
#   unattended execution of the series, but it is also what the flag name
#   says it is. Before running, make sure:
#     - the repo is clean (`git status`), so you can `git diff` / revert
#     - you are in the correct project directory
#     - you have a recent backup or are on a branch you can throw away
#
#   If anything goes sideways, kill the script with Ctrl-C. The shell handles
#   SIGINT cleanly and Claude Code will abort the in-flight tool use.

set -uo pipefail

# macOS ships bash 3.2. We need some bash features (arrays, process
# substitution) but avoid bash-4-only ones (mapfile, ${var,,}, etc.).
# If running under /bin/sh or dash, bail early with a useful message.
if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "ERROR: this script needs bash (not sh/dash). Run:  bash $0" >&2
  exit 1
fi

# ----- Config ---------------------------------------------------------------
PROJECT_ROOT="/Users/michaelquintin/Desktop/Theseus"
PROMPT_DIR="$PROJECT_ROOT/Claude_Code_Prompts"
LOG_DIR="$PROMPT_DIR/logs"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
FORMATTER="$PROJECT_ROOT/cc_stream_formatter.py"

# ----- Arg parsing ----------------------------------------------------------
if [[ $# -eq 0 ]]; then
  START=1
  END=17
elif [[ $# -eq 1 ]]; then
  START=$1
  END=$1
else
  START=$1
  END=$2
fi

mkdir -p "$LOG_DIR"
SUMMARY_LOG="$LOG_DIR/run_${RUN_TS}_summary.log"

log() { printf '%s\n' "$*" | tee -a "$SUMMARY_LOG"; }

# ----- Pre-flight -----------------------------------------------------------
if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found in PATH." >&2
  echo "Install with:  npm install -g @anthropic-ai/claude-code" >&2
  exit 1
fi

# python3 is required for the stream formatter that turns Claude Code's
# stream-json output into a readable narrative. macOS has included python3
# since 12.3; if it's missing the script falls back to plain text mode.
if command -v python3 >/dev/null 2>&1 && [[ -f "$FORMATTER" ]]; then
  HAVE_FORMATTER=1
else
  HAVE_FORMATTER=0
  echo "[warn] $FORMATTER or python3 not available — falling back to plain text output." >&2
fi

# stdbuf keeps output line-buffered so tee flushes progressively. It ships with
# GNU coreutils (Linux default; macOS needs `brew install coreutils`, which
# installs it as `gstdbuf`). If neither is present we drop it — Claude Code
# already streams, so the only loss is occasional chunking inside `tee`.
if command -v stdbuf >/dev/null 2>&1; then
  LINEBUF=(stdbuf -oL -eL)
elif command -v gstdbuf >/dev/null 2>&1; then
  LINEBUF=(gstdbuf -oL -eL)
else
  LINEBUF=()
fi

# Critical: force subscription billing by removing any API-key env vars.
# (Affects this script's process only; your interactive shell is untouched.)
for var in ANTHROPIC_API_KEY CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX \
           ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL; do
  if [[ -n "${!var:-}" ]]; then
    echo "[guard] unsetting $var for this run (was set in the calling shell)"
    unset "$var"
  fi
done

if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "ERROR: PROJECT_ROOT does not exist: $PROJECT_ROOT" >&2
  exit 1
fi
cd "$PROJECT_ROOT"

# ----- Collect prompts ------------------------------------------------------
# Only top-level NN_*.txt files in Claude_Code_Prompts/ (not archives).
# Portable to bash 3.2 (macOS default): no `mapfile`.
PROMPTS=()
while IFS= read -r line; do
  PROMPTS+=("$line")
done < <(find "$PROMPT_DIR" -maxdepth 1 -type f -name '[0-9][0-9]_*.txt' | sort)

if [[ ${#PROMPTS[@]} -eq 0 ]]; then
  echo "ERROR: no numbered prompt files found in $PROMPT_DIR" >&2
  exit 1
fi

# ----- Banner ---------------------------------------------------------------
log "════════════════════════════════════════════════════════════════"
log "  Currents prompt runner"
log "  Run id:         $RUN_TS"
log "  Project root:   $PROJECT_ROOT"
log "  Prompts found:  ${#PROMPTS[@]}"
log "  Requested:      prompts $START through $END"
log "  Log directory:  $LOG_DIR"
log "  Billing:        Claude subscription (API key env vars unset)"
if [[ "$HAVE_FORMATTER" = "1" ]]; then
  log "  Output mode:    stream-json → formatter (live tool calls + text)"
else
  log "  Output mode:    plain verbose text"
fi
log "════════════════════════════════════════════════════════════════"
log ""
log "Legend:"
log "  ●  session start    ~  thinking"
log "  →  tool call        ✓  tool result (success)"
log "  ✗  tool error       ◼  prompt complete"
log "  Claude: ...         streamed assistant text"
log ""

# Quick subscription sanity check. `claude /status` is interactive, so we
# do a lightweight probe instead — a tiny `--print` call that will itself
# fail fast if no auth is configured.
log ""
log "[check] verifying claude CLI auth is configured..."
if ! echo "ping" | claude --print --dangerously-skip-permissions \
      >"$LOG_DIR/run_${RUN_TS}_auth_probe.log" 2>&1; then
  log "ERROR: 'claude --print' probe failed. See:"
  log "       $LOG_DIR/run_${RUN_TS}_auth_probe.log"
  log "Common causes:"
  log "  - not logged in:   run  'claude login'  and pick the subscription option"
  log "  - no network:      the probe needs to reach Anthropic"
  exit 1
fi
log "[check] OK"

# ----- Execute --------------------------------------------------------------
ran=0
failed=0

for prompt_path in "${PROMPTS[@]}"; do
  basename="$(basename "$prompt_path")"
  num="${basename:0:2}"
  n=$((10#$num))  # force base-10 so leading zeros don't trigger octal parse

  if (( n < START || n > END )); then
    continue
  fi

  step_log="$LOG_DIR/run_${RUN_TS}_prompt_${num}.log"

  log ""
  log "════════════════════════════════════════════════════════════════"
  log "  ▶  PROMPT $num   $basename"
  log "     started:  $(date)"
  log "     log file: $step_log"
  log "════════════════════════════════════════════════════════════════"

  if [[ "${DRY_RUN:-0}" = "1" ]]; then
    log "  (dry run — skipping execution)"
    continue
  fi

  # The actual call.
  #
  # --print                        non-interactive; print and exit
  # --verbose                      stream tool-use events so progress is visible
  # --dangerously-skip-permissions auto-approve all tool use (required for unattended run)
  #
  # stdbuf -oL -eL keeps output line-buffered so tee flushes to terminal +
  # file in real time rather than waiting for Claude to close its pipe.
  #
  # PIPESTATUS is used to capture claude's exit code despite the tee at the
  # end of the pipeline.
  raw_log="$LOG_DIR/run_${RUN_TS}_prompt_${num}.raw.jsonl"
  start_epoch=$(date +%s)

  # Two output modes:
  #  - with formatter: claude emits NDJSON → tee raw → python formatter →
  #    tee pretty. The user sees a running narrative of thinking, tool
  #    calls, tool results, and streamed assistant text.
  #  - without: plain --verbose text.
  #
  # `${LINEBUF[@]+"${LINEBUF[@]}"}` is the bash-3.2-safe way to splice an
  # array that may be empty.
  if [[ "$HAVE_FORMATTER" = "1" ]]; then
    ${LINEBUF[@]+"${LINEBUF[@]}"} claude \
        --print \
        --verbose \
        --output-format stream-json \
        --dangerously-skip-permissions \
        < "$prompt_path" \
      2> >(tee -a "$step_log" >&2) \
      | tee "$raw_log" \
      | python3 "$FORMATTER" \
      | tee -a "$step_log"
    exit_code=${PIPESTATUS[0]}
  else
    ${LINEBUF[@]+"${LINEBUF[@]}"} claude \
        --print \
        --verbose \
        --dangerously-skip-permissions \
        < "$prompt_path" \
      2>&1 | tee "$step_log"
    exit_code=${PIPESTATUS[0]}
  fi

  end_epoch=$(date +%s)
  elapsed=$(( end_epoch - start_epoch ))

  ran=$((ran + 1))
  if [[ $exit_code -eq 0 ]]; then
    log ""
    log "  ✓  PROMPT $num finished in ${elapsed}s"
  else
    failed=$((failed + 1))
    log ""
    log "  ✗  PROMPT $num exited with code $exit_code after ${elapsed}s"
    log "     full log: $step_log"
    # Prompt for continuation only if stdin is a TTY; otherwise stop.
    if [[ -t 0 ]]; then
      read -r -p "     continue with next prompt anyway? [y/N] " reply
      case "$reply" in
        y|Y|yes|YES) log "     continuing..." ;;
        *) log "     stopping."; break ;;
      esac
    else
      log "     stdin not a tty; stopping."
      break
    fi
  fi
done

# ----- Summary --------------------------------------------------------------
log ""
log "════════════════════════════════════════════════════════════════"
log "  Run complete:  $(date)"
log "  Prompts run:   $ran"
log "  Failures:      $failed"
log "  Summary log:   $SUMMARY_LOG"
log "════════════════════════════════════════════════════════════════"

[[ $failed -eq 0 ]] || exit 2
