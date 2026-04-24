$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

Write-Host "=== Generating icons ===" -ForegroundColor Cyan
python scripts\generate_icons.py

Write-Host "=== Installing build dependencies ===" -ForegroundColor Cyan
pip install pyinstaller

Write-Host "=== Running PyInstaller ===" -ForegroundColor Cyan
pyinstaller noosphere.spec --noconfirm --clean

if (-not (Test-Path "dist\noosphere\noosphere.exe")) {
    Write-Error "PyInstaller build did not produce dist\noosphere\noosphere.exe"
    exit 1
}

$Version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

Write-Host "=== Building NSIS installer ===" -ForegroundColor Cyan
$makensis = Get-Command makensis -ErrorAction SilentlyContinue
$nsisRoot = $null
if (-not $makensis) {
    $candidates = @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $makensis = $c; $nsisRoot = Split-Path -Parent $c; break }
    }
} else {
    $nsisRoot = Split-Path -Parent $makensis.Source
}

# Install EnVar plugin (required by noosphere.nsi for PATH manipulation).
# The plugin is a small DLL dropped into the NSIS Plugins directory.
if ($nsisRoot -and -not (Test-Path "$nsisRoot\Plugins\x86-unicode\EnVar.dll")) {
    Write-Host "=== Installing EnVar NSIS plugin ===" -ForegroundColor Cyan
    $tmpZip = "$env:TEMP\EnVar_plugin.zip"
    $tmpDir = "$env:TEMP\EnVar_plugin"
    try {
        Invoke-WebRequest -Uri "https://nsis.sourceforge.io/mediawiki/images/7/7f/EnVar_plugin.zip" -OutFile $tmpZip -UseBasicParsing
        if (Test-Path $tmpDir) { Remove-Item -Recurse -Force $tmpDir }
        Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force
        foreach ($sub in @("x86-unicode","x86-ansi","amd64-unicode")) {
            $src = Join-Path $tmpDir "Plugins\$sub\EnVar.dll"
            $dst = Join-Path $nsisRoot "Plugins\$sub"
            if (Test-Path $src) {
                if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }
                Copy-Item -Force $src (Join-Path $dst "EnVar.dll")
            }
        }
        Write-Host "EnVar plugin installed." -ForegroundColor Green
    } catch {
        Write-Warning "Could not install EnVar plugin: $_"
    }
}

if ($makensis) {
    & $makensis "installer\noosphere.nsi"
    if (Test-Path "dist\Noosphere-Setup.exe") {
        Write-Host "=== Installer created: dist\Noosphere-Setup.exe ===" -ForegroundColor Green
    } else {
        Write-Warning "makensis ran but dist\Noosphere-Setup.exe was not produced."
    }
} else {
    Write-Warning "NSIS not found; skipping installer. Raw PyInstaller build is still in dist\noosphere\"
}

Write-Host "=== Build complete: dist\noosphere\ (version $Version) ===" -ForegroundColor Green
