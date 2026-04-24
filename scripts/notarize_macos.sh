#!/usr/bin/env bash
# Usage: ./scripts/notarize_macos.sh <path-to-dmg-or-zip> <apple-id> <team-id> <app-specific-password>
# If credentials are missing, exits 0 with a warning.
set -euo pipefail

ARTIFACT="${1:-}"
APPLE_ID="${2:-}"
TEAM_ID="${3:-}"
APP_PASSWORD="${4:-}"

if [[ -z "$ARTIFACT" ]]; then
  echo "Usage: $0 <path-to-dmg-or-zip> <apple-id> <team-id> <app-specific-password>" >&2
  exit 1
fi

if [[ -z "$APPLE_ID" || -z "$TEAM_ID" || -z "$APP_PASSWORD" ]]; then
  echo "⚠ Notarization credentials not provided — skipping."
  exit 0
fi

if [[ ! -e "$ARTIFACT" ]]; then
  echo "Error: artifact $ARTIFACT does not exist." >&2
  exit 1
fi

echo "=== Submitting $ARTIFACT for notarization ==="
xcrun notarytool submit "$ARTIFACT" \
  --apple-id "$APPLE_ID" \
  --team-id "$TEAM_ID" \
  --password "$APP_PASSWORD" \
  --wait --timeout 600

echo "=== Stapling notarization ticket ==="
xcrun stapler staple "$ARTIFACT"

echo "=== Notarization complete ==="
