#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Generating icons ==="
node scripts/generate_icons.js
echo "=== Building Next.js ==="
npm run build
echo "=== Compiling Electron TypeScript ==="
npx tsc -p desktop/tsconfig.json
echo "=== Building macOS distribution ==="
npx electron-builder --mac --config electron-builder.yml
echo "=== Done: check dist-electron/ ==="
