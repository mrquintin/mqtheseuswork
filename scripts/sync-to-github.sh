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
# Verify the Theseus Codex website link in README.md still resolves. The URL
# in the README is Vercel's stable production alias and auto-repoints to the
# latest deploy — but if someone ever renames the Vercel project or adds a
# custom domain, the hardcoded README string will drift from reality. A quick
# HEAD request here catches that.
# ──────────────────────────────────────────────────────────────────────────────
codex_url=""
codex_status="unchecked"
if [ -f README.md ] && command -v curl >/dev/null 2>&1; then
  # Extract the first *.vercel.app origin from the README. We match only
  # the scheme + host and stop there, so markdown-link syntax like
  # `[https://foo.vercel.app](https://foo.vercel.app)` doesn't cause us to
  # capture `https://foo.vercel.app](https://foo.vercel.app` as a single
  # "URL" (as happened before this regex was tightened — exit code 000).
  # A path after the host isn't needed for a health check.
  codex_url=$(grep -oE 'https://[A-Za-z0-9.-]+\.vercel\.app' README.md 2>/dev/null | head -n1 || true)
  if [ -n "$codex_url" ]; then
    http_status=$(curl -sS -o /dev/null -w '%{http_code}' -L --max-time 15 "$codex_url" 2>/dev/null || echo "000")
    if [ "$http_status" = "200" ]; then
      codex_status="200 ($codex_url)"
    else
      codex_status="BROKEN ($http_status for $codex_url)"
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
# Final completion banner. Color and wording reflect what actually succeeded:
#   - All installers present   → green SYNC COMPLETE
#   - Some installers missing  → yellow SYNC PARTIAL
#   - Zero installers present  → red SYNC FAILED (code pushed, builds broken)
# README link verification adds an extra line so stale URLs are caught early.
# ──────────────────────────────────────────────────────────────────────────────
summary_line="Installers: ${ok_count}/${total_expected} OK"
[ "$missing_count" -gt 0 ] && summary_line="${summary_line} · ${missing_count} missing"
release_line="Release: https://github.com/mrquintin/mqtheseuswork/releases/tag/latest-main"
push_line="Pushed commit ${pushed_sha:0:7} to origin/$branch"
codex_line="Codex URL: $codex_status"
vercel_line="Vercel deploy: $vercel_deploy_status"

codex_broken=0
case "$codex_status" in BROKEN*) codex_broken=1 ;; esac

vercel_broken=0
case "$vercel_deploy_status" in FAILED*) vercel_broken=1 ;; esac

if [ "$ok_count" -eq "$total_expected" ] && [ "$codex_broken" = 0 ] && [ "$vercel_broken" = 0 ]; then
  banner_success "$push_line" "$summary_line" "$release_line" "$codex_line" "$vercel_line"
elif [ "$ok_count" -eq 0 ]; then
  banner_failed  "$push_line" "$summary_line" "$release_line" "$codex_line" "$vercel_line" \
    "All installers are missing — check the CI logs."
elif [ "$vercel_broken" = 1 ]; then
  banner_partial "$push_line" "$summary_line" "$release_line" "$codex_line" "$vercel_line" \
    "Vercel couldn't build this commit. The live site is STALE — still showing the previous successful deploy. Check the Vercel dashboard and fix the build error."
elif [ "$codex_broken" = 1 ]; then
  banner_partial "$push_line" "$summary_line" "$release_line" "$codex_line" "$vercel_line" \
    "README's Codex URL didn't return 200. Verify in Vercel dashboard and update README.md if needed."
else
  banner_partial "$push_line" "$summary_line" "$release_line" "$codex_line" "$vercel_line"
fi

# Success path — override the default-failure EXIT trap so it doesn't fire.
trap - EXIT
exit 0
