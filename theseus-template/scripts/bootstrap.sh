#!/usr/bin/env bash
# Theseus template — per-tenant bootstrap wizard.
#
# Interactive setup that:
#   1. Asks the new tenant for the bare-minimum config it needs.
#   2. Writes a .env.live from .env.live.template.
#   3. Runs prisma migrate deploy + alembic upgrade.
#   4. Seeds one Organization + one admin Founder (zero conclusions /
#      zero principles — the tenant fills those in via the platform).
#   5. Prints next steps including pointers to the user guides.
#
# Re-run safely: existing .env.live is left in place unless --force.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORCE=0
NONINTERACTIVE=0
PRESET=""
PRESET_PARTNERS=""  # comma-separated; used in non-interactive mode
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1 ;;
    --non-interactive) NONINTERACTIVE=1 ;;
    --preset=*) PRESET="${1#--preset=}" ;;
    --preset)
      shift
      PRESET="${1:-}"
      [[ -z "$PRESET" ]] && { echo "--preset requires a value" >&2; exit 2; }
      ;;
    --partners=*) PRESET_PARTNERS="${1#--partners=}" ;;
    --partners)
      shift
      PRESET_PARTNERS="${1:-}"
      ;;
    -h|--help)
      sed -n '2,15p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf "\n\033[1;36m%s\033[0m\n" "$*"; }
ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    printf "%s" "$default"
    return
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " answer || true
    printf "%s" "${answer:-$default}"
  else
    read -r -p "$prompt: " answer
    printf "%s" "$answer"
  fi
}
ask_yes_no() {
  local prompt="$1"
  local default="${2:-N}"
  local answer
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    [[ "$default" == "Y" ]] && echo "true" || echo "false"
    return
  fi
  while true; do
    read -r -p "$prompt [y/N]: " answer || true
    answer="${answer:-$default}"
    case "$answer" in
      [yY]|[yY][eE][sS]) echo "true"; return ;;
      [nN]|[nN][oO]|"") echo "false"; return ;;
      *) echo "Please answer y or n." >&2 ;;
    esac
  done
}

say "Theseus tenant bootstrap"
echo "This wizard configures a fresh tenant installation. You can re-run it later."

if [[ -f .env.live && "$FORCE" -ne 1 ]]; then
  echo
  echo ".env.live already exists. Pass --force to overwrite it."
  echo "Continuing anyway (migrations + seed only)."
  SKIP_ENV=1
else
  SKIP_ENV=0
fi

if [[ "$SKIP_ENV" -eq 0 ]]; then
  ORG_NAME=$(ask "Organisation display name" "Example Capital")
  ORG_SLUG=$(ask "Organisation slug (URL-safe)" "example-capital")
  ADMIN_EMAIL=$(ask "Primary admin email" "admin@example.invalid")
  ADMIN_PASSWORD=$(ask "Primary admin password (will be hashed)" "change-me-immediately")
  DATABASE_URL=$(ask "Postgres DATABASE_URL" "postgresql://postgres:postgres@localhost:5432/${ORG_SLUG//-/_}")

  echo
  echo "LLM provider:"
  echo "  1) Anthropic"
  echo "  2) OpenAI"
  echo "  3) Both"
  PROVIDER_CHOICE=$(ask "Choose 1/2/3" "1")
  ANTHROPIC_KEY=""
  OPENAI_KEY=""
  case "$PROVIDER_CHOICE" in
    1|3) ANTHROPIC_KEY=$(ask "Anthropic API key" "") ;;
  esac
  case "$PROVIDER_CHOICE" in
    2|3) OPENAI_KEY=$(ask "OpenAI API key" "") ;;
  esac

  # Preset-driven module defaults. The vc_firm preset hard-disables
  # forecasts + equities; we still let an explicit operator answer
  # override, but the default flips to "no" and the prompt notes the
  # preset's opinion. Without a preset the prompts behave as before.
  PRESET_FORECASTS_DEFAULT="N"
  PRESET_EQUITIES_DEFAULT="N"
  PRESET_ORACLE="true"
  PRESET_CURRENTS="true"
  PRESET_PRINCIPLES="true"
  PRESET_DEALS="false"
  PRESET_PRIMARY="/dashboard"
  PRESET_ADJACENT=""
  PRESET_HIDDEN=""
  PRESET_DOMAINS=""
  if [[ -n "$PRESET" ]]; then
    PRESET_FILE="$ROOT/presets/${PRESET}.yml"
    if [[ ! -f "$PRESET_FILE" ]]; then
      echo "preset '${PRESET}' not found at $PRESET_FILE" >&2
      exit 2
    fi
    SCHEMA_FILE="$ROOT/presets/schema/preset.schema.json"
    PRESET_VARS=$(PRESET_FILE="$PRESET_FILE" SCHEMA_FILE="$SCHEMA_FILE" python3 - <<'PY'
import json, os, sys
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required to use --preset. pip install pyyaml.", file=sys.stderr)
    sys.exit(2)
try:
    import jsonschema  # noqa: F401
    _have_jsonschema = True
except ImportError:
    _have_jsonschema = False

with open(os.environ["PRESET_FILE"]) as fh:
    data = yaml.safe_load(fh) or {}
with open(os.environ["SCHEMA_FILE"]) as fh:
    schema = json.load(fh)
if _have_jsonschema:
    import jsonschema
    jsonschema.validate(data, schema)
modules = data.get("modules", {}) or {}
ds = data.get("decision_surface", {}) or {}
def b(name, default):
    return "true" if bool(modules.get(name, default)) else "false"
print("PRESET_FORECASTS_DEFAULT=" + ("Y" if modules.get("forecasts") else "N"))
print("PRESET_EQUITIES_DEFAULT=" + ("Y" if modules.get("equities") else "N"))
print("PRESET_ORACLE=" + b("oracle", True))
print("PRESET_CURRENTS=" + b("currents", True))
print("PRESET_PRINCIPLES=" + b("principles", True))
print("PRESET_DEALS=" + b("deals", False))
print("PRESET_PRIMARY=" + (ds.get("primary") or "/dashboard"))
print("PRESET_ADJACENT=" + ",".join(ds.get("adjacent") or []))
print("PRESET_HIDDEN=" + ",".join(ds.get("hidden") or []))
print("PRESET_DOMAINS=" + ",".join(data.get("default_principle_domains") or []))
print("PRESET_NAME=" + (data.get("name") or ""))
# seed_artifact paths + READMEs are emitted as a JSON blob for the
# subsequent seed step (parsed in Python again — round-tripping JSON
# through bash is the safest cross-platform option).
artifacts = data.get("seed_artifacts") or []
print("PRESET_ARTIFACTS_JSON=" + json.dumps(artifacts))
PY
)
    if [[ $? -ne 0 ]]; then
      echo "preset validation failed" >&2
      exit 2
    fi
    eval "$PRESET_VARS"
    echo "[bootstrap] preset '${PRESET_NAME}' loaded from $PRESET_FILE"
  fi

  FORECASTS_ENABLED=$(ask_yes_no "Enable Forecasts module? (default: no, requires gated rehearsal)" "$PRESET_FORECASTS_DEFAULT")
  EQUITIES_ENABLED=$(ask_yes_no "Enable Equities module? (default: no, requires gated rehearsal)" "$PRESET_EQUITIES_DEFAULT")

  if [[ ! -f .env.live.template ]]; then
    echo "error: .env.live.template missing — this is not a valid template tree." >&2
    exit 2
  fi

  cp .env.live.template .env.live
  # Substitute the values the wizard collected. We use python so we get
  # robust escaping; sed-on-secrets is a recipe for footguns.
  ORG_NAME="$ORG_NAME" ORG_SLUG="$ORG_SLUG" ADMIN_EMAIL="$ADMIN_EMAIL" \
  DATABASE_URL="$DATABASE_URL" ANTHROPIC_KEY="$ANTHROPIC_KEY" OPENAI_KEY="$OPENAI_KEY" \
  FORECASTS_ENABLED="$FORECASTS_ENABLED" EQUITIES_ENABLED="$EQUITIES_ENABLED" \
  PRESET="$PRESET" PRESET_ORACLE="$PRESET_ORACLE" PRESET_CURRENTS="$PRESET_CURRENTS" \
  PRESET_PRINCIPLES="$PRESET_PRINCIPLES" PRESET_DEALS="$PRESET_DEALS" \
  PRESET_PRIMARY="$PRESET_PRIMARY" PRESET_ADJACENT="$PRESET_ADJACENT" \
  PRESET_HIDDEN="$PRESET_HIDDEN" PRESET_DOMAINS="$PRESET_DOMAINS" \
  python3 - <<'PY'
import os, re, pathlib
p = pathlib.Path(".env.live")
text = p.read_text()
def setline(key, value):
    global text
    if value is None:
        return
    pattern = re.compile(rf"^{re.escape(key)}=.*$", flags=re.MULTILINE)
    repl = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(repl, text)
    else:
        text += f"\n{repl}\n"

setline("DATABASE_URL", os.environ["DATABASE_URL"])
setline("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_KEY", ""))
setline("OPENAI_API_KEY", os.environ.get("OPENAI_KEY", ""))
setline("THESEUS_ORG_NAME", os.environ["ORG_NAME"])
setline("THESEUS_ORG_SLUG", os.environ["ORG_SLUG"])
setline("THESEUS_NOTIFY_FROM", f"notify@{os.environ['ORG_SLUG']}.local")
setline("FOUNDER_ALPHA_EMAIL", os.environ["ADMIN_EMAIL"])
setline("SEED_FOUNDER_A_EMAIL", os.environ["ADMIN_EMAIL"])
setline("SEED_FOUNDER_A_NAME", os.environ["ORG_NAME"] + " Admin")
setline("FORECASTS_LIVE_TRADING_ENABLED", "false")  # eight-gate contract: stays off
setline("EQUITIES_LIVE_TRADING_ENABLED", "false")
setline("FORECASTS_MODULE_ENABLED", os.environ["FORECASTS_ENABLED"])
setline("EQUITIES_MODULE_ENABLED", os.environ["EQUITIES_ENABLED"])
preset = os.environ.get("PRESET", "")
if preset:
    setline("THESEUS_PRESET", preset)
    setline("ORACLE_MODULE_ENABLED", os.environ.get("PRESET_ORACLE", "true"))
    setline("CURRENTS_MODULE_ENABLED", os.environ.get("PRESET_CURRENTS", "true"))
    setline("PRINCIPLES_MODULE_ENABLED", os.environ.get("PRESET_PRINCIPLES", "true"))
    setline("DEALS_MODULE_ENABLED", os.environ.get("PRESET_DEALS", "false"))
    setline("THESEUS_DECISION_PRIMARY", os.environ.get("PRESET_PRIMARY", "/dashboard"))
    setline("THESEUS_DECISION_ADJACENT", os.environ.get("PRESET_ADJACENT", ""))
    setline("THESEUS_DECISION_HIDDEN", os.environ.get("PRESET_HIDDEN", ""))
    setline("THESEUS_DEFAULT_PRINCIPLE_DOMAINS", os.environ.get("PRESET_DOMAINS", ""))
p.write_text(text)
print("[bootstrap] wrote .env.live")
PY

  chmod 600 .env.live || true
  echo "[bootstrap] .env.live written (mode 600)."
else
  ORG_NAME="${THESEUS_ORG_NAME:-}"
  ORG_SLUG="${THESEUS_ORG_SLUG:-}"
  ADMIN_EMAIL="${SEED_FOUNDER_A_EMAIL:-}"
  ADMIN_PASSWORD="${SEED_FOUNDER_A_PASSWORD:-change-me-immediately}"
fi

# Load env for the migration + seed steps.
set -a
# shellcheck disable=SC1091
[[ -f .env.live ]] && source .env.live
set +a

say "Running migrations"
if [[ -d theseus-codex ]]; then
  (cd theseus-codex && npx --yes prisma migrate deploy)
else
  echo "[bootstrap] theseus-codex/ missing — skipping prisma migrate."
fi

if [[ -f noosphere/alembic.ini ]]; then
  (cd noosphere && alembic upgrade head)
else
  echo "[bootstrap] noosphere/alembic.ini missing — skipping alembic upgrade."
fi

say "Seeding initial tenant"
# Seed: one Organization + one admin Founder. Zero conclusions, zero
# principles — explicitly NOT setting SEED_WITH_MOCK_DATA.
if [[ -d theseus-codex ]]; then
  (
    cd theseus-codex
    SEED_FOUNDER_A_EMAIL="${ADMIN_EMAIL}" \
    SEED_FOUNDER_A_PASSWORD="${ADMIN_PASSWORD:-change-me-immediately}" \
    SEED_FOUNDER_A_NAME="${ORG_NAME} Admin" \
    SEED_FOUNDER_B_EMAIL="${ADMIN_EMAIL}" \
    SEED_FOUNDER_B_PASSWORD="${ADMIN_PASSWORD:-change-me-immediately}" \
    npx --yes tsx prisma/seed.ts
  )
fi

if [[ -n "$PRESET" ]]; then
  say "Applying preset onboarding (${PRESET})"
  TENANT_DATA_DIR="${TENANT_DATA_DIR:-tenant_data/${ORG_SLUG}}"
  mkdir -p "$TENANT_DATA_DIR"

  # Materialise seed_artifacts: empty directories + README per artifact.
  PRESET_FILE="$ROOT/presets/${PRESET}.yml" \
  TENANT_DATA_DIR="$TENANT_DATA_DIR" \
  python3 - <<'PY'
import os, sys, pathlib
try:
    import yaml
except ImportError:
    print("PyYAML required for preset onboarding; skipping seed_artifacts.", file=sys.stderr)
    sys.exit(0)
data = yaml.safe_load(pathlib.Path(os.environ["PRESET_FILE"]).read_text()) or {}
root = pathlib.Path(os.environ["TENANT_DATA_DIR"])
for art in data.get("seed_artifacts") or []:
    path = root / art["path"]
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(art["readme"])
        print(f"[bootstrap] created {path}/ + README")
PY

  # Preset-specific onboarding: vc_firm asks for partner names and
  # creates founders/<slug>/ folders. Other presets fall through.
  if [[ "$PRESET" == "vc_firm" ]]; then
    PARTNERS_LIST=()
    if [[ "$NONINTERACTIVE" -eq 1 ]]; then
      if [[ -n "$PRESET_PARTNERS" ]]; then
        IFS=',' read -ra PARTNERS_LIST <<< "$PRESET_PARTNERS"
      fi
    else
      echo
      echo "Founding partners — enter one name per prompt; blank line to stop."
      i=1
      while true; do
        partner=$(ask "Founding partner #${i} name (blank to stop)" "")
        [[ -z "$partner" ]] && break
        PARTNERS_LIST+=("$partner")
        i=$((i + 1))
      done
    fi
    for partner in "${PARTNERS_LIST[@]}"; do
      slug=$(printf '%s' "$partner" | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
      partner_dir="$TENANT_DATA_DIR/founders/${slug}"
      mkdir -p "$partner_dir/essays" "$partner_dir/transcripts"
      cat > "$partner_dir/README.md" <<EOR
# ${partner}

Drop ${partner}'s long-form writing under ./essays/ (PDF, markdown,
.txt) and podcast / interview transcripts under ./transcripts/ (plain
text or .srt). The principle extractor runs over both subfolders and
tags emitted claims against the firm's default principle domains
(see THESEUS_DEFAULT_PRINCIPLE_DOMAINS in .env.live).
EOR
      echo "[bootstrap] founder dir ready: $partner_dir"
    done
    if [[ "$NONINTERACTIVE" -ne 1 && ${#PARTNERS_LIST[@]} -gt 0 ]]; then
      echo
      echo "Drop initial materials into the founder folders above, then"
      echo "press <enter> to run the principle extractor + distillation pass."
      read -r _ || true
    fi

    if [[ -f noosphere/pyproject.toml || -d noosphere ]]; then
      # The extractor is idempotent — re-running over the same folders
      # de-dupes claims by content hash. We invoke it here so the
      # operator sees the principle queue populated after the wizard
      # finishes; subsequent uploads can be processed via the CLI.
      ( cd noosphere \
        && python -m noosphere.cli principles extract \
             --root "../${TENANT_DATA_DIR}/founders" \
             --org-slug "$ORG_SLUG" \
             --domains "$THESEUS_DEFAULT_PRINCIPLE_DOMAINS" \
             || echo "[bootstrap] principle extraction step skipped/failed (run later via the CLI)" )
      ( cd noosphere \
        && python -m noosphere.cli principles distill \
             --org-slug "$ORG_SLUG" \
             || echo "[bootstrap] principle distillation step skipped/failed (run later via the CLI)" )
    fi
  fi
fi

say "Bootstrap complete."
cat <<EOM

Next steps:
  1. Read docs/guides/01_Theseus_Quick_Start.pdf for the platform tour.
  2. Read docs/guides/02_Knowledge_and_Principles.pdf for how to feed your
     firm's intellectual capital into the system.
  3. ${PRESET:+(Preset: ${PRESET}) See docs/presets/${PRESET}.md for the
     intended workflow.}
  4. The Forecasts and Equities modules are OFF by default. Re-run with
     --force after completing the operator rehearsal in
     docs/operator/SCHEDULER_OPS.md before enabling either.
  4. Eight-gate safety contract stays in force. Read docs/security/Threat_Model.md.

Admin login:
  email: ${ADMIN_EMAIL}
  password: (the one you entered — change it on first login)
EOM
