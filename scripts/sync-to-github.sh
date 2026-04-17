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

# If the script dies unexpectedly (set -e tripped by an unhandled error),
# show a clear failure banner instead of an ambiguous silent exit.
trap 'rc=$?; if [ $rc -ne 0 ]; then banner_failed "Script exited with code $rc" "Scroll up for the actual error."; fi' EXIT

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
      git push origin main
      banner_success \
        "Pushed to origin/main" \
        "Repo: https://github.com/mrquintin/mqtheseuswork" \
        "(GitButler path — CI watch not performed.)"
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

# Refresh remote refs so "ahead of origin" is accurate. Quiet on offline/no-net.
git fetch origin "$branch" 2>/dev/null || true

ahead_count=0
remote_exists=1
if git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
  ahead_count=$(git rev-list --count "origin/$branch..HEAD" 2>/dev/null || echo 0)
else
  # Branch doesn't exist on origin yet — everything local needs to be pushed.
  # Treat as "ahead" so we don't falsely report "already in sync".
  remote_exists=0
fi

if [ "$has_wt_changes" = 0 ] && [ "$ahead_count" = 0 ] && [ "$remote_exists" = 1 ]; then
  echo ""
  echo "Repo is already in sync with origin/$branch:"
  echo "  - No uncommitted changes in working tree"
  echo "  - No local commits ahead of origin/$branch"
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
        "Already in sync with origin/$branch — nothing to do."
      exit 0
    fi
  fi
fi

echo ""
echo "Syncing to GitHub..."
echo ""

# Only create a new commit if the working tree actually has changes.
# Otherwise just push whatever commits are ahead of origin.
if [ "$has_wt_changes" = 1 ]; then
  git add -A
  if git status --porcelain | grep -q '^[MADRCU?]'; then
    git commit -m "Sync: latest changes"
  fi
else
  echo "No working-tree changes. Pushing $ahead_count existing commit(s) ahead of origin/$branch."
fi

git push origin "$branch"
echo ""
echo "Pushed to origin/$branch"
echo "Repo: https://github.com/mrquintin/mqtheseuswork"

# ──────────────────────────────────────────────────────────────────────────────
# Wait for the Rolling Release workflow to rebuild the installers and report
# which ones succeeded. Set SYNC_SKIP_WATCH=1 to push and exit immediately
# without watching CI (useful for small doc edits where you don't care about
# the installer rebuild).
# ──────────────────────────────────────────────────────────────────────────────
if [ "${SYNC_SKIP_WATCH:-0}" = "1" ]; then
  banner_success \
    "Pushed to origin/$branch." \
    "CI watch skipped (SYNC_SKIP_WATCH=1)." \
    "Build status: https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  banner_success \
    "Pushed to origin/$branch." \
    "gh CLI not installed — can't watch installer build." \
    "Track progress: https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  banner_success \
    "Pushed to origin/$branch." \
    "gh CLI not authenticated (run 'gh auth login') — can't watch build." \
    "Track progress: https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

# Record the pushed commit SHA so we can find the workflow run triggered by it
pushed_sha=$(git rev-parse HEAD)
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
# Final completion banner. Color and wording reflect what actually succeeded:
#   - All installers present   → green SYNC COMPLETE
#   - Some installers missing  → yellow SYNC PARTIAL
#   - Zero installers present  → red SYNC FAILED (code pushed, builds broken)
# ──────────────────────────────────────────────────────────────────────────────
summary_line="Installers: ${ok_count}/${total_expected} OK"
[ "$missing_count" -gt 0 ] && summary_line="${summary_line} · ${missing_count} missing"
release_line="Release: https://github.com/mrquintin/mqtheseuswork/releases/tag/latest-main"
push_line="Pushed commit ${pushed_sha:0:7} to origin/$branch"

if [ "$ok_count" -eq "$total_expected" ]; then
  banner_success "$push_line" "$summary_line" "$release_line"
elif [ "$ok_count" -eq 0 ]; then
  banner_failed  "$push_line" "$summary_line" "$release_line" \
    "All installers are missing — check the CI logs."
else
  banner_partial "$push_line" "$summary_line" "$release_line"
fi

# Success path — override the default-failure EXIT trap so it doesn't fire.
trap - EXIT
exit 0
