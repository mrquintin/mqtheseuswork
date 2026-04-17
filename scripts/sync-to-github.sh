#!/bin/bash
set -e
cd "$(git rev-parse --show-toplevel)"

# Clean stale git lock files if no git process is actually running.
# These lock files are left behind when a git process crashes (common with
# GUI clients like GitButler, editors, or interrupted terminal commands) and
# block all subsequent git operations with misleading "another git process is
# running" errors.
if ! pgrep -x git >/dev/null 2>&1; then
  rm -f .git/index.lock .git/HEAD.lock .git/config.lock .git/packed-refs.lock 2>/dev/null || true
  find .git/refs -name "*.lock" -delete 2>/dev/null || true
fi

branch=$(git branch --show-current 2>/dev/null) || branch=main
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
      echo "Pushed to origin/main"
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
if git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
  ahead_count=$(git rev-list --count "origin/$branch..HEAD" 2>/dev/null || echo 0)
fi

if [ "$has_wt_changes" = 0 ] && [ "$ahead_count" = 0 ]; then
  echo ""
  echo "Repo is already in sync with origin/$branch:"
  echo "  - No uncommitted changes in working tree"
  echo "  - No local commits ahead of origin/$branch"
  echo ""
  printf "Push anyway? (y/N) "
  read -r REPLY
  if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
    echo "Skipped. (Nothing to sync.)"
    exit 0
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
  echo ""
  echo "Skipping CI watch (SYNC_SKIP_WATCH=1). Build status:"
  echo "  https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo ""
  echo "gh CLI not installed; skipping installer build watch."
  echo "Track progress at:"
  echo "  https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "gh CLI not authenticated (run 'gh auth login'); skipping installer watch."
  echo "Track progress at:"
  echo "  https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
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
  echo "Could not find a Rolling Release run to watch."
  echo "Track progress at:"
  echo "  https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml"
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
expected="Dialectic.dmg Dialectic-Setup.exe noosphere-macos.tar.gz Noosphere-Setup.exe Theseus-Founder-Portal.dmg Theseus-Founder-Portal-Setup.exe"
assets=$(gh release view latest-main --json assets --jq '.assets[].name' 2>/dev/null || true)

if [ -z "$assets" ]; then
  echo "  No release found yet. Check:"
  echo "    https://github.com/mrquintin/mqtheseuswork/releases"
else
  for exp in $expected; do
    if echo "$assets" | grep -qx "$exp"; then
      echo "  [OK]     $exp"
    else
      echo "  [MISSING] $exp"
    fi
  done
  # Surface any extra assets (arm64/x64 DMGs, etc.)
  for a in $assets; do
    case " $expected " in
      *" $a "*) : ;;
      *) echo "  [EXTRA]  $a" ;;
    esac
  done
fi

echo ""
echo "Release page: https://github.com/mrquintin/mqtheseuswork/releases/tag/latest-main"
