#!/usr/bin/env bash
# Snapshot the production Postgres schema (structure only, no row data) into
# docs/architecture/snapshots/<UTC-timestamp>.sql.
#
# Contract:
#   - DATABASE_URL must be set and must parse as postgres:// or postgresql://.
#   - --allow-localhost permits local rehearsal hosts; otherwise local hosts
#     are refused.
#   - pg_dump must exist; the dump runs with --schema-only --no-owner
#     --no-privileges so the result is portable across environments.
#   - The dump writes to a temporary file, is verified non-empty, and is only
#     then moved into place. A partial dump never replaces an existing
#     snapshot.
#   - Row data is never read or written.
#
# Designed to be called from the weekly scheduler that already drives the
# repo's housekeeping jobs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SNAPSHOT_DIR="${REPO_ROOT}/docs/architecture/snapshots"

ALLOW_LOCALHOST=0
OUTPUT_OVERRIDE=""

usage() {
  cat <<'USAGE'
Usage: scripts/snapshot_production_schema.sh [--allow-localhost] [--out PATH]

Writes a structure-only dump of $DATABASE_URL to
docs/architecture/snapshots/<UTC-timestamp>.sql, or to --out if provided.
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
    --out=*)
      OUTPUT_OVERRIDE="${arg#--out=}"
      ;;
    --out)
      fail "--out requires a value (use --out=PATH)"
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

if [[ -z "${DATABASE_URL:-}" ]]; then
  fail "DATABASE_URL is not set"
fi
if [[ "$DATABASE_URL" != postgresql://* && "$DATABASE_URL" != postgres://* ]]; then
  fail "DATABASE_URL must start with postgresql:// or postgres://"
fi

PG_HOST="${DATABASE_URL#*://}"
PG_HOST="${PG_HOST##*@}"
PG_HOST="${PG_HOST%%/*}"
PG_HOST="${PG_HOST%%:*}"
case "$PG_HOST" in
  localhost|127.0.0.1|0.0.0.0)
    if [[ "$ALLOW_LOCALHOST" -ne 1 ]]; then
      fail "refusing local DATABASE_URL host '${PG_HOST}' without --allow-localhost"
    fi
    ;;
esac

if ! command -v pg_dump >/dev/null 2>&1; then
  fail "required command not found: pg_dump"
fi

mkdir -p "$SNAPSHOT_DIR"

if [[ -n "$OUTPUT_OVERRIDE" ]]; then
  OUTPUT_PATH="$OUTPUT_OVERRIDE"
else
  TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_PATH="${SNAPSHOT_DIR}/${TIMESTAMP}.sql"
fi

TMP_PATH="$(mktemp "${OUTPUT_PATH}.partial.XXXXXX")"
trap 'rm -f "$TMP_PATH"' EXIT

echo "Writing structure-only snapshot of ${PG_HOST} to ${OUTPUT_PATH}"

pg_dump \
  --schema-only \
  --no-owner \
  --no-privileges \
  --no-comments \
  --dbname="$DATABASE_URL" \
  --file="$TMP_PATH"

if [[ ! -s "$TMP_PATH" ]]; then
  fail "pg_dump produced an empty file; refusing to publish snapshot"
fi

mv "$TMP_PATH" "$OUTPUT_PATH"
trap - EXIT

echo "Snapshot written: ${OUTPUT_PATH}"
echo "Size: $(wc -c < "$OUTPUT_PATH") bytes"
