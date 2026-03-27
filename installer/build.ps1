# PostMule — Developer Build Script
# Builds PostMuleSetup.exe from source.
#
# Prerequisites (install once):
#   pip install pyinstaller
#   winget install JRSoftware.InnoSetup   (or download from jrsoftware.org)
#
# Usage:
#   .\installer\build.ps1                 # full build
#   .\installer\build.ps1 -SkipPyInstaller # Inno Setup only (faster iteration)

[CmdletBinding()]
param(
    [switch]$SkipPyInstaller,
    [string]$InnoSetupPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $RepoRoot

# ---------------------------------------------------------------------------
# 1. Locate Inno Setup compiler (ISCC.exe)
# ---------------------------------------------------------------------------
function Find-Iscc {
    param([string]$Hint)

    if ($Hint -and (Test-Path $Hint)) { return $Hint }

    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue)?.Source
    )

    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }

    throw "ISCC.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isdownload.php"
}

$Iscc = Find-Iscc -Hint $InnoSetupPath
Write-Host "Using ISCC: $Iscc" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 2. PyInstaller — bundle Python + PostMule into dist\postmule\
# ---------------------------------------------------------------------------
if (-not $SkipPyInstaller) {
    Write-Host ""
    Write-Host "=== PyInstaller: building postmule bundle ===" -ForegroundColor Cyan

    # Activate venv if present
    $VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
    if (Test-Path $VenvActivate) {
        . $VenvActivate
        Write-Host "Activated venv: $VenvActivate"
    }

    # Clean previous build artifacts
    Remove-Item -Recurse -Force "dist\postmule" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "build"         -ErrorAction SilentlyContinue

    # Run PyInstaller using the spec file (or generate one if absent)
    $SpecFile = Join-Path $RepoRoot "installer\postmule.spec"
    if (Test-Path $SpecFile) {
        pyinstaller $SpecFile --noconfirm
    } else {
        Write-Host "No postmule.spec found — generating with auto-detect..." -ForegroundColor Yellow
        pyinstaller `
            --name postmule `
            --onedir `
            --console `
            --clean `
            --noconfirm `
            --add-data "config.example.yaml;." `
            --add-data "postmule\web\templates;postmule\web\templates" `
            --add-data "postmule\web\static;postmule\web\static" `
            --hidden-import "postmule.providers.email.gmail" `
            --hidden-import "postmule.providers.email.outlook_365" `
            --hidden-import "postmule.providers.email.outlook_com" `
            --hidden-import "postmule.providers.storage.google_drive" `
            --hidden-import "postmule.providers.spreadsheet.google_sheets" `
            --hidden-import "postmule.providers.llm.gemini" `
            --hidden-import "postmule.providers.mailbox.vpm" `
            --hidden-import "flask" `
            --hidden-import "jinja2" `
            --hidden-import "keyring.backends.Windows" `
            "postmule\cli.py"
    }

    if (-not (Test-Path "dist\postmule\postmule.exe")) {
        throw "PyInstaller failed — dist\postmule\postmule.exe not found."
    }

    Write-Host "PyInstaller bundle ready: dist\postmule\" -ForegroundColor Green
} else {
    Write-Host "Skipping PyInstaller (using existing dist\postmule\)." -ForegroundColor Yellow
    if (-not (Test-Path "dist\postmule\postmule.exe")) {
        throw "dist\postmule\postmule.exe not found. Run without -SkipPyInstaller first."
    }
}

# ---------------------------------------------------------------------------
# 3. Inno Setup — compile the installer
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Inno Setup: compiling installer ===" -ForegroundColor Cyan

$IssFile = Join-Path $RepoRoot "installer\postmule.iss"
& $Iscc $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE."
}

# ---------------------------------------------------------------------------
# 4. Done
# ---------------------------------------------------------------------------
$Output = Join-Path $RepoRoot "dist\PostMuleSetup.exe"
if (Test-Path $Output) {
    $SizeMB = [math]::Round((Get-Item $Output).Length / 1MB, 1)
    Write-Host ""
    Write-Host "=== Build complete ===" -ForegroundColor Green
    Write-Host "Output: $Output ($SizeMB MB)" -ForegroundColor Green
} else {
    throw "Build succeeded but PostMuleSetup.exe not found at expected path: $Output"
}

Pop-Location
