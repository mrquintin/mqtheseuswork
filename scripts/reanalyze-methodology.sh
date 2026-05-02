#!/usr/bin/env bash
set -euo pipefail

# Safe wrapper for the methodological reanalysis pass. By default this is a
# dry-run. Pass --apply to write idempotent MethodologyProfile rows.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
NOOSPHERE_DIR="$ROOT/noosphere"

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT/.venv/currents/bin/python" ]; then
    PYTHON_BIN="$ROOT/.venv/currents/bin/python"
  elif [ -x "$ROOT/.venv-currents/bin/python" ]; then
    PYTHON_BIN="$ROOT/.venv-currents/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

needs_db=1
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      needs_db=0
      ;;
    --codex-db-url|--codex-db-url=*)
      needs_db=0
      ;;
  esac
done

if [ "$needs_db" = "1" ] && [ -z "${THESEUS_CODEX_DATABASE_URL:-}${CODEX_DATABASE_URL:-}${DIRECT_URL:-}${DATABASE_URL:-}" ]; then
  echo "ERROR: no Codex database URL is set." >&2
  echo "Export one of: THESEUS_CODEX_DATABASE_URL / CODEX_DATABASE_URL / DIRECT_URL / DATABASE_URL" >&2
  exit 2
fi

cd "$NOOSPHERE_DIR"
export PYTHONPATH="$NOOSPHERE_DIR${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON_BIN" -m noosphere codex-methodology-reanalyze "$@"
