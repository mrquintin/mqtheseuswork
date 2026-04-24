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
pyinstaller noosphere.spec --noconfirm --clean

if [ ! -d "dist/noosphere" ]; then
  echo "Error: dist/noosphere not found. PyInstaller build may have failed." >&2
  exit 1
fi

echo "=== Code signing ==="
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-skip}"
bash "$ROOT/../scripts/codesign_macos.sh" "dist/noosphere" "$SIGNING_IDENTITY"

echo "=== Creating distributable archive ==="
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
ARCHIVE="noosphere-${VERSION}-macos.tar.gz"
(cd dist && tar -czf "$ARCHIVE" noosphere/)

# Apple's notarytool only accepts .dmg, .pkg, or .zip — wrap the signed
# directory in a ZIP for notarization. The tar.gz remains the user-facing
# distribution; the notarization ticket is stapled to the ZIP.
NOTARIZE_ZIP="noosphere-${VERSION}-macos.zip"
(cd dist && /usr/bin/ditto -c -k --keepParent noosphere "$NOTARIZE_ZIP")

echo "=== Notarization ==="
bash "$ROOT/../scripts/notarize_macos.sh" "dist/$NOTARIZE_ZIP" \
  "${APPLE_ID:-}" "${APPLE_TEAM_ID:-}" "${APPLE_APP_PASSWORD:-}"

echo "=== Build complete: dist/$ARCHIVE ==="
echo "Users can extract and add the noosphere directory to their PATH, or"
echo "symlink dist/noosphere/noosphere into /usr/local/bin."
