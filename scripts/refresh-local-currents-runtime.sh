#!/usr/bin/env bash
# Refresh the local launchd-hosted Currents API/scheduler runtime after a
# Supabase DB password rotation.
#
# The public theseus-currents.thenashlabhivemind.com origin is currently a
# Cloudflare Tunnel to this Mac. The launchd services read an untracked env file
# under ~/.theseus-currents/app/current_events_api/.env, not the repo copy.
# This script updates that runtime env file and can restart the two Python
# services so they actually pick up the new credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUNTIME_ENV="${CURRENTS_RUNTIME_ENV:-$HOME/.theseus-currents/app/current_events_api/.env}"
SOURCE_ENV="${CURRENTS_SOURCE_ENV:-$REPO_ROOT/current_events_api/.env}"
RESTART=0
HEALTH_CHECK=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/refresh-local-currents-runtime.sh [--restart] [--health-check]

Options:
  --restart       Kickstart the launchd API and scheduler services after
                  updating the runtime env. This restarts those two services.
  --health-check  Poll local /readyz and public /readyz after restart.
  -h, --help      Show this help.

Inputs:
  DATABASE_URL_NEW and DIRECT_URL_NEW are used when present. Otherwise the
  script reads DATABASE_URL and DIRECT_URL from current_events_api/.env.

Rotation hook:
  CURRENTS_BACKEND_REFRESH_CMD="./scripts/refresh-local-currents-runtime.sh --restart --health-check"
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --restart)
      RESTART=1
      ;;
    --health-check)
      HEALTH_CHECK=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [ ! -f "$RUNTIME_ENV" ]; then
  echo "ERROR: runtime env file not found: $RUNTIME_ENV" >&2
  exit 1
fi

read_dotenv_value() {
  local key="$1"
  local file="$2"
  node - "$key" "$file" <<'NODE'
const fs = require("fs");
const key = process.argv[2];
const file = process.argv[3];
if (!fs.existsSync(file)) process.exit(1);
const text = fs.readFileSync(file, "utf8");
for (const rawLine of text.split(/\r?\n/)) {
  if (!rawLine.includes("=") || rawLine.trimStart().startsWith("#")) continue;
  const [rawKey, ...rest] = rawLine.split("=");
  if (rawKey.trim() !== key) continue;
  let value = rest.join("=").trim();
  const quote = value[0];
  if ((quote === '"' || quote === "'") && value.endsWith(quote)) {
    value = value.slice(1, -1);
  }
  process.stdout.write(value);
  process.exit(0);
}
process.exit(1);
NODE
}

DATABASE_URL_VALUE="${DATABASE_URL_NEW:-}"
DIRECT_URL_VALUE="${DIRECT_URL_NEW:-}"
if [ -z "$DATABASE_URL_VALUE" ]; then
  DATABASE_URL_VALUE="$(read_dotenv_value DATABASE_URL "$SOURCE_ENV" || true)"
fi
if [ -z "$DIRECT_URL_VALUE" ]; then
  DIRECT_URL_VALUE="$(read_dotenv_value DIRECT_URL "$SOURCE_ENV" || true)"
fi
if [ -z "$DATABASE_URL_VALUE" ] && [ -z "$DIRECT_URL_VALUE" ]; then
  echo "ERROR: could not find DATABASE_URL or DIRECT_URL from env or $SOURCE_ENV" >&2
  exit 1
fi
if [ -z "$DATABASE_URL_VALUE" ]; then
  DATABASE_URL_VALUE="$DIRECT_URL_VALUE"
fi
if [ -z "$DIRECT_URL_VALUE" ]; then
  DIRECT_URL_VALUE="$DATABASE_URL_VALUE"
fi

backup="${RUNTIME_ENV}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cp "$RUNTIME_ENV" "$backup"
chmod 600 "$backup" 2>/dev/null || true

RUNTIME_ENV="$RUNTIME_ENV" \
DATABASE_URL_VALUE="$DATABASE_URL_VALUE" \
DIRECT_URL_VALUE="$DIRECT_URL_VALUE" \
node <<'NODE'
const fs = require("fs");
const file = process.env.RUNTIME_ENV;
const updates = {
  DATABASE_URL: process.env.DATABASE_URL_VALUE,
  DIRECT_URL: process.env.DIRECT_URL_VALUE,
  THESEUS_CODEX_DATABASE_URL: process.env.DATABASE_URL_VALUE,
};
let text = fs.readFileSync(file, "utf8");
for (const [key, value] of Object.entries(updates)) {
  if (!value) continue;
  const line = `${key}=${JSON.stringify(value)}`;
  const re = new RegExp(`^\\s*${key.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}\\s*=.*$`, "m");
  if (re.test(text)) {
    text = text.replace(re, line);
  } else {
    if (text && !text.endsWith("\n")) text += "\n";
    text += `${line}\n`;
  }
}
fs.writeFileSync(file, text);
NODE
chmod 600 "$RUNTIME_ENV" 2>/dev/null || true

echo "Updated local Currents runtime env: $RUNTIME_ENV"
echo "Backup written: $backup"

if [ "$RESTART" = "1" ]; then
  uid="$(id -u)"
  echo "Restarting launchd services com.theseus.currents-api and com.theseus.currents-scheduler..."
  launchctl kickstart -k "gui/${uid}/com.theseus.currents-api"
  launchctl kickstart -k "gui/${uid}/com.theseus.currents-scheduler"
fi

if [ "$HEALTH_CHECK" = "1" ]; then
  echo "Checking local/public Currents readiness..."
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    local_status="$(curl -sS -o /tmp/theseus-currents-local.json -w '%{http_code}' --max-time 8 http://127.0.0.1:8088/readyz || echo 000)"
    public_status="$(curl -sS -o /tmp/theseus-currents-public.json -w '%{http_code}' --max-time 12 https://theseus-currents.thenashlabhivemind.com/readyz || echo 000)"
    echo "  attempt ${attempt}: local=${local_status} public=${public_status}"
    if [ "$local_status" = "200" ] && [ "$public_status" = "200" ]; then
      echo "Currents runtime is ready."
      exit 0
    fi
    sleep 10
  done
  echo "WARNING: readiness did not return 200 yet. Supabase may still be cooling down from ECIRCUITBREAKER."
  echo "Local response:"
  sed -E 's#postgresql://[^[:space:]"]+#postgresql://<redacted>#g' /tmp/theseus-currents-local.json 2>/dev/null || true
  echo ""
  echo "Public response:"
  sed -E 's#postgresql://[^[:space:]"]+#postgresql://<redacted>#g' /tmp/theseus-currents-public.json 2>/dev/null || true
fi
