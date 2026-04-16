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

Write-Host "=== Build complete: dist\Dialectic\ (version $Version) ===" -ForegroundColor Green
Write-Host "To create installer, install NSIS and run: makensis installer\dialectic.nsi"
