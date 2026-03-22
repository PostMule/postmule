#Requires -RunAsAdministrator
<#
.SYNOPSIS
    PostMule installer for Windows 11.

.PARAMETER InstallDir
    Installation directory. Default: C:\ProgramData\PostMule

.PARAMETER ConfigUrl
    Optional URL to download a pre-filled config.yaml from.

.PARAMETER CredentialsUrl
    Optional URL to download a pre-filled credentials.enc from.

.EXAMPLE
    .\install.ps1
    .\install.ps1 -InstallDir "D:\PostMule"
#>
param(
    [string]$InstallDir = "C:\ProgramData\PostMule",
    [string]$ConfigUrl = "",
    [string]$CredentialsUrl = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/PostMule/postmule/archive/refs/heads/main.zip"
$TASK_NAME  = "PostMule Daily Run"
$TASK_TIME  = "02:00"
$MIN_PYTHON = [version]"3.11"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    NOTE: $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "    FAIL: $msg" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------
# 1. Check Python
# ------------------------------------------------------------------
Write-Step "Checking Python..."
$pythonExe = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+\.\d+)") {
            $found = [version]$Matches[1]
            if ($found -ge $MIN_PYTHON) {
                $pythonExe = (Get-Command $candidate).Source
                Write-OK "Found $ver at $pythonExe"
                break
            }
        }
    } catch {}
}
if (-not $pythonExe) {
    Write-Fail "Python $MIN_PYTHON or newer is required. Install from https://python.org and re-run."
}

# ------------------------------------------------------------------
# 2. Create install directory
# ------------------------------------------------------------------
Write-Step "Creating install directory: $InstallDir"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path "$InstallDir\logs\verbose" -Force | Out-Null
New-Item -ItemType Directory -Path "$InstallDir\logs\processing" -Force | Out-Null
Write-OK "Directories created."

# ------------------------------------------------------------------
# 3. Download and extract PostMule
# ------------------------------------------------------------------
Write-Step "Downloading PostMule..."
$zipPath     = "$env:TEMP\postmule.zip"
$extractPath = "$env:TEMP\postmule-extract"

Invoke-WebRequest -Uri $REPO_URL -OutFile $zipPath -UseBasicParsing
Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

$sourceDir = Get-ChildItem $extractPath | Select-Object -First 1
Copy-Item -Path "$($sourceDir.FullName)\*" -Destination $InstallDir -Recurse -Force
Write-OK "PostMule extracted to $InstallDir"

# ------------------------------------------------------------------
# 4. Create virtual environment and install dependencies
# ------------------------------------------------------------------
Write-Step "Creating Python virtual environment..."
& $pythonExe -m venv "$InstallDir\.venv"
$pip = "$InstallDir\.venv\Scripts\pip.exe"
& $pip install --upgrade pip --quiet
& $pip install -e "$InstallDir" --quiet
Write-OK "Dependencies installed."

# ------------------------------------------------------------------
# 5. Copy or download config files
# ------------------------------------------------------------------
Write-Step "Setting up config files..."
$configDest = "$InstallDir\config.yaml"
$encDest    = "$InstallDir\credentials.enc"

if ($ConfigUrl) {
    Invoke-WebRequest -Uri $ConfigUrl -OutFile $configDest -UseBasicParsing
    Write-OK "config.yaml downloaded."
} elseif (-not (Test-Path $configDest)) {
    Copy-Item "$InstallDir\config.example.yaml" $configDest
    Write-Warn "Edit $configDest before first run."
}

if ($CredentialsUrl) {
    Invoke-WebRequest -Uri $CredentialsUrl -OutFile $encDest -UseBasicParsing
    Write-OK "credentials.enc downloaded."
} else {
    Write-Warn "Run 'vpm encrypt-credentials' to set up credentials."
}

# ------------------------------------------------------------------
# 6. Register Windows Task Scheduler task
# ------------------------------------------------------------------
Write-Step "Registering Windows Task Scheduler task..."
$vpmExe  = "$InstallDir\.venv\Scripts\vpm.exe"
$action  = New-ScheduledTaskAction -Execute $vpmExe -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -Daily -At $TASK_TIME
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable

if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Description "PostMule daily mail processing run" | Out-Null

Write-OK "Task '$TASK_NAME' scheduled daily at $TASK_TIME."

# ------------------------------------------------------------------
# 7. Add vpm to PATH for current user
# ------------------------------------------------------------------
Write-Step "Adding vpm to user PATH..."
$scriptsDir = "$InstallDir\.venv\Scripts"
$userPath   = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$scriptsDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$scriptsDir", "User")
    Write-OK "Added $scriptsDir to PATH. Restart your terminal to use 'vpm'."
} else {
    Write-OK "Already in PATH."
}

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "PostMule installed successfully!" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host @"

Next steps:
  1. Edit config:       notepad "$configDest"
  2. Set credentials:   vpm set-master-password
                        vpm encrypt-credentials
  3. Test run:          vpm --dry-run
  4. Full run:          vpm

The daily task runs automatically at $TASK_TIME.
"@
