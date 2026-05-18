#!/bin/bash
set -e
cd "$(git rev-parse --show-toplevel)"

# ──────────────────────────────────────────────────────────────────────────────
# Completion banner helpers — every success/exit path prints a loud banner so
# you can tell at a glance whether the sync is fully done (vs. still waiting).
# Colors auto-disable when stdout isn't a TTY (e.g. piped/redirected).
# ──────────────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_RESET=$'\033[0m'
  C_GREEN=$'\033[1;32m'
  C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""
fi

# print_banner <color> <title> [line1] [line2] ...
print_banner() {
  local color="$1"; shift
  local title="$1"; shift
  local bar
  bar=$(printf '═%.0s' $(seq 1 70))
  echo ""
  printf '%s%s%s\n' "$color" "$bar" "$C_RESET"
  printf '%s  %s%s\n' "$color" "$title" "$C_RESET"
  local line
  for line in "$@"; do
    printf '%s  %s%s\n' "$color" "$line" "$C_RESET"
  done
  printf '%s%s%s\n' "$color" "$bar" "$C_RESET"
  echo ""
}

banner_success()  { print_banner "$C_GREEN"  "✓ SYNC COMPLETE"  "$@"; }
banner_partial()  { print_banner "$C_YELLOW" "⚠ SYNC PARTIAL"   "$@"; }
banner_skipped()  { print_banner "$C_YELLOW" "○ SYNC SKIPPED"   "$@"; }
banner_failed()   { print_banner "$C_RED"    "✗ SYNC FAILED"    "$@"; }

# ──────────────────────────────────────────────────────────────────────────────
# Workflow audit — waits for every CI workflow run triggered by the pushed
# commit (headSha == $pushed_sha) to reach a terminal state, then tallies and
# prints failures. Idempotent and read-only — never mutates GitHub state.
#
# Why this exists: Rolling Release is only ONE of many workflows the firm
# runs on every push (Integrity, Type Contracts, smoke, Accessibility,
# Dead-code survey, Round-3 invariants, …). Watching only Rolling Release
# meant the sync banner could print "✓ SYNC COMPLETE" while five other
# workflows were silently failing. The historical fallout was hours of
# operator time spent re-discovering those failures one-at-a-time over
# subsequent days. This audit closes that gap.
#
# Sets the following globals so the banner block downstream can branch on
# them without re-running gh:
#   WORKFLOW_AUDIT_STATUS    success | failed | inflight | unchecked
#   WORKFLOW_AUDIT_TOTAL     number of runs observed
#   WORKFLOW_AUDIT_SUCCESS   success + skipped + neutral
#   WORKFLOW_AUDIT_FAILURE   failure + timed_out + cancelled + startup_failure
#   WORKFLOW_AUDIT_INFLIGHT  runs still in_progress / queued after max wait
#
# Env knobs:
#   SYNC_SKIP_WORKFLOW_AUDIT=1               opt out entirely
#   SYNC_WORKFLOW_AUDIT_MAX_WAIT_SECONDS=N   default 1800 (30 min) — covers
#                                            the longest known job (Round-3
#                                            invariants, ~16 min) with
#                                            generous headroom.
#   SYNC_WORKFLOW_AUDIT_POLL_SECONDS=N       default 20 — how often to poll.
# ──────────────────────────────────────────────────────────────────────────────
WORKFLOW_AUDIT_STATUS="unchecked"
WORKFLOW_AUDIT_TOTAL=0
WORKFLOW_AUDIT_SUCCESS=0
WORKFLOW_AUDIT_FAILURE=0
WORKFLOW_AUDIT_INFLIGHT=0

audit_all_workflows() {
  local sha="$1"
  local max_wait_seconds="${SYNC_WORKFLOW_AUDIT_MAX_WAIT_SECONDS:-1800}"
  local poll_interval="${SYNC_WORKFLOW_AUDIT_POLL_SECONDS:-20}"
  local started elapsed pending_count
  started=$(date +%s)

  if [ -z "$sha" ]; then
    WORKFLOW_AUDIT_STATUS="unchecked"
    return 0
  fi

  echo ""
  echo "=== Auditing every CI workflow run for commit ${sha:0:7} ==="
  echo "    (waiting up to ${max_wait_seconds}s for in-progress runs)"

  while true; do
    # `gh run list --commit <full-sha>` filters runs by headSha. status is
    # one of: completed | queued | in_progress | waiting | requested |
    # pending. Anything other than "completed" still needs more time.
    pending_count="$(gh run list --commit "$sha" --limit 60 \
      --json status \
      --jq '[.[] | select(.status != "completed")] | length' 2>/dev/null || echo 0)"

    [ -z "$pending_count" ] && pending_count=0
    if [ "$pending_count" -eq 0 ]; then
      break
    fi

    elapsed=$(($(date +%s) - started))
    if [ "$elapsed" -ge "$max_wait_seconds" ]; then
      echo "    audit timed out after ${max_wait_seconds}s with $pending_count run(s) still in flight"
      break
    fi
    echo "    $pending_count workflow run(s) still in progress (elapsed ${elapsed}s)"
    sleep "$poll_interval"
  done

  WORKFLOW_AUDIT_TOTAL="$(gh run list --commit "$sha" --limit 60 \
    --json databaseId --jq 'length' 2>/dev/null || echo 0)"
  WORKFLOW_AUDIT_SUCCESS="$(gh run list --commit "$sha" --limit 60 \
    --json conclusion \
    --jq '[.[] | select(.conclusion == "success" or .conclusion == "skipped" or .conclusion == "neutral")] | length' 2>/dev/null || echo 0)"
  WORKFLOW_AUDIT_FAILURE="$(gh run list --commit "$sha" --limit 60 \
    --json conclusion \
    --jq '[.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "cancelled" or .conclusion == "startup_failure" or .conclusion == "action_required")] | length' 2>/dev/null || echo 0)"
  [ -z "$WORKFLOW_AUDIT_TOTAL" ]   && WORKFLOW_AUDIT_TOTAL=0
  [ -z "$WORKFLOW_AUDIT_SUCCESS" ] && WORKFLOW_AUDIT_SUCCESS=0
  [ -z "$WORKFLOW_AUDIT_FAILURE" ] && WORKFLOW_AUDIT_FAILURE=0
  WORKFLOW_AUDIT_INFLIGHT=$((WORKFLOW_AUDIT_TOTAL - WORKFLOW_AUDIT_SUCCESS - WORKFLOW_AUDIT_FAILURE))
  [ "$WORKFLOW_AUDIT_INFLIGHT" -lt 0 ] && WORKFLOW_AUDIT_INFLIGHT=0

  if [ "$WORKFLOW_AUDIT_FAILURE" -gt 0 ]; then
    echo ""
    echo "${C_RED}    ${WORKFLOW_AUDIT_FAILURE} workflow run(s) FAILED on this commit:${C_RESET}"
    gh run list --commit "$sha" --limit 60 \
      --json conclusion,workflowName,url \
      --jq '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "cancelled" or .conclusion == "startup_failure") | "      - " + .workflowName + " (" + .conclusion + ")\n        " + .url' \
      2>/dev/null || true
    WORKFLOW_AUDIT_STATUS="failed"
  elif [ "$WORKFLOW_AUDIT_INFLIGHT" -gt 0 ]; then
    WORKFLOW_AUDIT_STATUS="inflight"
  else
    WORKFLOW_AUDIT_STATUS="success"
  fi

  echo ""
  echo "    Workflows: ${WORKFLOW_AUDIT_SUCCESS} passed · ${WORKFLOW_AUDIT_FAILURE} failed · ${WORKFLOW_AUDIT_INFLIGHT} still in flight (of ${WORKFLOW_AUDIT_TOTAL})"
}

SECRET_TMP_FILES=()
cleanup_secret_tmp_files() {
  local f
  for f in "${SECRET_TMP_FILES[@]}"; do
    [ -n "$f" ] && rm -f "$f" 2>/dev/null || true
  done
}

# If the script dies unexpectedly (set -e tripped by an unhandled error),
# show a clear failure banner instead of an ambiguous silent exit.
trap 'rc=$?; cleanup_secret_tmp_files; if [ $rc -ne 0 ]; then banner_failed "Script exited with code $rc" "Scroll up for the actual error."; fi' EXIT

# ──────────────────────────────────────────────────────────────────────────────
# Credential rotation before GitHub sync
#
# By default, every real sync rotates the Supabase Postgres password before the
# push. That ordering matters: GitHub Actions and Vercel receive the fresh env
# values before the pushed commit can trigger CI/deployment.
#
# Requirements:
#   SUPABASE_ACCESS_TOKEN must be set unless SYNC_SKIP_DB_ROTATION=1.
#   gh must be authenticated for GitHub secret writes.
#   npx/vercel must be authenticated and linked for Vercel env writes.
#
# Recovery archive:
#   The generated password is written to an encrypted, gitignored local archive
#   before Supabase is touched. If the process is interrupted after the password
#   reset, this archive is the recovery path.
#   In OpenSSL mode the script prompts for a fresh archive password, verifies it
#   itself, decrypt-checks the archive, and aborts before rotation on any mismatch.
#
# Controls:
#   SYNC_SKIP_DB_ROTATION=1              emergency bypass
#   SYNC_DB_PASSWORD_ARCHIVE_MODE=auto   auto|gpg|openssl|plain
#   SYNC_DB_PASSWORD_GPG_RECIPIENT=...   use public-key GPG instead of passphrase
#   SYNC_DB_PASSWORD_KEYCHAIN_SERVICE=... default theseus-sync-db-password-archive
#   SYNC_DB_PASSWORD_KEYCHAIN_ACCOUNT=... default mqtheseuswork
#   SYNC_DB_PASSWORD_ARCHIVE_PROMPT=1    fallback to terminal prompt if Keychain
#                                        is unavailable (off by default because
#                                        Cursor/VS Code tasks often cannot
#                                        handle hidden prompt input reliably)
#   SYNC_DB_PASSWORD_SECRET_DIR=...      default .theseus-secrets/db-password-rotations
#   SYNC_DB_ROTATE_REDEPLOY=0            skip Vercel redeploy after DB rotation
#   CURRENTS_BACKEND_REFRESH_CMD=...     command that updates/restarts the
#                                        external Currents API/scheduler host
#   SYNC_CURRENTS_BACKEND_REFRESH_REQUIRED=1
#                                        fail before rotating unless the hook
#                                        above is set (default: 1)
# ──────────────────────────────────────────────────────────────────────────────
DB_ROTATION_LINE="DB password rotation: not run"

generate_db_password() {
  node <<'NODE'
const crypto = require("crypto");
const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
let out = "";
for (let i = 0; i < 48; i += 1) out += alphabet[crypto.randomInt(alphabet.length)];
process.stdout.write(out);
NODE
}

infer_supabase_project_ref_for_sync() {
  node <<'NODE'
const fs = require("fs");
const candidates = [
  ".env",
  ".vercel/.env.production.local",
  "current_events_api/.env",
  "theseus-codex/.env",
];
const envRef = process.env.SUPABASE_PROJECT_REF;
if (envRef) {
  process.stdout.write(envRef);
  process.exit(0);
}
for (const file of candidates) {
  if (!fs.existsSync(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  const match =
    text.match(/postgres\.([a-z0-9]{20})/i) ||
    text.match(/db\.([a-z0-9]{20})\.supabase\.co/i);
  if (match) {
    process.stdout.write(match[1]);
    process.exit(0);
  }
}
process.stdout.write("unknown");
NODE
}

db_password_archive_keychain_service() {
  printf '%s' "${SYNC_DB_PASSWORD_KEYCHAIN_SERVICE:-theseus-sync-db-password-archive}"
}

db_password_archive_keychain_account() {
  printf '%s' "${SYNC_DB_PASSWORD_KEYCHAIN_ACCOUNT:-mqtheseuswork}"
}

prompt_db_password_archive_password() {
  local pass_one pass_two
  if [ ! -r /dev/tty ]; then
    return 1
  fi

  printf "Choose DB password recovery archive encryption password: " >/dev/tty
  IFS= read -r -s pass_one </dev/tty || {
    echo "" >/dev/tty
    return 1
  }
  echo "" >/dev/tty
  printf "Verify DB password recovery archive encryption password: " >/dev/tty
  IFS= read -r -s pass_two </dev/tty || {
    echo "" >/dev/tty
    return 1
  }
  echo "" >/dev/tty

  if [ -z "$pass_one" ]; then
    echo "ERROR: recovery archive encryption password cannot be empty." >&2
    return 1
  fi
  if [ "$pass_one" != "$pass_two" ]; then
    echo "ERROR: recovery archive encryption passwords did not match." >&2
    return 1
  fi

  printf '%s' "$pass_one"
}

read_db_password_archive_password() {
  local password
  if command -v security >/dev/null 2>&1; then
    if password="$(security find-generic-password \
      -a "$(db_password_archive_keychain_account)" \
      -s "$(db_password_archive_keychain_service)" \
      -w 2>/dev/null)" && [ -n "$password" ]; then
      printf '%s' "$password"
      return 0
    fi
  fi

  if [ "${SYNC_DB_PASSWORD_ARCHIVE_PROMPT:-0}" = "1" ]; then
    prompt_db_password_archive_password
    return $?
  fi

  return 1
}

write_db_password_recovery_archive() {
  local password_file="$1"
  local project_ref="$2"
  local secret_dir="${SYNC_DB_PASSWORD_SECRET_DIR:-.theseus-secrets/db-password-rotations}"
  local mode="${SYNC_DB_PASSWORD_ARCHIVE_MODE:-auto}"
  local ts plain archive
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  if ! mkdir -p "$secret_dir"; then
    echo "ERROR: failed to create DB password recovery archive directory: $secret_dir" >&2
    return 1
  fi
  chmod 700 ".theseus-secrets" "$secret_dir" 2>/dev/null || true

  if ! plain="$(mktemp /tmp/theseus-db-password-report.XXXXXX)"; then
    echo "ERROR: failed to create temporary DB password recovery report." >&2
    return 1
  fi
  if ! chmod 600 "$plain"; then
    echo "ERROR: failed to secure temporary DB password recovery report." >&2
    rm -f "$plain"
    return 1
  fi
  SECRET_TMP_FILES+=("$plain")

  if ! {
    echo "Theseus Supabase database password rotation"
    echo "Created UTC: $ts"
    echo "Repository: $(git remote get-url origin 2>/dev/null || pwd)"
    echo "Project ref: $project_ref"
    echo "Generated by: scripts/sync-to-github.sh"
    echo ""
    echo "This archive is written before the Supabase reset, so it remains useful"
    echo "if the rotation is interrupted after the database password changes."
    echo "Confirm the sync log before assuming all external consumers updated."
    echo ""
    echo "New database password:"
    cat "$password_file"
    echo ""
    echo ""
    echo "Consumers the rotation script updates:"
    echo "- local ignored dotenv files containing this project Postgres URL"
    echo "- GitHub Actions secret CODEX_DATABASE_URL"
    echo "- Vercel DATABASE_URL and DIRECT_URL in production, preview, development"
    echo "- external Currents API/scheduler if CURRENTS_BACKEND_REFRESH_CMD is set"
  } > "$plain"; then
    echo "ERROR: failed to write temporary DB password recovery report." >&2
    rm -f "$plain"
    return 1
  fi

  if [ "$mode" = "auto" ]; then
    if command -v gpg >/dev/null 2>&1; then
      mode="gpg"
    elif command -v openssl >/dev/null 2>&1; then
      mode="openssl"
    else
      mode="none"
    fi
  fi

  case "$mode" in
    gpg)
      archive="${secret_dir}/supabase-db-password-${ts}.txt.gpg"
      if [ -n "${SYNC_DB_PASSWORD_GPG_RECIPIENT:-}" ]; then
        if ! gpg --batch --yes --trust-model always \
          --recipient "$SYNC_DB_PASSWORD_GPG_RECIPIENT" \
          --output "$archive" --encrypt "$plain"; then
          echo "ERROR: failed to encrypt DB password recovery archive with GPG recipient ${SYNC_DB_PASSWORD_GPG_RECIPIENT}." >&2
          rm -f "$archive" "$plain"
          return 1
        fi
      else
        if ! gpg --symmetric --cipher-algo AES256 --output "$archive" "$plain"; then
          echo "ERROR: failed to encrypt DB password recovery archive with GPG symmetric encryption." >&2
          rm -f "$archive" "$plain"
          return 1
        fi
      fi
      if [ ! -s "$archive" ]; then
        echo "ERROR: encrypted DB password recovery archive is missing or empty." >&2
        rm -f "$archive" "$plain"
        return 1
      fi
      ;;
    openssl)
      archive="${secret_dir}/supabase-db-password-${ts}.txt.openssl.enc"
      local archive_tmp pass_file archive_password
      archive_tmp="${archive}.tmp.$$"
      if ! pass_file="$(mktemp /tmp/theseus-db-archive-pass.XXXXXX)"; then
        echo "ERROR: failed to create temporary OpenSSL password file." >&2
        rm -f "$archive_tmp" "$plain"
        return 1
      fi
      chmod 600 "$pass_file"
      SECRET_TMP_FILES+=("$pass_file" "$archive_tmp")

      if ! archive_password="$(read_db_password_archive_password)"; then
        echo "ERROR: DB password recovery archive password is not set." >&2
        echo "Run this once, then rerun sync:" >&2
        echo "  ./scripts/setup-sync-db-archive-password.sh --reset" >&2
        echo "If you intentionally want an interactive terminal prompt instead, run:" >&2
        echo "  SYNC_DB_PASSWORD_ARCHIVE_PROMPT=1 ./scripts/sync-to-github.sh" >&2
        echo "No database password rotation was attempted." >&2
        rm -f "$archive_tmp" "$pass_file" "$plain"
        return 1
      fi

      printf '%s' "$archive_password" > "$pass_file"
      unset archive_password

      if ! openssl enc -aes-256-cbc -salt -pbkdf2 -iter 210000 \
        -pass "file:${pass_file}" -in "$plain" -out "$archive_tmp"; then
        echo "ERROR: failed to encrypt the DB password recovery archive." >&2
        echo "Database password rotation was not started." >&2
        rm -f "$archive_tmp" "$pass_file" "$plain"
        return 1
      fi

      if [ ! -s "$archive_tmp" ]; then
        echo "ERROR: encrypted DB password recovery archive is empty." >&2
        echo "Database password rotation was not started." >&2
        rm -f "$archive_tmp" "$pass_file" "$plain"
        return 1
      fi

      if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 210000 \
        -pass "file:${pass_file}" -in "$archive_tmp" >/dev/null; then
        echo "ERROR: encrypted DB password recovery archive failed verification." >&2
        echo "Database password rotation was not started." >&2
        rm -f "$archive_tmp" "$pass_file" "$plain"
        return 1
      fi

      mv "$archive_tmp" "$archive"
      rm -f "$pass_file"
      ;;
    plain)
      archive="${secret_dir}/supabase-db-password-${ts}.txt"
      if ! cp "$plain" "$archive"; then
        echo "ERROR: failed to write plaintext DB password recovery archive." >&2
        rm -f "$archive" "$plain"
        return 1
      fi
      chmod 600 "$archive"
      echo "${C_YELLOW}WARNING: password archive was stored in plaintext because SYNC_DB_PASSWORD_ARCHIVE_MODE=plain.${C_RESET}" >&2
      ;;
    none)
      echo "ERROR: no supported encryption tool found for password recovery archive." >&2
      echo "Install gpg, install openssl, set SYNC_DB_PASSWORD_GPG_RECIPIENT, or explicitly set SYNC_DB_PASSWORD_ARCHIVE_MODE=plain." >&2
      return 1
      ;;
    *)
      echo "ERROR: unknown SYNC_DB_PASSWORD_ARCHIVE_MODE: $mode" >&2
      return 1
      ;;
  esac

  chmod 600 "$archive" 2>/dev/null || true
  rm -f "$plain"
  echo "$archive"
}

rotate_db_password_for_sync() {
  if [ "${SYNC_SKIP_DB_ROTATION:-0}" = "1" ]; then
    DB_ROTATION_LINE="DB password rotation: skipped (SYNC_SKIP_DB_ROTATION=1)"
    echo "$DB_ROTATION_LINE"
    return 0
  fi

  if [ ! -x "scripts/rotate-supabase-db-password.sh" ]; then
    echo "ERROR: scripts/rotate-supabase-db-password.sh is missing or not executable." >&2
    echo "Run: chmod +x scripts/rotate-supabase-db-password.sh" >&2
    return 1
  fi

  if [ -z "${SUPABASE_ACCESS_TOKEN:-}" ]; then
    echo "ERROR: SUPABASE_ACCESS_TOKEN is required for automatic DB password rotation." >&2
    echo "Set it from your Supabase account access token, or use SYNC_SKIP_DB_ROTATION=1 for an emergency code-only push." >&2
    return 1
  fi

  local password_file archive project_ref rotation_args
  password_file="$(mktemp /tmp/theseus-sync-db-password.XXXXXX)"
  chmod 600 "$password_file"
  SECRET_TMP_FILES+=("$password_file")
  generate_db_password > "$password_file"

  project_ref="$(infer_supabase_project_ref_for_sync)"
  if ! archive="$(write_db_password_recovery_archive "$password_file" "$project_ref")"; then
    echo "ERROR: DB password recovery archive setup failed." >&2
    echo "No Supabase, GitHub, Vercel, or local dotenv password rotation was attempted." >&2
    return 1
  fi
  echo "Encrypted DB password recovery archive: $archive"

  rotation_args=(--yes --password-file "$password_file")
  if [ "${SYNC_DB_ROTATE_REDEPLOY:-1}" = "0" ]; then
    rotation_args+=(--no-vercel-redeploy)
  fi
  if [ "${SYNC_CURRENTS_BACKEND_REFRESH_REQUIRED:-1}" = "1" ]; then
    rotation_args+=(--require-currents-backend-refresh)
  fi

  if [ "${SYNC_CURRENTS_BACKEND_REFRESH_REQUIRED:-1}" = "1" ] && \
     [ -z "${CURRENTS_BACKEND_REFRESH_CMD:-}" ]; then
    echo "ERROR: CURRENTS_BACKEND_REFRESH_CMD is required before automatic DB rotation." >&2
    echo "The public Currents API/scheduler is a database consumer outside Vercel/GitHub." >&2
    echo "Rotating without refreshing that service leaves it hammering Supabase with a stale password, which triggers the ECIRCUITBREAKER block currently breaking public publishing." >&2
    echo "Set CURRENTS_BACKEND_REFRESH_CMD to your deployment restart/update command, or use SYNC_CURRENTS_BACKEND_REFRESH_REQUIRED=0 only if you have manually refreshed that service." >&2
    return 1
  fi

  echo ""
  echo "Rotating Supabase DB password before GitHub push..."
  ./scripts/rotate-supabase-db-password.sh "${rotation_args[@]}"

  rm -f "$password_file"
  DB_ROTATION_LINE="DB password rotation: complete · recovery archive: $archive"
}

# Clean stale git lock files if no git process is actually running.
# These lock files are left behind when a git process crashes (common with
# GUI clients like GitButler, editors, or interrupted terminal commands) and
# block all subsequent git operations with misleading "another git process is
# running" errors.
if ! pgrep -x git >/dev/null 2>&1; then
  rm -f .git/index.lock .git/HEAD.lock .git/config.lock .git/packed-refs.lock 2>/dev/null || true
  find .git/refs -name "*.lock" -delete 2>/dev/null || true
fi

# `git branch --show-current` prints an empty string AND exits 0 on detached
# HEAD, so a plain `|| branch=main` fallback doesn't fire. Guard with -z too.
# Rolling release, latest-main, and Vercel are wired to `main` — we always push
# there, merging from your current branch when it isn't `main`.
branch=$(git branch --show-current 2>/dev/null || true)
[ -z "$branch" ] && branch=main
# If on GitButler's branch, switch to main
if [ "$branch" = "gitbutler/workspace" ]; then
  [ -f ".git/hooks/pre-commit" ] && grep -q GITBUTLER_MANAGED_HOOK ".git/hooks/pre-commit" 2>/dev/null && rm ".git/hooks/pre-commit"
  need_stash_pop=0
  if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    if git stash push -m "sync: before checkout main" 2>/dev/null; then
      need_stash_pop=1
    else
      git add -A
      git commit -m "Sync: Cursor edits"
      git fetch origin 2>/dev/null || true
      if git rev-parse --verify origin/main >/dev/null 2>&1; then
        git checkout -B main origin/main
        git merge gitbutler/workspace -m "Merge Cursor edits"
      else
        git checkout -B main
      fi
      rotate_db_password_for_sync
      git push origin main
      banner_success \
        "Pushed to origin/main" \
        "$DB_ROTATION_LINE" \
        "Repo: https://github.com/mrquintin/mqtheseuswork" \
        "(GitButler path — CI watch not performed.)"
      cleanup_secret_tmp_files
      trap - EXIT
      exit 0
    fi
  fi
  if ! git checkout main 2>/dev/null; then
    git fetch origin
    git checkout -B main origin/main
  fi
  [ "$need_stash_pop" = 1 ] && git stash pop
  branch=main
fi
# Check for changes:
#   1. Uncommitted working-tree changes (staged, unstaged, or untracked)
#   2. Local commits ahead of origin/<branch> (committed but not pushed)
# If BOTH are absent, the repo is already fully synced — prompt before doing
# anything so we don't burn CI minutes on an empty push.
# Ignore submodule drift when deciding if the working tree is "changed":
# the theseus-codex submodule is chronically marked modified (no .gitmodules
# + its own .git dir), which would otherwise make this script always push.
has_wt_changes=0
if ! git diff --quiet --ignore-submodules=all HEAD 2>/dev/null; then has_wt_changes=1; fi
if [ "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then has_wt_changes=1; fi

# Compare to origin/main — that's what this script publishes.
git fetch origin main 2>/dev/null || true
[ "$branch" != "main" ] && git fetch origin "$branch" 2>/dev/null || true

ahead_count=0
remote_exists=1
if git rev-parse --verify "origin/main" >/dev/null 2>&1; then
  ahead_count=$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo 0)
else
  remote_exists=0
fi

if [ "$has_wt_changes" = 0 ] && [ "$ahead_count" = 0 ] && [ "$remote_exists" = 1 ]; then
  last_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
  last_subj=$(git log -1 --format='%s' 2>/dev/null || echo "?")
  last_time=$(git log -1 --format='%cr' 2>/dev/null || echo "?")
  echo ""
  echo "Repo is already in sync with origin/main (working branch: $branch):"
  echo "  - No uncommitted changes in working tree"
  echo "  - No commits in HEAD that are not already in origin/main"
  echo "  - Last synced: $last_sha \"$last_subj\" ($last_time)"
  echo ""
  echo "If you expected pending work, verify with:   git status"
  echo "An in-progress edit pass may not have saved yet — wait a moment and retry."
  echo ""
  # Guard against non-interactive stdin (piped/CI). A blocking `read` would
  # hang forever; default to "no" if there's no TTY to prompt into.
  if [ ! -t 0 ]; then
    if [ "${SYNC_FORCE:-0}" != "1" ]; then
      banner_skipped \
        "Non-interactive shell and SYNC_FORCE is not set." \
        "Nothing pushed. Set SYNC_FORCE=1 to push anyway."
      exit 0
    fi
  else
    printf "Push anyway? (y/N) "
    read -r REPLY
    if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
      banner_skipped \
        "Already in sync with origin/main — nothing to do."
      exit 0
    fi
  fi
fi

echo ""
echo "Syncing to GitHub..."
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Ready-to-sync gate (Round 19b prompt 27).
#
# Runs every check from prompts 19–26 in one pass and emits a single
# pass/fail verdict. If the gate fails, the sync refuses; if it passes,
# the legacy per-check blocks below short-circuit because the gate has
# already run the equivalent commands.
#
# Flags:
#   --skip-ready-to-sync      bypass the gate entirely (loud warning + audit log)
#   --ready-to-sync-only      run the gate, do not push
#   --ready-to-sync-from N    resume the gate from step N (after a fix)
#   --ready-to-sync-skip N    skip step N of the gate (comma-separated for multi)
# ──────────────────────────────────────────────────────────────────────────────
SKIP_READY_TO_SYNC=0
READY_TO_SYNC_ONLY=0
READY_TO_SYNC_FROM=""
READY_TO_SYNC_SKIP=""
READY_TO_SYNC_RAN=0
for ((i=1; i<=$#; i++)); do
  arg="${!i}"
  case "$arg" in
    --skip-ready-to-sync) SKIP_READY_TO_SYNC=1 ;;
    --ready-to-sync-only) READY_TO_SYNC_ONLY=1 ;;
    --ready-to-sync-from)
      next=$((i + 1))
      READY_TO_SYNC_FROM="${!next:-}" ;;
    --ready-to-sync-from=*)
      READY_TO_SYNC_FROM="${arg#--ready-to-sync-from=}" ;;
    --ready-to-sync-skip)
      next=$((i + 1))
      READY_TO_SYNC_SKIP="${!next:-}" ;;
    --ready-to-sync-skip=*)
      READY_TO_SYNC_SKIP="${arg#--ready-to-sync-skip=}" ;;
  esac
done

ready_to_sync_log_bypass() {
  # Audit log for --skip-ready-to-sync. Persisted under docs/verification so
  # it surfaces in code review when frequent skips become a smell.
  local log_file ts
  log_file="docs/verification/ready_to_sync_skips.log"
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mkdir -p "$(dirname "$log_file")"
  printf '{"ts":"%s","event":"sync.ready_to_sync.skip","operator":"%s","branch":"%s","head":"%s","reason":"%s"}\n' \
    "$ts" \
    "${USER:-unknown}" \
    "$(git branch --show-current 2>/dev/null || echo unknown)" \
    "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
    "${SYNC_READY_TO_SYNC_SKIP_REASON:-unspecified}" \
    >> "$log_file" 2>/dev/null || true
  echo "${C_YELLOW}  Bypass recorded: $log_file${C_RESET}"
}

# ──────────────────────────────────────────────────────────────────────────────
# Ready-to-sync gate REMOVED from sync flow on 2026-05-16 per operator
# directive. The gate's home is `run_prompts.sh` (auto-runs after a clean
# prompt batch) and explicit manual invocation via
# `./scripts/ready-to-sync.sh` or `make ready-to-sync`. Sync's job is to
# sync; gating belongs upstream of code changes, not at push time.
#
# Backward compat for the flag surface: every --ready-to-sync-* flag is
# still accepted by the arg parser above so existing scripts / muscle
# memory don't error out, but only --ready-to-sync-only retains active
# behavior (delegates to the gate script and exits without pushing).
# The other flags become no-ops with a brief informational note.
# ──────────────────────────────────────────────────────────────────────────────
if [ "$SKIP_READY_TO_SYNC" = 1 ]; then
  echo "${C_YELLOW}note: --skip-ready-to-sync is now a no-op (gate is no longer wired${C_RESET}"
  echo "${C_YELLOW}      into sync). The gate lives in run_prompts.sh / ready-to-sync.sh.${C_RESET}"
  echo ""
fi

if [ -n "$READY_TO_SYNC_FROM" ] || [ -n "$READY_TO_SYNC_SKIP" ]; then
  echo "${C_YELLOW}note: --ready-to-sync-from / --ready-to-sync-skip are now no-ops in${C_RESET}"
  echo "${C_YELLOW}      sync (gate is no longer wired here). Use them directly with${C_RESET}"
  echo "${C_YELLOW}      ./scripts/ready-to-sync.sh if you want to invoke the gate.${C_RESET}"
  echo ""
fi

if [ "$READY_TO_SYNC_ONLY" = 1 ]; then
  # Compatibility path: delegate to the gate script + exit. This lets
  # `./scripts/sync-to-github.sh --ready-to-sync-only` keep working as
  # the "run the gate without pushing" entry point that prior docs
  # referenced.
  if [ -x scripts/ready-to-sync.sh ]; then
    echo "--ready-to-sync-only set; invoking gate without pushing."
    ./scripts/ready-to-sync.sh
    gate_rc=$?
    trap - EXIT
    exit "$gate_rc"
  else
    echo "${C_RED}--ready-to-sync-only set, but scripts/ready-to-sync.sh is missing.${C_RESET}"
    trap - EXIT
    exit 1
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pre-push gates REMOVED from sync on 2026-05-16 per operator directive.
#
# Previously this script ran (in order): migration linearity, bug-replay
# regression catalog, smoke harness. Each had its own --skip-* flag. The
# checks are all valuable — they just don't belong here. Gating belongs
# upstream of code changes (run_prompts.sh auto-runs the ready-to-sync
# gate after a clean prompt batch, and the operator can invoke
# ./scripts/ready-to-sync.sh manually at any time). Sync's job is to
# sync, period.
#
# Flag-surface compatibility: --skip-migration-check, --skip-regression,
# --skip-smoke, and --smoke are still accepted by the parser (and by the
# `for arg` loops below for backward compat) so muscle memory and
# automation don't error out. They become no-ops with a one-line note.
# To run the checks: invoke them directly.
#   - migrations: python3 scripts/check_migration_linearity.py
#   - bug-replay: python3 -m pytest tests/regression -q
#   - smoke:      ./scripts/smoke/run.sh
#   - all of the above + others: ./scripts/ready-to-sync.sh
# ──────────────────────────────────────────────────────────────────────────────
SKIP_MIGRATION_CHECK=0
SKIP_REGRESSION=0
SKIP_SMOKE=0
RUN_SMOKE_EXPLICIT=0
_legacy_flag_seen=0
for arg in "$@"; do
  case "$arg" in
    --skip-migration-check) SKIP_MIGRATION_CHECK=1; _legacy_flag_seen=1 ;;
    --skip-regression)      SKIP_REGRESSION=1; _legacy_flag_seen=1 ;;
    --skip-smoke)           SKIP_SMOKE=1; _legacy_flag_seen=1 ;;
    --smoke)                RUN_SMOKE_EXPLICIT=1; _legacy_flag_seen=1 ;;
  esac
done
if [ "$_legacy_flag_seen" = 1 ]; then
  echo "${C_YELLOW}note: pre-push gates (migration-check, regression, smoke) are no${C_RESET}"
  echo "${C_YELLOW}      longer wired into sync. The --skip-* and --smoke flags are${C_RESET}"
  echo "${C_YELLOW}      accepted for backward compat but are now no-ops. Run the${C_RESET}"
  echo "${C_YELLOW}      checks directly if you want them — see scripts/ready-to-sync.sh${C_RESET}"
  echo "${C_YELLOW}      or invoke each check standalone.${C_RESET}"
  echo ""
fi


# Show the user exactly what they're about to commit. Previously this
# script just ran `git add -A` + `git commit` and relied on the commit's
# stat line ("17 files changed …") to communicate what happened. That
# was easy to miss — and made it hard to tell, retrospectively, whether
# a given sync included the edits you expected. This preview lists every
# modified / added / deleted path, grouped by change type, before the
# commit fires.
if [ "$has_wt_changes" = 1 ]; then
  pending_list=$(git status --porcelain --ignore-submodules=all 2>/dev/null)
  if [ -n "$pending_list" ]; then
    pending_count=$(printf "%s\n" "$pending_list" | grep -c . || echo 0)
    echo "=== Pending changes ($pending_count files) ==="
    printf "%s\n" "$pending_list" | awk '{
      code=substr($0,1,2);
      path=substr($0,4);
      sym="?";
      if (code ~ /A/ || code ~ /\?\?/) sym="+";
      else if (code ~ /D/) sym="-";
      else if (code ~ /M/) sym="~";
      else if (code ~ /R/) sym=">";
      printf "  %s %s\n", sym, path;
    }' | head -40
    # If there are more than 40, say so rather than silently truncating.
    if [ "$pending_count" -gt 40 ]; then
      echo "  … and $((pending_count - 40)) more"
    fi
    echo "  Legend: +  added    ~  modified    -  deleted    >  renamed"
    echo ""
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# Deletion guardrail — refuse to silently push large deletions or deletions of
# load-bearing paths. This is the failure mode that lost the currents/live-news
# feature once: a previous run deleted theseus-public/src/app/currents/ and
# current_events_api/*.py and the next sync faithfully pushed the deletion to
# origin/main, taking the deployed site down with it. The bytecode caches in
# __pycache__/ are gitignored and survived on disk, so the loss was invisible
# until someone tried to use the feature.
#
# Override with SYNC_FORCE_DELETE=1 when the deletions are intentional.
# ──────────────────────────────────────────────────────────────────────────────
DELETE_HARD_LIMIT=${SYNC_DELETE_HARD_LIMIT:-25}
LOAD_BEARING_PATHS=(
  "theseus-public/src/app/currents/"
  "theseus-public/src/lib/currentsApi"
  "theseus-public/src/components/CurrentsNavPulse"
  "current_events_api/current_events_api/"
  "noosphere/noosphere/extractors/"
  "noosphere/noosphere/codex_bridge.py"
  "dialectic/dialectic/recording_modal.py"
  "dialectic/dialectic/recording_pipeline.py"
  "dialectic/dialectic/auto_trim.py"
  "dialectic/dialectic/auto_title.py"
  "dialectic/dialectic/codex_upload.py"
  "scripts/sync-to-github.sh"
  ".vscode/tasks.json"
)

# Only create a new commit if the working tree actually has changes.
# Otherwise just push whatever commits are ahead of origin.
if [ "$has_wt_changes" = 1 ]; then
  # Stage everything first so deleted-tracked-files show up as 'D' in --cached.
  git add -A

  # Count and list staged deletions.
  staged_deletions=$(git diff --cached --name-only --diff-filter=D 2>/dev/null || true)
  staged_delete_count=0
  if [ -n "$staged_deletions" ]; then
    staged_delete_count=$(printf '%s\n' "$staged_deletions" | grep -c .)
  fi

  # Match staged deletions against load-bearing paths.
  load_bearing_hits=""
  if [ -n "$staged_deletions" ]; then
    for lb in "${LOAD_BEARING_PATHS[@]}"; do
      hit=$(printf '%s\n' "$staged_deletions" | grep -F -- "$lb" || true)
      if [ -n "$hit" ]; then
        load_bearing_hits="${load_bearing_hits}${hit}"$'\n'
      fi
    done
  fi

  # Refuse to commit if load-bearing paths are being deleted without override.
  if [ -n "$load_bearing_hits" ] && [ "${SYNC_FORCE_DELETE:-0}" != "1" ]; then
    echo ""
    echo "${C_RED}=== REFUSING TO SYNC: load-bearing files staged for deletion ===${C_RESET}"
    printf '%s' "$load_bearing_hits" | sed 's/^/  -  /'
    echo ""
    echo "  These paths are listed in LOAD_BEARING_PATHS in this script because"
    echo "  losing them silently has broken the deployed site at least once."
    echo "  Unstaging the deletion (recommended):"
    echo "      git restore --staged <path> && git restore <path>"
    echo "  Or, if the deletion is intentional, override:"
    echo "      SYNC_FORCE_DELETE=1 ./scripts/sync-to-github.sh"
    banner_failed \
      "Deletion of load-bearing files blocked." \
      "Set SYNC_FORCE_DELETE=1 to override, or restore the files first."
    trap - EXIT
    exit 2
  fi

  # Soft confirmation when staged deletions exceed the hard limit.
  if [ "$staged_delete_count" -gt "$DELETE_HARD_LIMIT" ] && [ "${SYNC_FORCE_DELETE:-0}" != "1" ]; then
    echo ""
    echo "${C_YELLOW}=== WARNING: $staged_delete_count files staged for deletion (limit $DELETE_HARD_LIMIT) ===${C_RESET}"
    printf '%s\n' "$staged_deletions" | head -20 | sed 's/^/  -  /'
    if [ "$staged_delete_count" -gt 20 ]; then
      echo "  …and $((staged_delete_count - 20)) more"
    fi
    echo ""
    if [ -t 0 ]; then
      printf "Proceed with these deletions? (y/N) "
      read -r REPLY
      if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
        echo "Aborting. Run 'git restore --staged .' to unstage everything."
        banner_skipped "Bulk deletion declined; nothing pushed."
        trap - EXIT
        exit 0
      fi
    else
      banner_skipped \
        "Non-interactive shell with $staged_delete_count deletions exceeding $DELETE_HARD_LIMIT." \
        "Set SYNC_FORCE_DELETE=1 to bypass this check."
      trap - EXIT
      exit 0
    fi
  fi

  if git status --porcelain | grep -q '^[MADRCU?]'; then
    git commit -m "Sync: latest changes"
  fi
else
  echo "No working-tree changes. Pushing $ahead_count existing commit(s) not in origin/main yet."
fi

if [ "$has_wt_changes" = 0 ] && [ "$ahead_count" = 0 ] && [ "$remote_exists" = 1 ] && \
   [ "${SYNC_ROTATE_ON_EMPTY_PUSH:-0}" != "1" ]; then
  DB_ROTATION_LINE="DB password rotation: skipped (already in sync; set SYNC_ROTATE_ON_EMPTY_PUSH=1 to rotate anyway)"
  echo "$DB_ROTATION_LINE"
else
  rotate_db_password_for_sync
fi

# Merge $work_branch into `main` when needed, then push `main`.
work_branch=$branch
if [ "$work_branch" != "main" ]; then
  echo "Merging $work_branch into main and pushing to origin/main..."
  git fetch origin
  if git rev-parse --verify "refs/remotes/origin/main" >/dev/null 2>&1; then
    git checkout -B main "origin/main"
  elif git show-ref -q --verify refs/heads/main; then
    git checkout main
  else
    git checkout -B main "$work_branch"
  fi
  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "$work_branch")" ]; then
    merge_msg="Sync: merge $work_branch (sync-to-github.sh)"
    if git merge-base "$work_branch" HEAD >/dev/null 2>&1; then
      if ! git merge "$work_branch" -m "$merge_msg"; then
        echo "Merge into main failed (conflict?). Fix on branch main, then run the script again." >&2
        exit 1
      fi
    else
      echo "Note: $work_branch and main share no common history — using --allow-unrelated-histories" >&2
      if ! git merge --allow-unrelated-histories "$work_branch" -m "Sync: merge $work_branch (unrelated histories)"; then
        echo "Merge into main failed. Resolve on branch main, or rebase $work_branch onto main, then run again." >&2
        exit 1
      fi
    fi
  fi
  branch=main
fi
git push origin main
# CI watches the commit on main (read before we checkout a feature branch again).
pushed_sha=$(git rev-parse main 2>/dev/null || git rev-parse HEAD)
[ -n "$work_branch" ] && [ "$work_branch" != "main" ] && git checkout "$work_branch" || true
branch=main

echo ""
echo "Pushed to origin/main"
echo "Repo: https://github.com/mrquintin/mqtheseuswork"

# ──────────────────────────────────────────────────────────────────────────────
# Wait for the Rolling Release workflow to rebuild the installers and report
# which ones succeeded. Set SYNC_SKIP_WATCH=1 to push and exit immediately
# without watching CI (useful for small doc edits where you don't care about
# the installer rebuild).
# ──────────────────────────────────────────────────────────────────────────────
if [ "${SYNC_SKIP_WATCH:-0}" = "1" ]; then
  # SYNC_SKIP_WATCH=1 skips both the Rolling Release watch AND the all-
  # workflow audit. The banner explicitly degrades to "PARTIAL" rather
  # than "COMPLETE" because we cannot truthfully claim CI is healthy
  # without observing it. Operators who just want to push and walk away
  # should be using the "submit and check tomorrow" workflow, not
  # SYNC_SKIP_WATCH masquerading as success.
  banner_partial \
    "Pushed to origin/$branch." \
    "$DB_ROTATION_LINE" \
    "CI watch skipped (SYNC_SKIP_WATCH=1) — CI health not verified." \
    "Build status: https://github.com/mrquintin/mqtheseuswork/actions"
  cleanup_secret_tmp_files
  trap - EXIT
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  # Same reasoning as SYNC_SKIP_WATCH: if we cannot see CI, we cannot
  # report it. PARTIAL is the honest classification.
  banner_partial \
    "Pushed to origin/$branch." \
    "$DB_ROTATION_LINE" \
    "gh CLI not installed — CI health unverified." \
    "Install gh and re-run for accurate CI reporting." \
    "Track progress: https://github.com/mrquintin/mqtheseuswork/actions"
  cleanup_secret_tmp_files
  trap - EXIT
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  banner_partial \
    "Pushed to origin/$branch." \
    "$DB_ROTATION_LINE" \
    "gh CLI not authenticated (run 'gh auth login') — CI health unverified." \
    "Track progress: https://github.com/mrquintin/mqtheseuswork/actions"
  cleanup_secret_tmp_files
  trap - EXIT
  exit 0
fi

echo ""
echo "Waiting for Rolling Release workflow to start on commit ${pushed_sha:0:7}..."
echo "(Press Ctrl+C to stop watching — the build will continue on GitHub.)"
echo ""

# Give GitHub a few seconds to register the push event and queue the workflow.
# Poll for up to ~30s looking for a run whose headSha matches our pushed commit.
run_id=""
for _ in 1 2 3 4 5 6; do
  sleep 5
  run_id=$(gh run list --workflow=rolling-release.yml --limit 5 \
    --json databaseId,headSha \
    --jq ".[] | select(.headSha == \"$pushed_sha\") | .databaseId" 2>/dev/null | head -n1)
  [ -n "$run_id" ] && break
  echo "  (waiting for workflow to start...)"
done

if [ -z "$run_id" ]; then
  # Fallback: use the most recent run even if we can't match it by SHA.
  run_id=$(gh run list --workflow=rolling-release.yml --limit 1 \
    --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo "")
fi

if [ -z "$run_id" ]; then
  banner_partial \
    "Pushed to origin/$branch, but couldn't find a Rolling Release run to watch." \
    "Track progress: https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

echo "Watching run: https://github.com/mrquintin/mqtheseuswork/actions/runs/$run_id"
echo "Installer builds typically take 10–20 minutes."
echo ""

# `gh run watch` streams job status and returns when the run completes.
# It returns 0 on success, non-zero if the run failed. We don't want the
# script to exit non-zero on a partial failure (since the publish step
# handles partial failures gracefully and still produces a release).
gh run watch "$run_id" --interval 15 --exit-status || true

echo ""
echo "=== Installer build results ==="

# List what's currently in the latest-main release
# Theseus Codex intentionally excluded — it's a Next.js web app, not an
# installer. Users reach it via the hosted URL in README.md.
expected="Dialectic.dmg Dialectic-Setup.exe noosphere-macos.tar.gz Noosphere-Setup.exe"
assets=$(gh release view latest-main --json assets --jq '.assets[].name' 2>/dev/null || true)

ok_count=0
missing_count=0
total_expected=0
# Note: `for` word-splits, which is fine here because expected names are
# space-free. Count with $(...) | wc -w to avoid a subshell for the total.
for _ in $expected; do total_expected=$((total_expected + 1)); done

if [ -z "$assets" ]; then
  echo "  No release found yet. Check:"
  echo "    https://github.com/mrquintin/mqtheseuswork/releases"
  missing_count=$total_expected
else
  for exp in $expected; do
    # -F: fixed-string match (so '.' in filenames isn't a regex metachar).
    # -x: match whole line.  -q: quiet.
    if echo "$assets" | grep -Fxq "$exp"; then
      echo "  [OK]      $exp"
      ok_count=$((ok_count + 1))
    else
      echo "  [MISSING] $exp"
      missing_count=$((missing_count + 1))
    fi
  done
  # Surface any extra assets (arm64/x64 DMGs, etc.). Iterate line-by-line so
  # asset names containing spaces don't get word-split by the shell.
  while IFS= read -r a; do
    [ -z "$a" ] && continue
    case " $expected " in
      *" $a "*) : ;;
      *) echo "  [EXTRA]   $a" ;;
    esac
  done <<EOF
$assets
EOF
fi

echo ""
echo "Release page: https://github.com/mrquintin/mqtheseuswork/releases/tag/latest-main"

# ──────────────────────────────────────────────────────────────────────────────
# Verify the Theseus Codex website link in README.md still resolves. The README
# may point either at the custom production domain or Vercel's production alias.
# If that hardcoded public URL drifts from reality, a quick HEAD request catches
# it before the sync is reported as complete.
# ──────────────────────────────────────────────────────────────────────────────
codex_url=""
codex_status="unchecked"
codex_db_status="unchecked"
if [ -f README.md ] && command -v curl >/dev/null 2>&1; then
  # Extract the first public Codex origin from the README. Match only the
  # scheme + host so markdown syntax cannot get folded into the URL.
  codex_url=$(grep -oE 'https://(([A-Za-z0-9.-]+\.vercel\.app)|(www\.)?theseuscodex\.com)' README.md 2>/dev/null | head -n1 || true)
  if [ -n "$codex_url" ]; then
    http_status=$(curl -sS -o /dev/null -w '%{http_code}' -L --max-time 15 "$codex_url" 2>/dev/null || echo "000")
    if [ "$http_status" = "200" ]; then
      codex_status="200 ($codex_url)"
    else
      codex_status="BROKEN ($http_status for $codex_url)"
    fi

    db_health_url="${codex_url%/}/api/health/db"
    db_health_status=$(curl -sS -o /dev/null -w '%{http_code}' -L --max-time 15 "$db_health_url" 2>/dev/null || echo "000")
    if [ "$db_health_status" = "200" ]; then
      codex_db_status="DB 200 ($db_health_url)"
    else
      codex_db_status="DB BROKEN ($db_health_status for $db_health_url)"
    fi
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# Also check whether Vercel's *most recent* deployment for our pushed commit
# actually succeeded. The HTTP 200 check above only proves that SOME deploy
# is live on the production alias — which is usually the last successful
# one. If Vercel just tried to build the commit we pushed and failed (e.g.
# type error, duplicate route), the alias keeps pointing at the old deploy,
# the URL still returns 200, and the user has no idea their new code isn't
# live. This extra check surfaces that silently-failing case explicitly.
# ──────────────────────────────────────────────────────────────────────────────
vercel_deploy_status="unchecked"
if command -v gh >/dev/null 2>&1 && [ -n "${pushed_sha:-}" ]; then
  vercel_deploy_id=$(gh api "repos/mrquintin/mqtheseuswork/deployments?sha=${pushed_sha}&environment=Production&per_page=1" --jq '.[0].id' 2>/dev/null || true)
  if [ -n "$vercel_deploy_id" ] && [ "$vercel_deploy_id" != "null" ]; then
    vercel_state=$(gh api "repos/mrquintin/mqtheseuswork/deployments/${vercel_deploy_id}/statuses" --jq '.[0].state' 2>/dev/null || true)
    case "$vercel_state" in
      success)
        vercel_deploy_status="success"
        ;;
      failure|error)
        vercel_deploy_status="FAILED — run 'gh api repos/mrquintin/mqtheseuswork/deployments/${vercel_deploy_id}/statuses' for details"
        ;;
      in_progress|queued|pending|"")
        vercel_deploy_status="in-progress (check dashboard in a minute)"
        ;;
      *)
        vercel_deploy_status="$vercel_state"
        ;;
    esac
  else
    vercel_deploy_status="no deployment found yet"
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# All-workflow audit. Rolling Release was already watched above, but every
# OTHER workflow that fires on this push (Integrity, Type Contracts, smoke,
# Accessibility, Dead-code survey, Round-3 invariants, …) ran in parallel
# and would otherwise complete invisibly. The audit is what makes the
# banner an honest report of CI health rather than a single-workflow
# proxy that the operator has to manually cross-check afterwards.
# ──────────────────────────────────────────────────────────────────────────────
if [ "${SYNC_SKIP_WORKFLOW_AUDIT:-0}" = "1" ]; then
  echo ""
  echo "${C_YELLOW}note: workflow audit skipped (SYNC_SKIP_WORKFLOW_AUDIT=1).${C_RESET}"
  echo "${C_YELLOW}      Banner will not reflect other CI workflows' status.${C_RESET}"
  WORKFLOW_AUDIT_STATUS="unchecked"
else
  audit_all_workflows "${pushed_sha:-}"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Final completion banner. Color and wording reflect what actually succeeded
# across every observable surface:
#   - All installers present, Codex 200, Vercel success, every workflow green
#     → green SYNC COMPLETE
#   - Any workflow failed, OR Vercel/Codex broken, OR installers missing
#     → yellow SYNC PARTIAL
#   - Zero installers AND no other signal of life → red SYNC FAILED
# ──────────────────────────────────────────────────────────────────────────────
summary_line="Installers: ${ok_count}/${total_expected} OK"
[ "$missing_count" -gt 0 ] && summary_line="${summary_line} · ${missing_count} missing"
release_line="Release: https://github.com/mrquintin/mqtheseuswork/releases/tag/latest-main"
push_line="Pushed commit ${pushed_sha:0:7} to origin/$branch"
codex_line="Codex URL: $codex_status · $codex_db_status"
vercel_line="Vercel deploy: $vercel_deploy_status"

# Build the Workflows line. Phrasing makes the failure count the loudest
# part of the string so it cannot be missed in a glance at the banner.
case "$WORKFLOW_AUDIT_STATUS" in
  success)
    workflow_line="Workflows: ${WORKFLOW_AUDIT_SUCCESS}/${WORKFLOW_AUDIT_TOTAL} green"
    ;;
  failed)
    workflow_line="Workflows: ${WORKFLOW_AUDIT_FAILURE} FAILED of ${WORKFLOW_AUDIT_TOTAL} (see list above for URLs)"
    ;;
  inflight)
    workflow_line="Workflows: ${WORKFLOW_AUDIT_SUCCESS}/${WORKFLOW_AUDIT_TOTAL} green, ${WORKFLOW_AUDIT_INFLIGHT} still in flight (audit timed out)"
    ;;
  unchecked|*)
    workflow_line="Workflows: not audited"
    ;;
esac

codex_broken=0
case "$codex_status" in BROKEN*) codex_broken=1 ;; esac
case "$codex_db_status" in "DB BROKEN"*) codex_broken=1 ;; esac

vercel_broken=0
case "$vercel_deploy_status" in FAILED*) vercel_broken=1 ;; esac

workflows_broken=0
[ "$WORKFLOW_AUDIT_STATUS" = "failed" ] && workflows_broken=1

if [ "$ok_count" -eq "$total_expected" ] \
   && [ "$codex_broken" = 0 ] \
   && [ "$vercel_broken" = 0 ] \
   && [ "$workflows_broken" = 0 ] \
   && [ "$WORKFLOW_AUDIT_STATUS" = "success" ]; then
  banner_success "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line"
elif [ "$ok_count" -eq 0 ]; then
  banner_failed  "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line" \
    "All installers are missing — check the CI logs."
elif [ "$workflows_broken" = 1 ] && [ "$vercel_broken" = 0 ] && [ "$codex_broken" = 0 ]; then
  banner_partial "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line" \
    "${WORKFLOW_AUDIT_FAILURE} CI workflow(s) failed even though Vercel and Rolling Release are green. Click the URLs printed above the banner to triage."
elif [ "$vercel_broken" = 1 ]; then
  banner_partial "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line" \
    "Vercel couldn't build this commit. The live site is STALE — still showing the previous successful deploy. Check the Vercel dashboard and fix the build error."
elif [ "$codex_broken" = 1 ]; then
  banner_partial "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line" \
    "The Codex public URL or database health check failed. Verify Vercel runtime logs and the production DATABASE_URL before calling the sync complete."
else
  banner_partial "$push_line" "$DB_ROTATION_LINE" "$summary_line" "$release_line" "$codex_line" "$vercel_line" "$workflow_line"
fi

# Success path — override the default-failure EXIT trap so it doesn't fire.
cleanup_secret_tmp_files
trap - EXIT
exit 0
