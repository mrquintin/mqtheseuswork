# Usage: .\scripts\codesign_windows.ps1 -Target <exe-or-dir> -CertPath <pfx-path> -CertPassword <pw>
# If no certificate is provided, exits 0 with a warning.
param(
  [Parameter(Mandatory=$true)] [string]$Target,
  [string]$CertPath = "",
  [string]$CertPassword = ""
)

$ErrorActionPreference = "Stop"

if (-not $CertPath -or -not (Test-Path $CertPath)) {
  Write-Host "⚠ No certificate provided — skipping code signing." -ForegroundColor Yellow
  exit 0
}

if (-not (Test-Path $Target)) {
  Write-Host "Error: target $Target does not exist." -ForegroundColor Red
  exit 1
}

$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\*\bin\*\x64\signtool.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $signtool) {
  Write-Host "⚠ signtool.exe not found — skipping." -ForegroundColor Yellow
  exit 0
}

# Find all .exe and .dll files (recursive if Target is a directory; single file if Target is one).
if ((Get-Item $Target).PSIsContainer) {
  $files = Get-ChildItem -Path $Target -Recurse -Include *.exe,*.dll
} else {
  $files = @(Get-Item $Target)
}

foreach ($file in $files) {
  Write-Host "Signing $($file.FullName)..."
  & $signtool.FullName sign /f $CertPath /p $CertPassword /tr http://timestamp.digicert.com /td sha256 /fd sha256 $file.FullName
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: signtool failed for $($file.FullName)" -ForegroundColor Red
    exit $LASTEXITCODE
  }
}

Write-Host "=== Windows signing complete ===" -ForegroundColor Green
