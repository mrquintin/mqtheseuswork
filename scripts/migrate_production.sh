#!/usr/bin/env bash
# Apply pending Prisma and Alembic migrations against $DATABASE_URL.
#
# Contract:
#   - DATABASE_URL must be set and must parse as postgres:// or postgresql://.
#   - The parsed host is refused when it is localhost, 127.0.0.1, or 0.0.0.0
#     unless --allow-localhost is passed for a local rehearsal.
#   - psql, npx, and alembic must exist before any plan is gathered.
#   - Only host, port, and database name are printed; credentials are never
#     echoed.
#   - The operator must type the parsed hostname exactly before any migrator
#     command is allowed to run.
#   - Prisma runs from theseus-codex/; Alembic runs from noosphere/ with
#     THESEUS_DATABASE_URL set from DATABASE_URL so both migrators target the
#     same database.
#
# Exit codes:
#   0 success.
#   1 pre-flight, confirmation, pending-dry-run, or post-check failure.
#   2 Prisma migrate deploy failed, or Prisma still reports pending work.
#   3 Alembic upgrade head failed, or Alembic still reports pending work after
#     Prisma already applied.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ALLOW_LOCALHOST=0
DRY_RUN=0
SKIP_SNAPSHOT=0
SNAPSHOT_PATH=""

usage() {
  cat <<'USAGE'
Usage: scripts/migrate_production.sh [--allow-localhost] [--dry-run] [--skip-snapshot]

Applies pending Prisma and Alembic migrations after an explicit host
confirmation. A structure-only snapshot of the target database is written to
docs/architecture/snapshots/ before any migration runs unless --skip-snapshot
is passed (intended only for local rehearsals). --dry-run performs the same
pre-flight and plan checks but never runs prisma migrate deploy or alembic
upgrade head.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --allow-localhost)
      ALLOW_LOCALHOST=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-snapshot)
      SKIP_SNAPSHOT=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: ${arg}"
      ;;
  esac
done

PG_HOST=""
PG_PORT=""
PG_DB=""

parse_database_url() {
  local raw_url="${DATABASE_URL:-}"
  if [[ -z "$raw_url" ]]; then
    fail "DATABASE_URL is not set"
  fi

  if [[ "$raw_url" != postgresql://* && "$raw_url" != postgres://* ]]; then
    fail "DATABASE_URL must start with postgresql:// or postgres://"
  fi

  local rest="${raw_url#*://}"
  if [[ "$rest" != */* ]]; then
    fail "DATABASE_URL is malformed: missing database name"
  fi

  local authority="${rest%%/*}"
  local path_and_query="${rest#*/}"
  local db_name="${path_and_query%%\?*}"
  db_name="${db_name%%#*}"

  if [[ -z "$authority" || -z "$db_name" ]]; then
    fail "DATABASE_URL is malformed: missing host or database name"
  fi

  local host_port="${authority##*@}"
  local host=""
  local port="5432"

  if [[ -z "$host_port" ]]; then
    fail "DATABASE_URL is malformed: missing host"
  fi

  if [[ "$host_port" == \[* ]]; then
    if [[ "$host_port" != *\]* ]]; then
      fail "DATABASE_URL is malformed: invalid bracketed host"
    fi
    host="${host_port#\[}"
    host="${host%%\]*}"
    local after_host="${host_port#*\]}"
    if [[ "$after_host" == :* ]]; then
      port="${after_host#:}"
    elif [[ -n "$after_host" ]]; then
      fail "DATABASE_URL is malformed: invalid host/port"
    fi
  else
    host="${host_port%%:*}"
    if [[ "$host_port" == *:* ]]; then
      port="${host_port##*:}"
    fi
  fi

  if [[ -z "$host" || -z "$port" ]]; then
    fail "DATABASE_URL is malformed: missing host or port"
  fi
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    fail "DATABASE_URL is malformed: port must be numeric"
  fi

  PG_HOST="$host"
  PG_PORT="$port"
  PG_DB="$db_name"
}

require_non_local_host() {
  case "$PG_HOST" in
    localhost|127.0.0.1|0.0.0.0)
      if [[ "$ALLOW_LOCALHOST" -ne 1 ]]; then
        fail "refusing local DATABASE_URL host '${PG_HOST}' without --allow-localhost"
      fi
      ;;
  esac
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "required command not found: ${name}"
  fi
}

print_target() {
  echo "Connection target:"
  printf '  target: %s:%s + %s\n' "$PG_HOST" "$PG_PORT" "$PG_DB"
  printf '  host:   %s\n' "$PG_HOST"
  printf '  port:   %s\n' "$PG_PORT"
  printf '  db:     %s\n' "$PG_DB"
}

confirm_host() {
  local typed_host=""
  printf 'Type the host exactly to confirm: '
  if ! IFS= read -r typed_host; then
    fail "hostname confirmation was not provided"
  fi
  if [[ "$typed_host" != "$PG_HOST" ]]; then
    fail "hostname confirmation mismatch"
  fi
}

PRISMA_STATUS_OUTPUT=""
PRISMA_PENDING=0

parse_prisma_pending_count() {
  local output="$1"
  local count=""

  count="$(
    (
      printf '%s\n' "$output" |
        tr '[:upper:]' '[:lower:]' |
        sed -En 's/.*([0-9]+)[[:space:]]+migrations?[[:space:]]+(have[[:space:]]+)?not[[:space:]]+(yet[[:space:]]+)?(been[[:space:]]+)?applied.*/\1/p'
    ) || true
  )"
  count="${count%%$'\n'*}"
  if [[ -n "$count" ]]; then
    printf '%s\n' "$count"
    return
  fi

  if printf '%s\n' "$output" | grep -Eiq 'database schema is up to date|schema is up to date|no pending migrations'; then
    printf '0\n'
    return
  fi

  count="$(
    printf '%s\n' "$output" |
      awk '/^[[:space:]]*[0-9]{14}_[[:alnum:]_ -]+[[:space:]]*$/ { c++ } END { print c + 0 }'
  )"
  if [[ "$count" -gt 0 ]]; then
    printf '%s\n' "$count"
    return
  fi

  if printf '%s\n' "$output" | grep -Eiq 'not yet applied|not applied|pending'; then
    printf '1\n'
    return
  fi

  printf '0\n'
}

collect_prisma_plan() {
  local status=0
  set +e
  PRISMA_STATUS_OUTPUT="$(cd "${REPO_ROOT}/theseus-codex" && npx prisma migrate status 2>&1)"
  status=$?
  set -e

  echo
  echo "Prisma migrate status:"
  printf '%s\n' "$PRISMA_STATUS_OUTPUT"

  PRISMA_PENDING="$(parse_prisma_pending_count "$PRISMA_STATUS_OUTPUT")"
  if [[ "$status" -ne 0 && "$PRISMA_PENDING" -eq 0 ]]; then
    fail "prisma migrate status failed before a migration plan could be trusted"
  fi
  printf 'Prisma pending migrations: %s\n' "$PRISMA_PENDING"
}

ALEMBIC_CURRENT_OUTPUT=""
ALEMBIC_HISTORY_OUTPUT=""
ALEMBIC_PENDING=0

parse_alembic_pending_count() {
  local current_output="$1"
  local history_output="$2"

  if printf '%s\n' "$current_output" | grep -Eq '\(head\)|\(heads\)'; then
    printf '0\n'
    return
  fi

  local count
  count="$(
    printf '%s\n' "$history_output" |
      awk '
        /\(current\)/ { seen_current = 1; next }
        / -> / {
          if (!seen_current) {
            count++
          }
        }
        END { print count + 0 }
      '
  )"
  printf '%s\n' "$count"
}

collect_alembic_plan() {
  local current_status=0
  local history_status=0

  set +e
  ALEMBIC_CURRENT_OUTPUT="$(
    cd "${REPO_ROOT}/noosphere" &&
      THESEUS_DATABASE_URL="$DATABASE_URL" alembic current 2>&1
  )"
  current_status=$?
  ALEMBIC_HISTORY_OUTPUT="$(
    cd "${REPO_ROOT}/noosphere" &&
      THESEUS_DATABASE_URL="$DATABASE_URL" alembic history --indicate-current 2>&1
  )"
  history_status=$?
  set -e

  echo
  echo "Alembic current:"
  if [[ -n "$ALEMBIC_CURRENT_OUTPUT" ]]; then
    printf '%s\n' "$ALEMBIC_CURRENT_OUTPUT"
  else
    echo "(no current revision recorded)"
  fi

  echo
  echo "Alembic history --indicate-current:"
  printf '%s\n' "$ALEMBIC_HISTORY_OUTPUT"

  if [[ "$current_status" -ne 0 ]]; then
    fail "alembic current failed before a migration plan could be trusted"
  fi
  if [[ "$history_status" -ne 0 ]]; then
    fail "alembic history --indicate-current failed before a migration plan could be trusted"
  fi

  ALEMBIC_PENDING="$(parse_alembic_pending_count "$ALEMBIC_CURRENT_OUTPUT" "$ALEMBIC_HISTORY_OUTPUT")"
  printf 'Alembic pending migrations: %s\n' "$ALEMBIC_PENDING"
}

take_snapshot() {
  if [[ "$SKIP_SNAPSHOT" -eq 1 ]]; then
    echo
    echo "WARNING: --skip-snapshot was passed; no schema snapshot will be taken."
    return
  fi

  local snapshot_args=()
  if [[ "$ALLOW_LOCALHOST" -eq 1 ]]; then
    snapshot_args+=(--allow-localhost)
  fi

  local timestamp
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  SNAPSHOT_PATH="${REPO_ROOT}/docs/architecture/snapshots/${timestamp}.pre-migrate.sql"
  snapshot_args+=(--out="$SNAPSHOT_PATH")

  echo
  echo "Taking pre-migration schema snapshot via scripts/snapshot_production_schema.sh"
  if ! "${SCRIPT_DIR}/snapshot_production_schema.sh" "${snapshot_args[@]}"; then
    fail "pre-migration snapshot failed; refusing to apply migrations"
  fi
  echo "Pre-migration snapshot: ${SNAPSHOT_PATH}"
}

print_rollback_sql() {
  local stage="$1"
  cat >&2 <<ROLLBACK

============================================================
ROLLBACK REQUIRED (stage: ${stage})
============================================================

The migrator failed after partially advancing the schema. To return
production to the pre-migration state, restore the structure from the
snapshot captured at the start of this run:

  Snapshot: ${SNAPSHOT_PATH:-<none; --skip-snapshot was used>}

Recommended operator steps (run from a host with psql + the same
DATABASE_URL exported):

  # 1. Open a session and start a transaction so a typo can be undone.
  psql "\$DATABASE_URL" <<'SQL'
  BEGIN;

  -- 2. Roll the failed Alembic step back to the prior head, if any.
  --    (Only needed when failure stage = alembic.)
  -- \\! cd noosphere && THESEUS_DATABASE_URL="\$DATABASE_URL" alembic downgrade -1

  -- 3. Mark Prisma's _prisma_migrations row for the failed migration as
  --    rolled_back_at = NOW(); the failing migration name is in the
  --    Prisma output above.
  -- UPDATE "_prisma_migrations" SET rolled_back_at = NOW()
  --  WHERE finished_at IS NULL AND rolled_back_at IS NULL;

  COMMIT;
  SQL

  # 4. If the failure was structural (DDL partially applied), restore the
  #    schema from the snapshot. This drops and recreates objects, so it
  #    must be run with explicit operator confirmation and a fresh backup.
  # psql "\$DATABASE_URL" -v ON_ERROR_STOP=1 -f "${SNAPSHOT_PATH:-<snapshot>}"

After rollback, re-run scripts/migrate_production_dry_run.sh to confirm the
database matches the expected schema before retrying.
============================================================
ROLLBACK
}

run_prisma_deploy() {
  local output=""
  local status=0

  echo
  echo "Running Prisma migrate deploy from theseus-codex/"
  set +e
  output="$(cd "${REPO_ROOT}/theseus-codex" && npx prisma migrate deploy 2>&1)"
  status=$?
  set -e
  printf '%s\n' "$output"

  if [[ "$status" -ne 0 ]]; then
    echo "ERROR: Prisma migrate deploy failed; Alembic was not attempted." >&2
    print_rollback_sql "prisma"
    exit 2
  fi
}

run_alembic_upgrade() {
  local output=""
  local status=0

  echo
  echo "Running Alembic upgrade head from noosphere/"
  set +e
  output="$(
    cd "${REPO_ROOT}/noosphere" &&
      THESEUS_DATABASE_URL="$DATABASE_URL" alembic upgrade head 2>&1
  )"
  status=$?
  set -e
  printf '%s\n' "$output"

  if [[ "$status" -ne 0 ]]; then
    echo "ERROR: Alembic upgrade head failed after Prisma already applied." >&2
    print_rollback_sql "alembic"
    exit 3
  fi
}

confirm_apply() {
  local total_pending="$1"
  local answer=""

  printf 'apply %s pending migrations? (yes/no) ' "$total_pending"
  if ! IFS= read -r answer; then
    fail "final apply confirmation was not provided"
  fi
  if [[ "$answer" != "yes" ]]; then
    fail "final apply confirmation was not literal yes"
  fi
}

verify_clean_after_apply() {
  collect_prisma_plan
  if [[ "$PRISMA_PENDING" -ne 0 ]]; then
    echo "ERROR: Prisma still reports pending work after migrate deploy." >&2
    exit 2
  fi

  collect_alembic_plan
  if [[ "$ALEMBIC_PENDING" -ne 0 ]]; then
    echo "ERROR: Alembic still reports pending work after upgrade head." >&2
    exit 3
  fi
}

relation_exists() {
  local quoted_relation="$1"
  local exists=""
  exists="$(psql "$DATABASE_URL" -t -A -v ON_ERROR_STOP=1 \
    -c "SELECT to_regclass('${quoted_relation}') IS NOT NULL;" 2>/dev/null | tr -d '[:space:]')"
  [[ "$exists" == "t" ]]
}

print_row_counts() {
  local table=""
  local count=""

  echo
  echo "Post-migration row counts:"
  for table in ForecastMarket ForecastPrediction CurrentEvent Conclusion Claim; do
    if ! relation_exists "\"${table}\""; then
      printf '  %s: missing\n' "$table"
      continue
    fi
    count="$(psql "$DATABASE_URL" -t -A -v ON_ERROR_STOP=1 \
      -c "SELECT count(*) FROM \"${table}\";" | tr -d '[:space:]')"
    printf '  %s: %s\n' "$table" "$count"
  done
}

main() {
  parse_database_url
  require_non_local_host
  require_command psql
  require_command npx
  require_command alembic
  if [[ "$SKIP_SNAPSHOT" -ne 1 && "$DRY_RUN" -ne 1 ]]; then
    require_command pg_dump
  fi

  print_target
  confirm_host
  collect_prisma_plan
  collect_alembic_plan

  local total_pending=$((PRISMA_PENDING + ALEMBIC_PENDING))
  printf '\nTotal pending migrations: %s\n' "$total_pending"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run only; Prisma deploy and Alembic upgrade were not executed."
    if [[ "$total_pending" -ne 0 ]]; then
      fail "dry run found ${total_pending} pending migrations"
    fi
    exit 0
  fi

  confirm_apply "$total_pending"
  take_snapshot
  run_prisma_deploy
  run_alembic_upgrade
  verify_clean_after_apply
  print_row_counts
}

main
