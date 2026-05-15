#!/usr/bin/env bash
# Rotate the Supabase Postgres password and update every project consumer that
# stores it as a connection URL.
#
# What this updates by default:
#   1. Supabase project database password via the Management API.
#   2. Local ignored dotenv files that contain the project Postgres URL.
#   3. GitHub Actions secret CODEX_DATABASE_URL.
#   4. Vercel DATABASE_URL and DIRECT_URL for production, preview, development.
#   5. Latest Vercel production deployment, so runtime env snapshots refresh.
#
# Required for full automation:
#   SUPABASE_ACCESS_TOKEN  Supabase access token with database:write/database_write.
#   gh                    GitHub CLI authenticated to mrquintin/mqtheseuswork.
#   npx/vercel            Vercel CLI auth; this repo is linked at .vercel/.
#
# Safe defaults:
#   - The generated password is alphanumeric, so URL encoding cannot break psql,
#     Prisma, Vercel, or GitHub Actions.
#   - Passwords are never echoed. Values are passed through stdin or temporary
#     0600 files and then removed.
#   - Git-tracked dotenv files containing this Supabase URL are refused; secrets
#     belong in ignored .env.local-style files or provider secret stores.
#   - Without --yes, the operator must type the Supabase project ref before
#     the first write.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DRY_RUN=0
YES=0
DO_SUPABASE=1
DO_LOCAL_ENV=1
DO_GITHUB=1
DO_VERCEL=1
DO_REDEPLOY=1
DO_VERIFY=1
DO_CURRENTS_BACKEND_REFRESH=1
REQUIRE_CURRENTS_BACKEND_REFRESH=0

PROJECT_REF="${SUPABASE_PROJECT_REF:-}"
PASSWORD_FILE=""
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_SECRET_NAME="${GITHUB_SECRET_NAME:-CODEX_DATABASE_URL}"
VERCEL_TARGETS="${VERCEL_TARGETS:-production preview development}"
CURRENTS_BACKEND_REFRESH_CMD="${CURRENTS_BACKEND_REFRESH_CMD:-}"
ENV_FILES=()

TMP_FILES=()

cleanup() {
  local f
  for f in "${TMP_FILES[@]:-}"; do
    [ -n "$f" ] && rm -f "$f" 2>/dev/null || true
  done
}
trap cleanup EXIT

usage() {
  cat <<'USAGE'
Usage:
  scripts/rotate-supabase-db-password.sh [options]

Full rotation:
  SUPABASE_ACCESS_TOKEN=... scripts/rotate-supabase-db-password.sh

Preview the exact plan without writing anything:
  scripts/rotate-supabase-db-password.sh --dry-run

If you already reset the password manually in Supabase, update consumers only:
  scripts/rotate-supabase-db-password.sh \
    --skip-supabase-reset \
    --password-file /path/to/new-password

Options:
  --dry-run                 Print plan; do not reset Supabase or write secrets.
  --yes                     Skip interactive project-ref confirmation.
  --project-ref REF          Override project ref inferred from DIRECT_URL.
  --password-file FILE       Read the new password from FILE instead of generating.
  --skip-supabase-reset      Do not call Supabase Management API.
  --skip-local-env           Do not update local ignored .env files.
  --skip-github              Do not update GitHub Actions secret.
  --skip-vercel              Do not update Vercel env vars.
  --no-vercel-redeploy       Do not redeploy latest production deployment.
  --skip-currents-backend-refresh
                            Do not run CURRENTS_BACKEND_REFRESH_CMD.
  --require-currents-backend-refresh
                            Refuse to rotate unless CURRENTS_BACKEND_REFRESH_CMD
                            is set. Use this when the public Currents API /
                            scheduler are deployed outside Vercel.
  --no-verify                Do not run psql verification after rotation.
  --github-repo OWNER/REPO   Override repo for gh secret set.
  --github-secret NAME       Override GitHub secret name. Default CODEX_DATABASE_URL.
  --env-file PATH            Add an explicit dotenv file to update.
  -h, --help                 Show this help.

Environment:
  SUPABASE_ACCESS_TOKEN      Required unless --skip-supabase-reset or --dry-run.
  SUPABASE_PROJECT_REF       Optional project ref override.
  GITHUB_REPO                Optional OWNER/REPO override.
  GITHUB_SECRET_NAME         Optional GitHub secret name override.
  VERCEL_TARGETS             Space-separated targets; default:
                             production preview development.
  CURRENTS_BACKEND_REFRESH_CMD
                             Optional shell command run after provider secrets
                             are updated. It receives DATABASE_URL_NEW,
                             DIRECT_URL_NEW, SUPABASE_PROJECT_REF, and
                             THESEUS_DB_PASSWORD_NEW in its environment.
                             Example:
                               ssh app@host 'cd /srv/Theseus && ./scripts/apply-runtime-db-url.sh'
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

note() {
  printf '%s\n' "$*"
}

need_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "required command not found: ${name}"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --yes)
      YES=1
      ;;
    --project-ref)
      [ "$#" -ge 2 ] || fail "--project-ref requires a value"
      PROJECT_REF="$2"
      shift
      ;;
    --password-file)
      [ "$#" -ge 2 ] || fail "--password-file requires a value"
      PASSWORD_FILE="$2"
      shift
      ;;
    --skip-supabase-reset)
      DO_SUPABASE=0
      ;;
    --skip-local-env)
      DO_LOCAL_ENV=0
      ;;
    --skip-github)
      DO_GITHUB=0
      ;;
    --skip-vercel)
      DO_VERCEL=0
      DO_REDEPLOY=0
      ;;
    --no-vercel-redeploy)
      DO_REDEPLOY=0
      ;;
    --skip-currents-backend-refresh)
      DO_CURRENTS_BACKEND_REFRESH=0
      ;;
    --require-currents-backend-refresh)
      REQUIRE_CURRENTS_BACKEND_REFRESH=1
      ;;
    --no-verify)
      DO_VERIFY=0
      ;;
    --github-repo)
      [ "$#" -ge 2 ] || fail "--github-repo requires OWNER/REPO"
      GITHUB_REPO="$2"
      shift
      ;;
    --github-secret)
      [ "$#" -ge 2 ] || fail "--github-secret requires a name"
      GITHUB_SECRET_NAME="$2"
      shift
      ;;
    --env-file)
      [ "$#" -ge 2 ] || fail "--env-file requires a path"
      ENV_FILES+=("$2")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

cd "$REPO_ROOT"

need_cmd node
need_cmd curl

if [ "$DO_GITHUB" -eq 1 ]; then
  need_cmd gh
fi
if [ "$DO_VERCEL" -eq 1 ] || [ "$DO_REDEPLOY" -eq 1 ]; then
  need_cmd npx
fi

dotenv_value() {
  local key="$1"
  shift
  node - "$key" "$@" <<'NODE'
const fs = require("fs");
const key = process.argv[2];
const files = process.argv.slice(3);
for (const file of files) {
  if (!file || !fs.existsSync(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const m = rawLine.match(new RegExp("^\\s*" + key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*=\\s*(.*)\\s*$"));
    if (!m) continue;
    let value = m[1].trim();
    const quote = value[0];
    if ((quote === '"' || quote === "'") && value.endsWith(quote)) {
      value = value.slice(1, -1);
    }
    process.stdout.write(value);
    process.exit(0);
  }
}
NODE
}

discover_env_files() {
  find . \
    \( -path './.git' -o -path './node_modules' -o -path './theseus-codex/node_modules' -o -path './theseus-codex/.next' -o -path './.venv*' -o -path './*/__pycache__' \) -prune \
    -o -type f -name '.env*' -print |
    sort |
    while IFS= read -r f; do
      case "$f" in
        *.example|*.template|*.fake|*.sample)
          continue
          ;;
      esac
      printf '%s\n' "${f#./}"
    done
}

default_env_files=()
while IFS= read -r f; do
  [ -n "$f" ] && default_env_files+=("$f")
done < <(discover_env_files)
ENV_FILES=("${default_env_files[@]+"${default_env_files[@]}"}" "${ENV_FILES[@]+"${ENV_FILES[@]}"}")

DATABASE_URL_CURRENT="${DATABASE_URL:-}"
DIRECT_URL_CURRENT="${DIRECT_URL:-}"
if [ -z "$DATABASE_URL_CURRENT" ]; then
  DATABASE_URL_CURRENT="$(dotenv_value DATABASE_URL "${ENV_FILES[@]+"${ENV_FILES[@]}"}")"
fi
if [ -z "$DIRECT_URL_CURRENT" ]; then
  DIRECT_URL_CURRENT="$(dotenv_value DIRECT_URL "${ENV_FILES[@]+"${ENV_FILES[@]}"}")"
fi

if [ -z "$DATABASE_URL_CURRENT" ] && [ -z "$DIRECT_URL_CURRENT" ]; then
  fail "could not find DATABASE_URL or DIRECT_URL in env or local dotenv files"
fi

infer_project_ref() {
  local raw="$1"
  node - "$raw" <<'NODE'
const raw = process.argv[2];
try {
  const url = new URL(raw);
  const user = decodeURIComponent(url.username || "");
  let m = user.match(/^postgres\.([a-z0-9]{20})$/i);
  if (m) {
    process.stdout.write(m[1]);
    process.exit(0);
  }
  m = url.hostname.match(/^(?:db\.)?([a-z0-9]{20})\.supabase\.co$/i);
  if (m) {
    process.stdout.write(m[1]);
    process.exit(0);
  }
} catch {}
process.exit(1);
NODE
}

if [ -z "$PROJECT_REF" ]; then
  if [ -n "$DIRECT_URL_CURRENT" ]; then
    PROJECT_REF="$(infer_project_ref "$DIRECT_URL_CURRENT" || true)"
  fi
  if [ -z "$PROJECT_REF" ] && [ -n "$DATABASE_URL_CURRENT" ]; then
    PROJECT_REF="$(infer_project_ref "$DATABASE_URL_CURRENT" || true)"
  fi
fi

if [ -z "$PROJECT_REF" ]; then
  fail "could not infer Supabase project ref; pass --project-ref REF"
fi

if ! [[ "$PROJECT_REF" =~ ^[a-z0-9]{20}$ ]]; then
  fail "project ref '${PROJECT_REF}' does not look like a Supabase project ref"
fi

if [ -n "$PASSWORD_FILE" ]; then
  [ -f "$PASSWORD_FILE" ] || fail "password file does not exist: ${PASSWORD_FILE}"
  NEW_PASSWORD="$(tr -d '\r\n' < "$PASSWORD_FILE")"
else
  if [ "$DO_SUPABASE" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    fail "--skip-supabase-reset requires --password-file so consumers match the password already set in Supabase"
  fi
  NEW_PASSWORD="$(
    node <<'NODE'
const crypto = require("crypto");
const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
let out = "";
for (let i = 0; i < 48; i += 1) out += alphabet[crypto.randomInt(alphabet.length)];
process.stdout.write(out);
NODE
  )"
fi

if ! [[ "$NEW_PASSWORD" =~ ^[A-Za-z0-9]{32,128}$ ]]; then
  fail "new password must be 32-128 alphanumeric characters; use a generated password or a URL-safe file value"
fi

rewrite_url_password() {
  local raw="$1"
  [ -n "$raw" ] || return 0
  CURRENT_URL="$raw" NEW_PASSWORD="$NEW_PASSWORD" node <<'NODE'
const raw = process.env.CURRENT_URL;
try {
  const url = new URL(raw);
  url.password = process.env.NEW_PASSWORD;
  process.stdout.write(url.toString());
} catch (error) {
  process.stderr.write(`invalid Postgres URL: ${error.message}\n`);
  process.exit(1);
}
NODE
}

DATABASE_URL_NEW=""
DIRECT_URL_NEW=""
[ -n "$DATABASE_URL_CURRENT" ] && DATABASE_URL_NEW="$(rewrite_url_password "$DATABASE_URL_CURRENT")"
[ -n "$DIRECT_URL_CURRENT" ] && DIRECT_URL_NEW="$(rewrite_url_password "$DIRECT_URL_CURRENT")"

if [ -z "$DATABASE_URL_NEW" ]; then
  DATABASE_URL_NEW="$DIRECT_URL_NEW"
fi
if [ -z "$DIRECT_URL_NEW" ]; then
  DIRECT_URL_NEW="$DATABASE_URL_NEW"
fi

mask_url() {
  local raw="$1"
  [ -n "$raw" ] || return 0
  node - "$raw" <<'NODE'
const raw = process.argv[2];
try {
  new URL(raw);
  process.stdout.write(
    raw.replace(
      /:\/\/([^:@]+):([^@]*)@/,
      (_match, user) => `://${decodeURIComponent(user).replace(/^postgres\..+$/i, "postgres.<ref>")}:<password>@`,
    ),
  );
} catch {
  process.stdout.write("<unparseable-url>");
}
NODE
}

github_repo_default() {
  if [ -n "$GITHUB_REPO" ]; then
    printf '%s\n' "$GITHUB_REPO"
    return
  fi
  if gh repo view --json nameWithOwner --jq .nameWithOwner >/tmp/theseus-gh-repo.out 2>/dev/null; then
    TMP_FILES+=("/tmp/theseus-gh-repo.out")
    tr -d '\r\n' < /tmp/theseus-gh-repo.out
    return
  fi
  local remote=""
  remote="$(git remote get-url origin 2>/dev/null || true)"
  case "$remote" in
    git@github.com:*)
      remote="${remote#git@github.com:}"
      ;;
    https://github.com/*)
      remote="${remote#https://github.com/}"
      ;;
  esac
  remote="${remote%.git}"
  if [[ "$remote" == */* ]]; then
    printf '%s\n' "$remote"
    return
  fi
  printf 'mrquintin/mqtheseuswork\n'
}

GITHUB_REPO="$(github_repo_default)"

ENV_FILES_DISPLAY="(none)"
if [ "${#ENV_FILES[@]}" -gt 0 ]; then
  ENV_FILES_DISPLAY="${ENV_FILES[*]}"
fi

note "Rotation plan:"
printf '  Supabase project ref: %s\n' "$PROJECT_REF"
printf '  Local dotenv files:   %s\n' "$ENV_FILES_DISPLAY"
printf '  GitHub repo/secret:   %s / %s\n' "$GITHUB_REPO" "$GITHUB_SECRET_NAME"
printf '  Vercel targets:       %s\n' "$VERCEL_TARGETS"
printf '  Supabase reset:       %s\n' "$([ "$DO_SUPABASE" -eq 1 ] && echo yes || echo no)"
printf '  Vercel redeploy:      %s\n' "$([ "$DO_REDEPLOY" -eq 1 ] && echo yes || echo no)"
printf '  Currents backend hook:%s\n' "$(
  if [ "$DO_CURRENTS_BACKEND_REFRESH" -eq 0 ]; then
    echo ' skipped'
  elif [ -n "$CURRENTS_BACKEND_REFRESH_CMD" ]; then
    echo ' configured'
  elif [ "$REQUIRE_CURRENTS_BACKEND_REFRESH" -eq 1 ]; then
    echo ' REQUIRED BUT MISSING'
  else
    echo ' not configured'
  fi
)"
printf '  Verify with psql:     %s\n' "$([ "$DO_VERIFY" -eq 1 ] && echo yes || echo no)"
printf '  New DATABASE_URL:     %s\n' "$(mask_url "$DATABASE_URL_NEW")"
printf '  New DIRECT_URL:       %s\n' "$(mask_url "$DIRECT_URL_NEW")"

if [ "$DO_CURRENTS_BACKEND_REFRESH" -eq 1 ] && \
   [ "$REQUIRE_CURRENTS_BACKEND_REFRESH" -eq 1 ] && \
   [ -z "$CURRENTS_BACKEND_REFRESH_CMD" ]; then
  fail "CURRENTS_BACKEND_REFRESH_CMD is required. This prevents rotating the DB password while leaving the public Currents API/scheduler on stale credentials."
fi

if [ "$DRY_RUN" -eq 1 ]; then
  note
  note "Dry run: no password reset, files, GitHub secrets, or Vercel env vars were changed."
  exit 0
fi

if [ "$YES" -ne 1 ]; then
  printf 'Type the Supabase project ref exactly to rotate credentials: '
  IFS= read -r typed_ref
  if [ "$typed_ref" != "$PROJECT_REF" ]; then
    fail "project-ref confirmation mismatch"
  fi
fi

reset_supabase_password() {
  [ -n "${SUPABASE_ACCESS_TOKEN:-}" ] || fail "SUPABASE_ACCESS_TOKEN is required unless --skip-supabase-reset is used"
  local payload response code
  payload="$(mktemp /tmp/theseus-supabase-password.XXXXXX.json)"
  response="$(mktemp /tmp/theseus-supabase-response.XXXXXX.json)"
  chmod 600 "$payload" "$response"
  TMP_FILES+=("$payload" "$response")
  PAYLOAD="$payload" NEW_PASSWORD="$NEW_PASSWORD" node <<'NODE'
const fs = require("fs");
fs.writeFileSync(process.env.PAYLOAD, JSON.stringify({ password: process.env.NEW_PASSWORD }));
NODE
  code="$(
    curl -sS -o "$response" -w '%{http_code}' \
      -X PATCH "https://api.supabase.com/v1/projects/${PROJECT_REF}/database/password" \
      -H "Authorization: Bearer ${SUPABASE_ACCESS_TOKEN}" \
      -H "Content-Type: application/json" \
      --data-binary @"$payload"
  )"
  if [ "$code" != "200" ]; then
    echo "Supabase response body:" >&2
    sed -E 's/[A-Za-z0-9_=-]{32,}/<redacted>/g' "$response" >&2 || true
    fail "Supabase password reset failed with HTTP ${code}"
  fi
  note "Supabase password reset accepted."
}

update_local_env_files() {
  [ "${#ENV_FILES[@]}" -gt 0 ] || return 0
  local file
  for file in "${ENV_FILES[@]+"${ENV_FILES[@]}"}"; do
    if git ls-files --error-unmatch "$file" >/dev/null 2>&1 && grep -q "$PROJECT_REF" "$file"; then
      fail "refusing to write database password into Git-tracked dotenv file: ${file}"
    fi
  done
  PROJECT_REF="$PROJECT_REF" NEW_PASSWORD="$NEW_PASSWORD" node - "${ENV_FILES[@]+"${ENV_FILES[@]}"}" <<'NODE'
const fs = require("fs");
const files = process.argv.slice(2);
const ref = process.env.PROJECT_REF;
const pw = encodeURIComponent(process.env.NEW_PASSWORD);
const escapedRef = ref.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = [
  new RegExp(`(postgres(?:ql)?:\\/\\/postgres\\.${escapedRef}:)([^@\\s"']+)(@)`, "g"),
  new RegExp(`(postgres(?:ql)?:\\/\\/postgres:)([^@\\s"']+)(@db\\.${escapedRef}\\.supabase\\.co)`, "g"),
];
let changed = 0;
for (const file of files) {
  if (!fs.existsSync(file)) continue;
  let text = fs.readFileSync(file, "utf8");
  let next = text;
  for (const pattern of patterns) {
    next = next.replace(pattern, `$1${pw}$3`);
  }
  if (next !== text) {
    fs.writeFileSync(file, next);
    changed += 1;
    console.log(`updated ${file}`);
  }
}
if (changed === 0) {
  console.log("no local dotenv files needed changes");
}
NODE
}

update_github_secret() {
  printf '%s' "$DATABASE_URL_NEW" | gh secret set "$GITHUB_SECRET_NAME" --repo "$GITHUB_REPO" >/dev/null
  note "GitHub Actions secret updated: ${GITHUB_REPO}/${GITHUB_SECRET_NAME}"
}

vercel_env_add() {
  local name="$1"
  local target="$2"
  local value="$3"
  local out
  out="$(mktemp "/tmp/theseus-vercel-${name}-${target}.XXXXXX.log")"
  TMP_FILES+=("$out")

  npx --yes vercel@latest env rm "$name" "$target" --yes >"$out" 2>&1 || true
  if [ "$target" = "preview" ]; then
    printf '%s' "$value" | npx --yes vercel@latest env add "$name" preview "" --force --yes >>"$out" 2>&1
  else
    printf '%s' "$value" | npx --yes vercel@latest env add "$name" "$target" --force --yes >>"$out" 2>&1
  fi
  sed -E 's#postgresql://[^[:space:]]+#postgresql://<redacted>#g; s#[A-Za-z0-9_=-]{40,}#<redacted>#g' "$out"
}

update_vercel_envs() {
  local target
  for target in $VERCEL_TARGETS; do
    vercel_env_add DATABASE_URL "$target" "$DATABASE_URL_NEW"
    vercel_env_add DIRECT_URL "$target" "$DIRECT_URL_NEW"
  done
}

latest_production_deployment_url() {
  local listing
  listing="$(mktemp /tmp/theseus-vercel-list.XXXXXX.json)"
  TMP_FILES+=("$listing")
  npx --yes vercel@latest ls --status READY --format json >"$listing"
  node - "$listing" <<'NODE'
const fs = require("fs");
const file = process.argv[2];
const s = fs.readFileSync(file, "utf8");
const jsonStart = s.indexOf("{");
const parsed = JSON.parse(jsonStart >= 0 ? s.slice(jsonStart) : s);
const deployment = parsed.deployments.find((d) => d.target === "production");
if (!deployment) process.exit(1);
process.stdout.write(deployment.url);
NODE
}

redeploy_vercel() {
  local url
  url="$(latest_production_deployment_url)"
  [ -n "$url" ] || fail "could not determine latest production Vercel deployment"
  npx --yes vercel@latest redeploy "$url" --target production
}

refresh_currents_backend() {
  if [ "$DO_CURRENTS_BACKEND_REFRESH" -eq 0 ]; then
    return 0
  fi
  if [ -z "$CURRENTS_BACKEND_REFRESH_CMD" ]; then
    note "No CURRENTS_BACKEND_REFRESH_CMD set; external Currents API/scheduler refresh skipped."
    return 0
  fi
  note "Refreshing external Currents API/scheduler credentials..."
  export DATABASE_URL_NEW
  export DIRECT_URL_NEW
  export SUPABASE_PROJECT_REF="$PROJECT_REF"
  export THESEUS_DB_PASSWORD_NEW="$NEW_PASSWORD"
  bash -lc "$CURRENTS_BACKEND_REFRESH_CMD"
  note "Currents backend refresh command completed."
}

verify_database() {
  if ! command -v psql >/dev/null 2>&1; then
    note "psql not found; skipping connection verification."
    return 0
  fi
  local url="${DIRECT_URL_NEW%%\?*}"
  if [ -z "$url" ]; then
    url="${DATABASE_URL_NEW%%\?*}"
  fi
  note "Waiting before psql verification to avoid Supabase auth-rate-limit false negatives..."
  sleep 20
  local attempt out err
  for attempt in 1 2 3 4 5 6; do
    out="$(mktemp /tmp/theseus-psql-out.XXXXXX)"
    err="$(mktemp /tmp/theseus-psql-err.XXXXXX)"
    TMP_FILES+=("$out" "$err")
    if psql "$url" -qAt -c 'select current_user' >"$out" 2>"$err"; then
      printf 'psql verification succeeded as user %s\n' "$(cat "$out")"
      return 0
    fi
    if grep -qi 'ECIRCUITBREAKER\\|too many authentication failures' "$err"; then
      printf 'psql attempt %s hit Supabase auth circuit breaker; waiting...\n' "$attempt"
      sleep 30
      continue
    fi
    sed -E 's#postgresql://[^[:space:]]+#postgresql://<redacted>#g; s#[A-Za-z0-9_=-]{40,}#<redacted>#g' "$err" >&2
    fail "psql verification failed"
  done
  fail "psql verification could not complete before Supabase circuit breaker cleared"
}

if [ "$DO_SUPABASE" -eq 1 ]; then
  reset_supabase_password
fi
if [ "$DO_LOCAL_ENV" -eq 1 ]; then
  update_local_env_files
fi
if [ "$DO_GITHUB" -eq 1 ]; then
  update_github_secret
fi
if [ "$DO_VERCEL" -eq 1 ]; then
  update_vercel_envs
fi
if [ "$DO_REDEPLOY" -eq 1 ]; then
  redeploy_vercel
fi
refresh_currents_backend
if [ "$DO_VERIFY" -eq 1 ]; then
  verify_database
fi

note "Supabase DB password rotation complete."
