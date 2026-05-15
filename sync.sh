#!/bin/bash
# ============================================================
# Auto-sync Theseus to GitHub
# Run manually: ./sync.sh
# Or schedule with cron: crontab -e → */30 * * * * ~/Desktop/Theseus/sync.sh
# (syncs every 30 minutes)
#
# This script now honours two safety layers:
#   1. If the runner is in --branch-mode (THESEUS_RUNNER_BRANCH_MODE=1)
#      it skips entirely — the runner owns the push for those branches.
#   2. Final-defence credential regex over staged content. Refuses to
#      push if anything credential-shaped is staged, redundant with
#      .gitignore and scripts/hooks/pre-commit.sh but worth keeping
#      because a cron'd script runs unattended.
# ============================================================

set -uo pipefail

cd ~/Desktop/Theseus

# Layer 1 — the branch-mode runner owns its own pushes.
if [ "${THESEUS_RUNNER_BRANCH_MODE:-0}" = "1" ]; then
  echo "sync.sh: THESEUS_RUNNER_BRANCH_MODE=1 — runner owns push, skipping."
  exit 0
fi

# Check if there are changes.
if [ -z "$(git status --porcelain)" ]; then
    echo "No changes to sync."
    exit 0
fi

# Run the pre-commit hook explicitly. The hook itself is wired to
# .git/hooks/pre-commit via scripts/hooks/install.sh, so `git commit`
# below will trigger it — but invoking it up front lets us refuse
# before staging the tree at all.
if [ -x scripts/hooks/pre-commit.sh ]; then
    # Stage first so the hook sees what we'd actually commit.
    git add -A
    if ! scripts/hooks/pre-commit.sh; then
        echo "sync.sh: pre-commit gate refused. Not committing." >&2
        echo "sync.sh: fix the issue and re-run, or bypass once with THESEUS_SKIP_PRECOMMIT=1." >&2
        exit 1
    fi
else
    git add -A
fi

# Layer 2 — credential regex sweep over the staged diff. Independent
# of the pre-commit hook so that even if the hook is bypassed the
# auto-sync path still refuses to push the secret.
CRED_REGEX='sk-ant-api[0-9]{2}-[A-Za-z0-9_\-]{20,}|sk_live_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
if git diff --cached --no-color | grep -E "$CRED_REGEX" >/dev/null 2>&1; then
    echo "sync.sh: credential-shaped value in staged diff. REFUSING TO PUSH." >&2
    echo "sync.sh: rotate the value, remove from file, then re-run." >&2
    # Unstage so the operator does not accidentally re-run and commit anyway.
    git reset >/dev/null 2>&1
    exit 1
fi

# Stage, commit, push.
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
git commit -m "Auto-sync: ${TIMESTAMP}"
git push origin main

echo "Synced to GitHub at ${TIMESTAMP}"
