<#
.SYNOPSIS
    PostMule CLI setup script - interactive or fully scripted.

.DESCRIPTION
    Sets up PostMule from a cloned repo. Run with no arguments for an interactive
    walkthrough, or pass flags for a fully silent install (CI/automation).

.PARAMETER AlertEmail
    Email address for daily summaries and alerts.

.PARAMETER GeminiApiKey
    Gemini API key. Get one at: https://aistudio.google.com/app/api-keys

.PARAMETER VpmSender
    Scan notification sender address from your virtual mailbox provider.
    Default for VirtualPostMail: noreply@virtualpostmail.com

.PARAMETER MasterPassword
    Master password for encrypting credentials. If omitted in non-interactive
    mode, you will be prompted once; set POSTMULE_MASTER_PASSWORD env var to
    avoid the prompt entirely.

.PARAMETER NoTaskScheduler
    Skip registering the Windows Task Scheduler entry.

.PARAMETER DryRunOnly
    Run `postmule --dry-run` at the end but skip the Task Scheduler step.
    Implies -NoTaskScheduler.

.EXAMPLE
    # Interactive install (recommended for first-time setup)
    .\setup.ps1

.EXAMPLE
    # Silent install (CI / automation)
    .\setup.ps1 `
        -AlertEmail you@example.com `
        -GeminiApiKey AIzaSy... `
        -VpmSender noreply@virtualpostmail.com `
        -MasterPassword "correct horse battery staple" `
        -NoTaskScheduler
#>

param(
    [string]$AlertEmail      = "",
    [string]$GeminiApiKey    = "",
    [string]$VpmSender       = "",
    [string]$MasterPassword  = "",
    [switch]$NoTaskScheduler,
    [switch]$DryRunOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$MIN_PYTHON  = [version]"3.12"
$TASK_NAME   = "PostMule Daily Run"
$TASK_TIME   = "02:00"
$ROOT        = $PSScriptRoot
$VENV        = Join-Path $ROOT ".venv"
$POSTMULE    = Join-Path $VENV "Scripts\postmule.exe"
$PYTHON_VENV = Join-Path $VENV "Scripts\python.exe"
$SILENT      = ($AlertEmail -or $GeminiApiKey -or $MasterPassword -or $NoTaskScheduler -or $DryRunOnly)

if ($DryRunOnly) { $NoTaskScheduler = $true }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)    { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "    NOTE: $msg" -ForegroundColor Yellow }
function Write-Fail($msg)  { Write-Host "`n  FAIL: $msg`n" -ForegroundColor Red; exit 1 }

function Prompt-Or-Default([string]$prompt, [string]$default, [bool]$isSecret = $false) {
    if ($default) { return $default }
    if ($isSecret) {
        $secure = Read-Host $prompt -AsSecureString
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    return (Read-Host $prompt).Trim()
}

function Set-YamlValue([string]$file, [string]$pattern, [string]$replacement) {
    $content = Get-Content $file -Raw
    $updated = $content -replace $pattern, $replacement
    if ($updated -eq $content) {
        Write-Warn "Pattern not matched in $file - value may already be set or file format changed."
    } else {
        Set-Content -Path $file -Value $updated -NoNewline
    }
}

# ---------------------------------------------------------------------------
# 1. Check Python 3.12+
# ---------------------------------------------------------------------------
Write-Step "Checking Python $MIN_PYTHON+..."
$pythonExe = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+\.\d+)") {
            $found = [version]$Matches[1]
            if ($found -ge $MIN_PYTHON) {
                $pythonExe = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
                Write-OK "Found $ver"
                break
            }
        }
    } catch {}
}
if (-not $pythonExe) {
    Write-Fail @"
Python $MIN_PYTHON or newer is required but was not found.

  1. Download and run the installer from: https://python.org/downloads
  2. On the first screen, check "Add Python to PATH"
  3. Re-run this script

If Python is already installed, make sure it is on your PATH:
  Open a new terminal and run: python --version
"@
}

# ---------------------------------------------------------------------------
# 2. Check git
# ---------------------------------------------------------------------------
Write-Step "Checking git..."
try {
    $gitVer = & git --version 2>&1
    Write-OK $gitVer
} catch {
    Write-Fail @"
git is required but was not found.

  Download and install from: https://git-scm.com/downloads
  During install, accept the default "Add Git to PATH" option.

Note: git is only used to download PostMule. Once set up, you do not need it
for day-to-day operation.
"@
}

# ---------------------------------------------------------------------------
# 3. Create virtual environment
# ---------------------------------------------------------------------------
Write-Step "Creating Python virtual environment..."
if (Test-Path $VENV) {
    Write-OK "Virtual environment already exists at $VENV"
} else {
    & $pythonExe -m venv $VENV
    Write-OK "Created $VENV"
}

# ---------------------------------------------------------------------------
# 4. Install PostMule
# ---------------------------------------------------------------------------
Write-Step "Installing PostMule and dependencies..."
$pip = Join-Path $VENV "Scripts\pip.exe"
& $pip install --upgrade pip --quiet
& $pip install -e $ROOT --quiet
Write-OK "postmule installed"

# ---------------------------------------------------------------------------
# 5. Copy config files
# ---------------------------------------------------------------------------
Write-Step "Setting up config files..."
$configPath      = Join-Path $ROOT "config.yaml"
$credentialsPath = Join-Path $ROOT "credentials.yaml"

if (-not (Test-Path $configPath)) {
    Copy-Item (Join-Path $ROOT "config.example.yaml") $configPath
    Write-OK "Created config.yaml from template"
} else {
    Write-OK "config.yaml already exists - skipping copy"
}

if (-not (Test-Path $credentialsPath)) {
    Copy-Item (Join-Path $ROOT "credentials.example.yaml") $credentialsPath
    Write-OK "Created credentials.yaml from template"
} else {
    Write-OK "credentials.yaml already exists - skipping copy"
}

# ---------------------------------------------------------------------------
# 6. Prompt for minimum config values
# ---------------------------------------------------------------------------
Write-Step "Configuring PostMule..."

if (-not $SILENT) {
    Write-Host ""
    Write-Host "  PostMule needs a few values to get started." -ForegroundColor White
    Write-Host "  Press Enter to skip any field (you can fill it in later)." -ForegroundColor DarkGray
    Write-Host ""
}

# alert_email
if (-not $AlertEmail) {
    $AlertEmail = (Read-Host "  Alert email (where to send daily summaries and alerts)").Trim()
}
if ($AlertEmail) {
    Set-YamlValue $configPath 'alert_email: ""' "alert_email: `"$AlertEmail`""
    Write-OK "alert_email set"
} else {
    Write-Warn "alert_email not set - fill in config.yaml before your first real run"
}

# scan notification sender
if (-not $VpmSender) {
    Write-Host ""
    Write-Host "  Scan notification sender: the From address on emails your virtual" -ForegroundColor DarkGray
    Write-Host "  mailbox sends when new mail arrives." -ForegroundColor DarkGray
    Write-Host "  VirtualPostMail default: noreply@virtualpostmail.com" -ForegroundColor DarkGray
    $VpmSender = (Read-Host "  Scan sender [noreply@virtualpostmail.com]").Trim()
    if (-not $VpmSender) { $VpmSender = "noreply@virtualpostmail.com" }
}
Set-YamlValue $configPath 'scan_sender: "noreply@virtualpostmail.com"' "scan_sender: `"$VpmSender`""
Write-OK "scan_sender set to: $VpmSender"

# Gemini API key
if (-not $GeminiApiKey) {
    Write-Host ""
    Write-Host "  Gemini API key: PostMule uses Gemini 1.5 Flash (free tier) to classify mail." -ForegroundColor DarkGray
    Write-Host "  Get a free key at: https://aistudio.google.com/app/api-keys" -ForegroundColor DarkGray
    Write-Host "  (No credit card required for the free tier)" -ForegroundColor DarkGray
    $GeminiApiKey = (Read-Host "  Gemini API key").Trim()
}
if ($GeminiApiKey) {
    Set-YamlValue $credentialsPath '(gemini:\r?\n  api_key: )""' "`${1}`"$GeminiApiKey`""
    Write-OK "Gemini API key set"
} else {
    Write-Warn "Gemini API key not set - fill in credentials.yaml before your first real run"
}

# ---------------------------------------------------------------------------
# 7. Set master password + encrypt credentials
# ---------------------------------------------------------------------------
Write-Step "Encrypting credentials..."

# Resolve master password: parameter > env var > prompt
if (-not $MasterPassword) {
    $envPw = [Environment]::GetEnvironmentVariable("POSTMULE_MASTER_PASSWORD")
    if ($envPw) {
        $MasterPassword = $envPw
        Write-OK "Using master password from POSTMULE_MASTER_PASSWORD env var"
    }
}
if (-not $MasterPassword) {
    Write-Host ""
    Write-Host "  Choose a master password to encrypt your credentials." -ForegroundColor DarkGray
    Write-Host "  This is stored in the Windows Credential Manager (never on disk)." -ForegroundColor DarkGray
    $MasterPassword = Prompt-Or-Default "  Master password" "" $true
}

if ($MasterPassword) {
    # Invoke the Python functions directly so we can pass the password non-interactively.
    & $PYTHON_VENV -c @"
import sys
sys.path.insert(0, r'$ROOT')
from postmule.core.credentials import save_master_password, encrypt_credentials
from pathlib import Path
save_master_password('$MasterPassword')
encrypt_credentials(Path(r'$credentialsPath'), Path(r'$(Join-Path $ROOT "credentials.enc")'), '$MasterPassword')
"@
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Credential encryption failed. Check credentials.yaml for syntax errors."
    }
    Write-OK "Credentials encrypted to credentials.enc"
    Write-OK "Master password saved to Windows Credential Manager"
    Write-Warn "You can now delete credentials.yaml - credentials.enc is your encrypted copy"
} else {
    Write-Warn "Skipping encryption - run 'postmule set-master-password' and 'postmule encrypt-credentials' manually"
}

# ---------------------------------------------------------------------------
# 8. Register Windows Task Scheduler (unless skipped)
# ---------------------------------------------------------------------------
if (-not $NoTaskScheduler) {
    Write-Step "Registering Windows Task Scheduler task..."

    if (-not (Test-Path $POSTMULE)) {
        Write-Warn "postmule.exe not found at expected path - skipping Task Scheduler"
    } else {
        $action   = New-ScheduledTaskAction -Execute $POSTMULE -WorkingDirectory $ROOT
        $trigger  = New-ScheduledTaskTrigger -Daily -At $TASK_TIME
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
        Write-OK "Task '$TASK_NAME' scheduled daily at $TASK_TIME"
    }
}

# ---------------------------------------------------------------------------
# 9. Dry run
# ---------------------------------------------------------------------------
Write-Step "Running dry-run check..."
Write-Host "  (No files will be written, no emails sent)" -ForegroundColor DarkGray
& $POSTMULE --dry-run
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Dry run exited with errors. Review the output above before running for real."
} else {
    Write-OK "Dry run passed"
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host " PostMule setup complete" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host @"

Next steps:
  1. Set up Google OAuth (needed for Drive + Sheets):
     Follow the instructions at: docs/install-cli.md#step-3

  2. Start the dashboard:
     postmule serve
     Then open: http://localhost:5000

  3. Run PostMule now (live run):
     postmule run

The daily task runs automatically at $TASK_TIME.
$(if ($NoTaskScheduler) { "  (Task Scheduler was skipped - run 'postmule install-task' to register it later)" })
"@
