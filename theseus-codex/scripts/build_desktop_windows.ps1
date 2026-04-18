$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "=== Generating icons ===" -ForegroundColor Cyan
node scripts\generate_icons.js
Write-Host "=== Building Next.js ===" -ForegroundColor Cyan
npm run build
Write-Host "=== Compiling Electron TypeScript ===" -ForegroundColor Cyan
npx tsc -p desktop\tsconfig.json
Write-Host "=== Building Windows distribution ===" -ForegroundColor Cyan
npx electron-builder --win --config electron-builder.yml
Write-Host "=== Done: check dist-electron\ ===" -ForegroundColor Green
