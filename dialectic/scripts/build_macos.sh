#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."
cd "$ROOT"

echo "=== Generating icons ==="
python3 scripts/generate_icons.py

echo "=== Installing build dependencies ==="
pip install pyinstaller

echo "=== Running PyInstaller ==="
pyinstaller dialectic.spec --noconfirm --clean

echo "=== Creating DMG ==="
APP_PATH="dist/Dialectic.app"
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
DMG_PATH="dist/Dialectic-${VERSION}.dmg"

if [ ! -d "$APP_PATH" ]; then
  echo "Error: $APP_PATH not found. PyInstaller build may have failed." >&2
  exit 1
fi

echo "=== Code signing ==="
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-skip}"
bash "$ROOT/../scripts/codesign_macos.sh" "$APP_PATH" "$SIGNING_IDENTITY"

if command -v create-dmg &>/dev/null; then
  create-dmg \
    --volname "Dialectic" \
    --volicon "assets/Dialectic.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "Dialectic.app" 150 190 \
    --app-drop-link 450 190 \
    --hide-extension "Dialectic.app" \
    "$DMG_PATH" "$APP_PATH"
else
  echo "create-dmg not found, falling back to hdiutil"
  hdiutil create \
    -volname "Dialectic" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"
fi

echo "=== Notarization ==="
bash "$ROOT/../scripts/notarize_macos.sh" "$DMG_PATH" \
  "${APPLE_ID:-}" "${APPLE_TEAM_ID:-}" "${APPLE_APP_PASSWORD:-}"

echo "=== Build complete: $DMG_PATH ==="
