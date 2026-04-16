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
# Check for changes
has_changes=0
if ! git diff --quiet HEAD 2>/dev/null; then has_changes=1; fi
if [ "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then has_changes=1; fi
if [ "$has_changes" = 0 ]; then
  printf "No changes detected. Push anyway? (y/N) "
  read -r REPLY
  if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
    echo "Skipped."
    exit 0
  fi
fi
echo ""
echo "Syncing to GitHub..."
echo ""
git add -A
if git status --porcelain | grep -q '^[MADRCU?]'; then
  git commit -m "Sync: latest changes"
else
  echo "Nothing to commit."
fi
git push origin "$branch"
echo ""
echo "Pushed to origin/$branch"
echo "Repo: https://github.com/mrquintin/mqtheseuswork"
