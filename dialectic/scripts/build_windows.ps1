$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

Write-Host "=== Generating icons ===" -ForegroundColor Cyan
python scripts\generate_icons.py

Write-Host "=== Installing build dependencies ===" -ForegroundColor Cyan
pip install pyinstaller

Write-Host "=== Running PyInstaller ===" -ForegroundColor Cyan
pyinstaller dialectic.spec --noconfirm --clean

if (-not (Test-Path "dist\Dialectic\Dialectic.exe")) {
    Write-Error "PyInstaller build did not produce dist\Dialectic\Dialectic.exe"
    exit 1
}

$Version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

Write-Host "=== Building NSIS installer ===" -ForegroundColor Cyan
$makensis = Get-Command makensis -ErrorAction SilentlyContinue
if (-not $makensis) {
    $candidates = @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $makensis = $c; break }
    }
}
if ($makensis) {
    & $makensis "installer\dialectic.nsi"
    if (Test-Path "dist\Dialectic-Setup.exe") {
        Write-Host "=== Installer created: dist\Dialectic-Setup.exe ===" -ForegroundColor Green
    } else {
        Write-Warning "makensis ran but dist\Dialectic-Setup.exe was not produced."
    }
} else {
    Write-Warning "NSIS not found; skipping installer. Raw PyInstaller build is still in dist\Dialectic\"
}

Write-Host "=== Build complete: dist\Dialectic\ (version $Version) ===" -ForegroundColor Green
