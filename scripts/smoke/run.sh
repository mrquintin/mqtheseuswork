#!/usr/bin/env bash
# scripts/smoke/run.sh
#
# Single-command full-stack smoke harness. Runs every section in order
# and HALTS on the first failure. Each section writes a structured
# JSON to docs/verification/smoke/<timestamp>/<section>.json so an
# operator can debug from the artifact alone.
#
# Usage:
#   ./scripts/smoke/run.sh                 # run every section
#   ./scripts/smoke/run.sh frontend-routes # run a single section
#   PUBLIC_BASE_URL=http://127.0.0.1:3000 ./scripts/smoke/run.sh
#                                          # also probe live frontend
#
# Exit codes:
#   0  every section passed
#   1  one or more sections failed (see JSON for details)
#   2  invalid arguments

set -u
set -o pipefail

cd "$(git rev-parse --show-toplevel)"

# Bootstrap PYTHONPATH so the smoke harness finds the in-repo packages
# even when running in a venv that doesn't have them pip-installed.
# Without this, Python picks up the repo's outer `current_events_api/`
# directory as an implicit NAMESPACE package, never reaches the real
# `current_events_api/current_events_api/__init__.py`, and the
# `from current_events_api.main import app` line in api_endpoints.py
# fails with "cannot import name '__version__' from current_events_api
# (unknown location)". Same fix covers noosphere.
_repo_root="$(pwd)"
export PYTHONPATH="${_repo_root}/current_events_api:${_repo_root}/noosphere:${PYTHONPATH:-}"

# Bypass the Round-19b prompt 23 boot-check during smoke. The smoke
# harness boots the FastAPI app via TestClient, which runs the lifespan
# handler. The lifespan handler calls run_boot_check() which refuses
# to start when required env vars are missing. THESEUS_BOOT_CHECK=skip
# short-circuits the check with a loud structured-log line; the bypass
# is intentionally inert in production (operators never set this var
# in a real deploy and watch for the boot_check_skipped log line).
export THESEUS_BOOT_CHECK=skip
export THESEUS_BOOT_CHECK_REASON="smoke-harness scripts/smoke/run.sh"
# Also export the existing in-lifespan skip flag (older path) so we
# don't depend on which name is read first.
export THESEUS_SKIP_BOOT_CHECK=1

# Crucially, also skip the *stateful* lifespan init (store, OpinionBus,
# OpinionTailer, persistent budget). The boot-check skip alone wasn't
# enough — make_store() / tailer.start() hang trying to connect to the
# stub DATABASE_URL=db.invalid:1 (intentionally non-routable). With
# THESEUS_SMOKE_MODE=1, the lifespan installs no-op stand-ins and
# yields immediately, then routes are registered and the smoke harness
# can probe them. The bypass is announced loudly in stderr by the
# lifespan handler itself so a misconfigured prod deploy cannot
# silently inherit it.
export THESEUS_SMOKE_MODE=1

# Stub values for the four vars the env validator wants populated. The
# smoke harness never calls Anthropic, never connects to a real DB, and
# never hits Supabase — these stubs exist only so any code path that
# inspects an env var beyond the boot-check sees a non-empty string.
# Stubs use the non-routable db.invalid pattern + obviously-fake key
# shapes so a leak into a prod context is immediately recognisable.
export THESEUS_MODE="${THESEUS_MODE:-algorithms-only}"
export DATABASE_URL="${DATABASE_URL:-postgresql://stub:stub@db.invalid:1/stub}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-sk-ant-SMOKE_STUB_VALUE_NOT_A_REAL_KEY}"
export FORECASTS_INGEST_ORG_ID="${FORECASTS_INGEST_ORG_ID:-smoke-org}"
export FORECASTS_OPERATOR_SECRET="${FORECASTS_OPERATOR_SECRET:-deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef}"

if [ -t 1 ]; then
  C_RESET=$'\033[0m'
  C_GREEN=$'\033[1;32m'
  C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'
  C_BLUE=$'\033[1;34m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""
fi

ALL_SECTIONS=(
  frontend-routes
  api-endpoints
  cli-help
  scheduler-tick
  pipelines-e2e
)

if [ "$#" -gt 0 ]; then
  for s in "$@"; do
    found=0
    for a in "${ALL_SECTIONS[@]}"; do
      [ "$s" = "$a" ] && found=1 && break
    done
    if [ "$found" != 1 ]; then
      echo "smoke: unknown section '$s'" >&2
      echo "smoke: valid sections: ${ALL_SECTIONS[*]}" >&2
      exit 2
    fi
  done
  SECTIONS=("$@")
else
  SECTIONS=("${ALL_SECTIONS[@]}")
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="docs/verification/smoke/${TIMESTAMP}"
mkdir -p "${OUT_DIR}"

echo ""
echo "${C_BLUE}=== Theseus smoke harness — ${TIMESTAMP} ===${C_RESET}"
echo "Output: ${OUT_DIR}"
echo "Sections: ${SECTIONS[*]}"
[ -n "${PUBLIC_BASE_URL:-}" ] && echo "PUBLIC_BASE_URL: ${PUBLIC_BASE_URL}"
echo ""

PYTHON="${PYTHON:-python3}"

run_section() {
  local section="$1"
  local module
  case "$section" in
    frontend-routes) module="scripts.smoke.frontend_routes" ;;
    api-endpoints)   module="scripts.smoke.api_endpoints" ;;
    cli-help)        module="scripts.smoke.cli_help" ;;
    scheduler-tick)  module="scripts.smoke.scheduler_tick" ;;
    pipelines-e2e)   module="scripts.smoke.pipelines_e2e" ;;
    *) echo "smoke: unknown section '$section'" >&2; return 2 ;;
  esac
  echo "${C_BLUE}--- ${section} ---${C_RESET}"
  local args=(--output-dir "${OUT_DIR}")
  if [ "$section" = "frontend-routes" ] && [ -n "${PUBLIC_BASE_URL:-}" ]; then
    args+=(--base-url "${PUBLIC_BASE_URL}")
  fi
  local rc=0
  "${PYTHON}" -m "${module}" "${args[@]}" || rc=$?
  return "$rc"
}

OVERALL_RC=0
PASSED=()
FAILED=()

for section in "${SECTIONS[@]}"; do
  if run_section "${section}"; then
    PASSED+=("${section}")
    echo "${C_GREEN}  ✓ ${section}${C_RESET}"
  else
    FAILED+=("${section}")
    OVERALL_RC=1
    echo "${C_RED}  ✗ ${section} (see ${OUT_DIR}/${section}.json)${C_RESET}"
    break
  fi
  echo ""
done

# Summary file: lets CI / sync read overall status without inspecting
# every per-section JSON.
"${PYTHON}" - "${OUT_DIR}" "${PASSED[@]:-}" -- "${FAILED[@]:-}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
sep = sys.argv.index("--")
passed = [s for s in sys.argv[2:sep] if s]
failed = [s for s in sys.argv[sep+1:] if s]

summary = {
    "output_dir": str(out_dir),
    "ok": len(failed) == 0,
    "passed": passed,
    "failed": failed,
}
(out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2))
PY

echo ""
echo "${C_BLUE}=== Summary ===${C_RESET}"
echo "Passed: ${#PASSED[@]} / ${#SECTIONS[@]}"
[ "${#FAILED[@]}" -gt 0 ] && echo "${C_RED}Failed: ${FAILED[*]}${C_RESET}"
echo "Artifacts: ${OUT_DIR}/"
echo ""

exit "${OVERALL_RC}"
