#!/usr/bin/env bash
# Usage: ./scripts/codesign_macos.sh <path-to-app-or-dir> <signing-identity>
# If signing identity is empty or "skip", signing is skipped gracefully.
set -euo pipefail

TARGET="${1:-}"
IDENTITY="${2:-skip}"

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 <path-to-app-or-dir> <signing-identity>" >&2
  exit 1
fi

if [[ "$IDENTITY" == "skip" || -z "$IDENTITY" ]]; then
  echo "⚠ No signing identity provided — skipping code signing."
  exit 0
fi

if [[ ! -e "$TARGET" ]]; then
  echo "Error: target $TARGET does not exist." >&2
  exit 1
fi

echo "=== Signing $TARGET with identity: $IDENTITY ==="

# Deep-sign all nested binaries first (required for notarization).
# -perm +111 is BSD syntax (macOS); use a portable approach.
find "$TARGET" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 \
  | xargs -0 -I {} codesign --force --options runtime --timestamp --sign "$IDENTITY" {}

# Also sign any executable files (Mach-O binaries).
find "$TARGET" -type f -perm -u+x ! -name "*.dylib" ! -name "*.so" -print0 2>/dev/null \
  | xargs -0 -I {} codesign --force --options runtime --timestamp --sign "$IDENTITY" {} || true

# Sign the top-level bundle or directory
codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$TARGET"

# Verify
codesign --verify --deep --strict "$TARGET"
echo "=== Signing complete ==="
