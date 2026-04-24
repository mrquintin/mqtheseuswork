#!/bin/bash
#
# Convenience wrapper: run theseus-codex/scripts/clear-library.ts from
# anywhere in the repo. Reason for existence:
#
#   $ cd ~/Desktop/Theseus
#   $ npm run db:clear-library
#   npm error enoent Could not read package.json: ...
#
# — npm looks for package.json in the current directory, so the command
# only works from inside `theseus-codex/`. This script cd's there
# automatically, re-exports the DATABASE_URL you supplied, and forwards
# any flags (--dry-run, --yes, --also-sessions, --keep-audit).
#
# Usage from anywhere inside the repo:
#   DATABASE_URL="postgresql://..." ./scripts/clear-codex-library.sh
#   DATABASE_URL="postgresql://..." ./scripts/clear-codex-library.sh --dry-run
#
# Note: DATABASE_URL must point at the Supabase *direct* connection
# (port 5432, i.e. aws-1-…pooler.supabase.com:5432/postgres) so the
# script can run DDL/DML cleanly. The transaction pooler (port 6543)
# works too for deletes but is slower per round-trip.

set -euo pipefail

# Resolve the repo root from this script's own location so it works no
# matter where the user cd's before invoking it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEX_DIR="$REPO_ROOT/theseus-codex"

if [ ! -d "$CODEX_DIR" ]; then
  echo "ERROR: expected $CODEX_DIR to exist" >&2
  exit 1
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  echo "       Export it first (use Supabase's DIRECT URL on port 5432):" >&2
  echo "       export DATABASE_URL='postgresql://<user>:<pw>@<host>:5432/postgres'" >&2
  exit 1
fi

cd "$CODEX_DIR"
exec npm run db:clear-library -- "$@"
