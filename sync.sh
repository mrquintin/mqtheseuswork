#!/bin/bash
# ============================================================
# Thin wrapper around scripts/sync-to-github.sh.
#
# `./sync.sh` is the canonical, name-stable entry point for pushing
# commits to GitHub. All real logic — credential-rotation, deletion
# guardrails, Vercel/CI watch, completion banners — lives in
# `scripts/sync-to-github.sh`, which is also what `make sync` and the
# VS Code "Sync to GitHub" task invoke. This wrapper exists so that
#
#   - existing muscle memory / docs / cron jobs that say `./sync.sh`
#     keep working, and
#   - there is exactly ONE behavior regardless of which entry point
#     the operator picks.
#
# Two things this wrapper still owns (not delegated):
#
#   1. THESEUS_RUNNER_BRANCH_MODE=1 short-circuit. The per-prompt
#      runner pushes its own branches. If a cron'd ./sync.sh fires
#      while the runner is mid-flight, the racing pushes corrupt the
#      runner's branch lineage. This guard is intentionally checked
#      BEFORE the wrapper hands off, so even if the comprehensive
#      script learns its own branch-mode logic later this layer stays
#      cheap and explicit.
#
#   2. Working directory pin. Cron starts in $HOME, not the repo, so
#      the comprehensive script's `cd "$(git rev-parse --show-toplevel)"`
#      would fail. The wrapper cd's to its own directory (the repo
#      root, since this file lives there) before exec'ing.
#
# Cron note: the comprehensive script ROTATES the Supabase DB password
# on every push and requires SUPABASE_ACCESS_TOKEN. If you cron this
# wrapper, either export that token in the crontab line, or set
# SYNC_SKIP_DB_ROTATION=1 to opt out:
#
#   */30 * * * * SYNC_SKIP_DB_ROTATION=1 ~/Desktop/Theseus/sync.sh
# ============================================================

set -uo pipefail

# Resolve script directory so we work regardless of cwd. macOS ships BSD
# readlink which lacks -f; this portable form follows symlinks one level
# and is enough for the way this script gets called (direct path, cron).
SCRIPT_DIR="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

if [ "${THESEUS_RUNNER_BRANCH_MODE:-0}" = "1" ]; then
  echo "sync.sh: THESEUS_RUNNER_BRANCH_MODE=1 — runner owns push, skipping."
  exit 0
fi

exec "$SCRIPT_DIR/scripts/sync-to-github.sh" "$@"
