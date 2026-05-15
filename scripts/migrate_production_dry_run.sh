#!/usr/bin/env bash
# Production migration dry-run.
#
# Performs three checks before any operator considers running
# scripts/migrate_production.sh against a real database:
#
#   1. Migration linearity check
#      (scripts/check_migration_linearity.py) -- no two migrations may
#      contradict each other.
#   2. Destructive-op justification -- if any pending Prisma migration
#      contains DROP COLUMN or DROP TABLE without a justification comment
#      somewhere in the same migration file, the script refuses. A
#      justification comment is a SQL line comment containing the marker
#      "JUSTIFY:" (case-insensitive).
#   3. Live plan vs. $DATABASE_URL -- delegates to
#      migrate_production.sh --dry-run for URL validation, host
#      confirmation, and pending-migration listing. The diff between the
#      migrations on disk and the live schema is empty iff this reports
#      zero pending migrations; in that case the wrapper refuses to
#      proceed (signal that the migration was already applied).
#
# Exit codes:
#   0  static checks pass AND the live plan reports pending work.
#   1  any check failed -- pre-flight, unjustified destructive ops,
#      already-applied state, or other migrate_production.sh failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/theseus-codex/prisma/migrations"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

echo "Step 1: migration linearity check"
if ! python3 "${SCRIPT_DIR}/check_migration_linearity.py" \
    --migrations-dir "$MIGRATIONS_DIR"; then
  fail "linearity check failed; refusing to dry-run"
fi

echo
echo "Step 2: destructive-op justification scan"
unjustified_count=0
unjustified_report=""
while IFS= read -r -d '' file; do
  # Match DROP COLUMN / DROP TABLE only when it appears as SQL (i.e., not as
  # part of a "-- ..." comment). We strip leading whitespace and reject lines
  # that begin with "--".
  if awk '
      {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        if (line ~ /^--/) next
        # Drop trailing inline comments before matching.
        sub(/--.*$/, "", line)
        if (line ~ /[Dd][Rr][Oo][Pp][[:space:]]+([Cc][Oo][Ll][Uu][Mm][Nn]|[Tt][Aa][Bb][Ll][Ee])/) {
          found = 1
        }
      }
      END { exit found ? 0 : 1 }
    ' "$file"; then
    if ! grep -iq 'JUSTIFY:' "$file"; then
      unjustified_count=$((unjustified_count + 1))
      unjustified_report+="  ${file#${REPO_ROOT}/}"$'\n'
    fi
  fi
done < <(find "$MIGRATIONS_DIR" -mindepth 2 -name 'migration.sql' -print0)

if [[ "$unjustified_count" -gt 0 ]]; then
  echo "Unjustified destructive operations:" >&2
  printf '%s' "$unjustified_report" >&2
  fail "${unjustified_count} migration(s) contain DROP COLUMN/DROP TABLE without a 'JUSTIFY:' comment"
fi
echo "  no unjustified DROP COLUMN / DROP TABLE found."

echo
echo "Step 3: live plan against \$DATABASE_URL"
plan_log="$(mktemp)"
trap 'rm -f "$plan_log"' EXIT

set +e
"${SCRIPT_DIR}/migrate_production.sh" --dry-run "$@" 2>&1 | tee "$plan_log"
plan_status="${PIPESTATUS[0]}"
set -e

total_pending="$(
  awk '/^Total pending migrations:/ { print $4; exit }' "$plan_log"
)"
total_pending="${total_pending:-}"

if [[ -z "$total_pending" ]]; then
  fail "live plan did not report a pending-migration total (exit ${plan_status}); see output above"
fi

if [[ "$total_pending" -eq 0 ]]; then
  fail "live plan reports 0 pending migrations; refusing dry-run (schema already matches migrations on disk)"
fi

echo
echo "Dry-run OK: ${total_pending} pending migration(s) ready to apply."
