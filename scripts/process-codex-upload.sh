#!/bin/bash
#
# Wrapper: run `noosphere ingest-from-codex` against the shared Supabase
# DB from the repo root, with PYTHONPATH pre-set. Lets the user process
# a queued Codex upload in one command:
#
#   DIRECT_URL="postgresql://..." ./scripts/process-codex-upload.sh <upload-id>
#
# or, to see what's queued first:
#
#   DIRECT_URL="postgresql://..." ./scripts/process-codex-upload.sh --list
#
# Why this wrapper exists:
#   * `python -m noosphere ...` requires the noosphere package to be
#     installed OR on PYTHONPATH. Neither is the case fresh after
#     `git clone`. This script sets PYTHONPATH automatically.
#   * The CLI's --codex-db-url / DIRECT_URL resolution is the same, but
#     exporting it from one place keeps the invocation terse.
#   * First-time users forget the `--upload-id` prefix on the id value;
#     this script accepts a bare id as the positional argument and adds
#     the flag itself.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NOOSPHERE_DIR="$REPO_ROOT/noosphere"

if [ ! -d "$NOOSPHERE_DIR" ]; then
  echo "ERROR: expected $NOOSPHERE_DIR to exist" >&2
  exit 1
fi

if [ -z "${DIRECT_URL:-}${DATABASE_URL:-}${THESEUS_CODEX_DATABASE_URL:-}" ]; then
  echo "ERROR: no Codex DB URL set." >&2
  echo "       export one of: DIRECT_URL / DATABASE_URL / THESEUS_CODEX_DATABASE_URL" >&2
  echo "       (Use the Supabase DIRECT connection, port 5432 — not the 6543 pooler.)" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  cat >&2 <<EOF
usage:
  $0 <upload-id>           # process a single upload
  $0 --list                # list queued uploads
  $0 <upload-id> --with-llm
  $0 <upload-id> --dry-run
EOF
  exit 2
fi

cd "$NOOSPHERE_DIR"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$NOOSPHERE_DIR"

if [ "$1" = "--list" ]; then
  shift
  exec python3 -m noosphere codex-queued "$@"
fi

# Accept bare id OR --upload-id X. If the first arg isn't a flag, treat
# it as the id and prepend the flag.
if [[ "$1" != --* ]]; then
  upload_id="$1"
  shift
  exec python3 -m noosphere ingest-from-codex --upload-id "$upload_id" "$@"
fi

exec python3 -m noosphere ingest-from-codex "$@"
