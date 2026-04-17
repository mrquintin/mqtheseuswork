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
