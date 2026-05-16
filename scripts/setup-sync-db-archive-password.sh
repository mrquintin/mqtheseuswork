#!/bin/bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SERVICE="${SYNC_DB_PASSWORD_KEYCHAIN_SERVICE:-theseus-sync-db-password-archive}"
ACCOUNT="${SYNC_DB_PASSWORD_KEYCHAIN_ACCOUNT:-mqtheseuswork}"
RESET=0

usage() {
  cat <<EOF
Usage: $0 [--reset]

Stores the Sync to GitHub DB password recovery-archive password in macOS
Keychain. This is the password used to encrypt local recovery archives, not the
Supabase database password itself.

Options:
  --reset    Delete any existing Keychain item first, then prompt for a new one.

Environment:
  SYNC_DB_PASSWORD_KEYCHAIN_SERVICE   default: theseus-sync-db-password-archive
  SYNC_DB_PASSWORD_KEYCHAIN_ACCOUNT   default: mqtheseuswork
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --reset)
      RESET=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v security >/dev/null 2>&1; then
  echo "ERROR: this setup script requires macOS Keychain's 'security' command." >&2
  echo "Fallback: run sync with SYNC_DB_PASSWORD_ARCHIVE_PROMPT=1 in a fully interactive terminal." >&2
  exit 1
fi

prompt_with_osascript() {
  osascript <<'APPLESCRIPT'
set firstAnswer to text returned of (display dialog "Choose the Theseus Sync recovery-archive password. This encrypts the local DB-password recovery archive; it is not the Supabase DB password." default answer "" with hidden answer buttons {"Cancel", "Continue"} default button "Continue")
set secondAnswer to text returned of (display dialog "Verify the Theseus Sync recovery-archive password." default answer "" with hidden answer buttons {"Cancel", "Save"} default button "Save")
if firstAnswer is "" then error "Archive password cannot be empty." number 1001
if firstAnswer is not secondAnswer then error "Archive passwords did not match." number 1002
return firstAnswer
APPLESCRIPT
}

prompt_with_terminal() {
  local first second
  if [ ! -r /dev/tty ]; then
    echo "ERROR: no interactive terminal is available for password setup." >&2
    return 1
  fi
  printf "Choose Theseus Sync recovery-archive password: " >/dev/tty
  IFS= read -r -s first </dev/tty
  echo "" >/dev/tty
  printf "Verify Theseus Sync recovery-archive password: " >/dev/tty
  IFS= read -r -s second </dev/tty
  echo "" >/dev/tty
  if [ -z "$first" ]; then
    echo "ERROR: archive password cannot be empty." >&2
    return 1
  fi
  if [ "$first" != "$second" ]; then
    echo "ERROR: archive passwords did not match." >&2
    return 1
  fi
  printf '%s' "$first"
}

if [ "$RESET" = "1" ]; then
  security delete-generic-password -a "$ACCOUNT" -s "$SERVICE" >/dev/null 2>&1 || true
fi

password=""
if command -v osascript >/dev/null 2>&1; then
  if ! password="$(prompt_with_osascript)"; then
    echo "ERROR: password setup was cancelled or failed." >&2
    exit 1
  fi
else
  if ! password="$(prompt_with_terminal)"; then
    echo "ERROR: password setup failed." >&2
    exit 1
  fi
fi

security add-generic-password \
  -a "$ACCOUNT" \
  -s "$SERVICE" \
  -w "$password" \
  -U >/dev/null

unset password

echo "Stored Theseus Sync recovery-archive password in macOS Keychain."
echo "Service: $SERVICE"
echo "Account: $ACCOUNT"
echo ""
echo "Now rerun:"
echo "  ./scripts/sync-to-github.sh"
