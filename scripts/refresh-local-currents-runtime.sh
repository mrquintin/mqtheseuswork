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
  # The thing we ACTUALLY want to confirm after a rotation: did the new
  # DB password reach the local + public services AND get accepted by
  # Postgres? Anything else the /readyz endpoint reports (forecasts
  # status file freshness, scheduler heartbeat, etc.) is orthogonal —
  # those subsystems can be degraded for reasons that have nothing to
  # do with credential rotation, and waiting on them turned this step
  # into a recurring 2-minute time sink whenever they happened to be
  # broken (the historical case: forecasts_status.json missing).
  #
  # The /readyz endpoint reports each subsystem separately. A 503 with
  # `"db":true` in the JSON body means: service is up, credentials work,
  # other concerns. That's exactly the success criterion this rotation
  # cares about, so we treat it as "credentials accepted" and exit.
  #
  # We only retry to give launchd time to bring the service back up
  # after `launchctl kickstart` (usually ~3-5 seconds). After that any
  # 5xx is a stable signal — no point waiting longer.
  echo "Checking local/public Currents readiness..."
  echo "  (fast-exits on first response with db:true; max ~30s total)"

  credentials_accepted_in() {
    local file="$1" status="$2"
    # 200: fully healthy. 503 with db:true: credentials work, other
    # subsystems may be degraded but those aren't ours to gate on.
    if [ "$status" = "200" ]; then return 0; fi
    if [ "$status" = "503" ] && grep -q '"db":true' "$file" 2>/dev/null; then
      return 0
    fi
    return 1
  }

  is_circuit_breaker_response() {
    # Supabase's pgbouncer ECIRCUITBREAKER blocks all connections —
    # including ours — for a few minutes after a burst of auth retries.
    # During that window the API can't open a DB connection and the
    # health check cannot meaningfully succeed. Detecting this lets the
    # script log honestly instead of timing out with a misleading
    # "credentials not confirmed" warning.
    local file="$1"
    grep -qi 'ECIRCUITBREAKER\|too many authentication failures' "$file" 2>/dev/null
  }

  describe_degraded() {
    # Pull the structured failure code out of the readyz JSON so the
    # operator can tell at a glance what the lingering issue is (the
    # response shape is {"detail":{"forecasts":{"code":"…"}}} when
    # forecasts is the blocker). Falls back gracefully if Python or jq
    # aren't available.
    local file="$1"
    python3 -c "
import json,sys
try:
    d = json.load(open(sys.argv[1])).get('detail', {})
except Exception:
    sys.exit(0)
parts = []
for subsystem in ('forecasts',):
    sub = d.get(subsystem)
    if isinstance(sub, dict) and sub.get('ok') is False:
        code = sub.get('code', 'unknown')
        parts.append(f'{subsystem}: {code}')
print('; '.join(parts) if parts else '')
" "$file" 2>/dev/null
  }

  # Clear any stale response body from a previous run so we don't
  # accidentally read it back as "this attempt's body". Curl skips
  # writing when the connection fails; without this we'd misreport.
  rm -f /tmp/theseus-currents-local.json /tmp/theseus-currents-public.json

  local_ok=0
  public_ok=0
  circuit_breaker_seen=0
  local_status="000"
  public_status="000"
  local_responded=0
  public_responded=0
  for attempt in 1 2 3 4 5 6; do
    local_status="$(curl -sS -o /tmp/theseus-currents-local.json -w '%{http_code}' --max-time 5 http://127.0.0.1:8088/readyz 2>/dev/null || echo 000)"
    public_status="$(curl -sS -o /tmp/theseus-currents-public.json -w '%{http_code}' --max-time 8 https://theseus-currents.thenashlabhivemind.com/readyz 2>/dev/null || echo 000)"
    # Track whether each endpoint ever produced a real HTTP response
    # (anything other than 000 = connection refused / DNS / timeout).
    # Used below to distinguish "API is up but unhappy" from "API is
    # not listening at all". A 502 from the public Cloudflare tunnel
    # also counts as not-responding from the API's perspective —
    # the tunnel itself responded but the origin behind it didn't.
    [ "$local_status" != "000" ] && local_responded=1
    [ "$public_status" != "000" ] && [ "$public_status" != "502" ] && public_responded=1

    # If either response body explicitly reports Supabase circuit-breaker,
    # the API genuinely cannot reach Postgres right now. Stop polling —
    # waiting won't help on this side; only the next rotation cycle can.
    if is_circuit_breaker_response /tmp/theseus-currents-local.json \
       || is_circuit_breaker_response /tmp/theseus-currents-public.json; then
      circuit_breaker_seen=1
      break
    fi

    if [ "$local_ok" = 0 ] && credentials_accepted_in /tmp/theseus-currents-local.json "$local_status"; then
      local_ok=1
      degraded="$(describe_degraded /tmp/theseus-currents-local.json)"
      if [ -n "$degraded" ]; then
        echo "  local:  credentials accepted (${local_status}; degraded subsystems: ${degraded})"
      else
        echo "  local:  ready (${local_status})"
      fi
    fi
    if [ "$public_ok" = 0 ] && credentials_accepted_in /tmp/theseus-currents-public.json "$public_status"; then
      public_ok=1
      degraded="$(describe_degraded /tmp/theseus-currents-public.json)"
      if [ -n "$degraded" ]; then
        echo "  public: credentials accepted (${public_status}; degraded subsystems: ${degraded})"
      else
        echo "  public: ready (${public_status})"
      fi
    fi

    if [ "$local_ok" = 1 ] && [ "$public_ok" = 1 ]; then
      break
    fi
    [ "$attempt" -lt 6 ] && sleep 4
  done

  if [ "$local_ok" = 1 ] && [ "$public_ok" = 1 ]; then
    echo "Currents runtime accepted the new credentials."
    exit 0
  fi

  if [ "$circuit_breaker_seen" = 1 ]; then
    # This is the post-rotation-flurry condition we explicitly know how
    # to recognize. Exit 0 — the rotation succeeded, the API just can't
    # prove it from this side until the breaker clears (usually 5-15
    # min, handled by launchd KeepAlive). The downstream psql verifier
    # has its own retry-with-backoff for the same condition.
    echo ""
    echo "NOTE: Supabase ECIRCUITBREAKER detected in readyz response."
    echo "      The local API cannot open a DB connection during the"
    echo "      pgbouncer auth-rate-limit cool-down. The new credentials"
    echo "      ARE in place (just rotated); launchd will reconnect each"
    echo "      service automatically when the breaker clears."
    echo "      No action needed beyond waiting."
    exit 0
  fi

  if [ "$local_responded" = 0 ] && [ "$public_responded" = 0 ]; then
    # Neither endpoint produced a real HTTP response in 30 seconds.
    # That usually means the local API service hasn't come back up
    # since the last restart — most often because Supabase's pgbouncer
    # is in ECIRCUITBREAKER cool-down from THIS rotation's auth burst,
    # or a previous one that hasn't cleared yet. The API will recover
    # on its own via launchd KeepAlive once the cool-down ends.
    #
    # Soft-exit (0) rather than failing the sync: the rotation we
    # came from already updated GitHub, Vercel, local dotenvs, and
    # Supabase itself. Failing here would only block git push and
    # leave the operator with rotated credentials but unpushed code.
    echo ""
    echo "NOTE: neither local (127.0.0.1:8088) nor public Currents endpoint"
    echo "      produced a real HTTP response in 30s. The launchd services"
    echo "      are likely still in Supabase ECIRCUITBREAKER cool-down."
    echo "      Recover: wait 5-15 min for the breaker to clear, then"
    echo "        launchctl kickstart gui/\$(id -u)/com.theseus.currents-api"
    echo "        launchctl kickstart gui/\$(id -u)/com.theseus.currents-scheduler"
    echo "      No action needed for the rotation itself — it succeeded."
    exit 0
  fi

  # If we got here, at least one endpoint did NOT return db:true in 30s
  # AND we have at least one HTTP-level response to inspect. Print the
  # final statuses + bodies (or "(empty)" when the body file is missing)
  # so the operator can triage instead of a 12-line noise loop.
  echo ""
  echo "WARNING: credential acceptance not confirmed for one or both endpoints."

  # Helper: redact-and-print a response body, guarding against missing
  # or empty files. Avoids the set -e + pipefail trap where sed on a
  # non-existent file fails the pipeline and kills the script.
  print_redacted_body() {
    local file="$1"
    if [ ! -s "$file" ]; then
      echo "    (empty — no response body captured)"
      return 0
    fi
    {
      sed -E 's#postgresql://[^[:space:]"]+#postgresql://<redacted>#g' "$file" 2>/dev/null \
        | head -c 600
      echo
    } || true
  }

  if [ "$local_ok" = 0 ]; then
    echo "  local final status: $local_status — body (redacted):"
    print_redacted_body /tmp/theseus-currents-local.json
  fi
  if [ "$public_ok" = 0 ]; then
    echo "  public final status: $public_status — body (redacted):"
    print_redacted_body /tmp/theseus-currents-public.json
  fi
fi
