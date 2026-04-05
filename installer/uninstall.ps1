#Requires -RunAsAdministrator
<#
.SYNOPSIS
    PostMule uninstaller for Windows 11.

.PARAMETER InstallDir
    Installation directory to remove. Default: C:\ProgramData\PostMule

.PARAMETER KeepData
    If specified, JSON data files and credentials.enc are NOT deleted.

.EXAMPLE
    .\uninstall.ps1
    .\uninstall.ps1 -InstallDir "D:\PostMule" -KeepData
#>
param(
    [string]$InstallDir = "C:\ProgramData\PostMule",
    [switch]$KeepData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TASK_NAME = "PostMule Daily Run"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    NOTE: $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------------
# Confirm
# ------------------------------------------------------------------
Write-Host ""
Write-Host "PostMule Uninstaller" -ForegroundColor Yellow
Write-Host ("=" * 40) -ForegroundColor Yellow
Write-Host ""
Write-Host "  Install dir : $InstallDir"
Write-Host "  Keep data   : $KeepData"
Write-Host ""

$confirm = Read-Host "Type YES to uninstall PostMule"
if ($confirm -ne "YES") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# ------------------------------------------------------------------
# 1. Remove scheduled task
# ------------------------------------------------------------------
Write-Step "Removing scheduled task '$TASK_NAME'..."
if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
    Write-OK "Task removed."
} else {
    Write-Warn "Task '$TASK_NAME' not found - skipping."
}

# ------------------------------------------------------------------
# 2. Remove PATH entry
# ------------------------------------------------------------------
Write-Step "Removing PATH entry..."
$scriptsDir = "$InstallDir\.venv\Scripts"
$userPath   = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -like "*$scriptsDir*") {
    $newPath = ($userPath -split ";" | Where-Object { $_ -ne $scriptsDir }) -join ";"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-OK "Removed '$scriptsDir' from user PATH."
} else {
    Write-Warn "PATH entry not found - skipping."
}

# ------------------------------------------------------------------
# 3. Remove install directory (optionally preserving data)
# ------------------------------------------------------------------
Write-Step "Removing install directory..."
if (-not (Test-Path $InstallDir)) {
    Write-Warn "Directory '$InstallDir' not found - skipping."
} elseif ($KeepData) {
    # Delete everything except the data folder and credentials.enc
    $dataDir = "$InstallDir\data"
    $encFile = "$InstallDir\credentials.enc"
    Get-ChildItem $InstallDir | ForEach-Object {
        $path = $_.FullName
        if ($path -eq $dataDir -or $path -eq $encFile) {
            Write-Warn "Keeping: $path"
        } else {
            Remove-Item -Path $path -Recurse -Force
        }
    }
    Write-OK "Install directory cleaned (data and credentials.enc kept at $InstallDir)."
} else {
    Remove-Item -Path $InstallDir -Recurse -Force
    Write-OK "Removed '$InstallDir'."
}

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 40) -ForegroundColor Green
Write-Host "PostMule uninstalled." -ForegroundColor Green
Write-Host ("=" * 40) -ForegroundColor Green
if ($KeepData) {
    Write-Host ""
    Write-Host "Your data files are still at: $InstallDir\data" -ForegroundColor Yellow
    Write-Host "Your encrypted credentials are at: $InstallDir\credentials.enc" -ForegroundColor Yellow
}
