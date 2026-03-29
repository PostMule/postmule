# CLI Install Guide

For advanced users who prefer the command line. If you want a guided setup wizard, use the [Windows installer](https://github.com/PostMule/app/releases) instead.

## Quickest path — setup script

After cloning the repo, run:

```powershell
.\setup.ps1
```

This handles Steps 1–2 and 4–5 below automatically (interactive prompts for email, API key, and master password). For a fully silent install:

```powershell
.\setup.ps1 `
  -AlertEmail you@example.com `
  -GeminiApiKey AIzaSy... `
  -VpmSender noreply@virtualpostmail.com `
  -MasterPassword "your master password" `
  -NoTaskScheduler
```

The manual steps below are for reference or if you prefer to run each step yourself.

## Requirements

- Python 3.12+ on Windows 11 (macOS/Linux may work with minor adjustments)
- A virtual mailbox service (VirtualPostMail, Earth Class Mail, Traveling Mailbox, PostScan)
- A Gmail account (or other supported provider) to receive mailbox notifications
- A Google account for Drive + Sheets storage (or configure an alternative)
- An API key for a supported LLM (default: Gemini 1.5 Flash — free tier)

## Step 1 — Clone and install

```powershell
git clone https://github.com/PostMule/app.git PostMule
cd PostMule
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Step 2 — Create config files

```powershell
copy config.example.yaml config.yaml
copy credentials.example.yaml credentials.yaml
```

Both files are in `.gitignore` and will never be committed. Edit `config.yaml` to set your `alert_email` and virtual mailbox provider. Edit `credentials.yaml` to add your Google OAuth credentials and Gemini API key.

See [Configuration Reference](configuration.md) for all available fields.

## Step 3 — Set up Google OAuth

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project
2. Enable the **Google Drive API** and **Google Sheets API**
3. Create an OAuth 2.0 Client ID (Desktop app type)
4. Download the JSON file and save it as `credentials.json` in the PostMule directory
5. On first run, PostMule will open a browser for OAuth consent — approve access

## Step 4 — Encrypt credentials

```powershell
postmule set-master-password
postmule encrypt-credentials
```

Your master password is stored in the Windows system keyring (DPAPI). After encrypting, you can delete `credentials.yaml`.

## Step 5 — Test and schedule

```powershell
# Test with a dry run (no writes, no emails)
postmule --dry-run

# Schedule the daily run (time set in config.yaml → schedule.run_time)
postmule install-task

# Run immediately
postmule run
```

## First-Run Checklist

- `postmule --dry-run` completes without errors
- Dashboard loads at [localhost:5000](http://localhost:5000)
- Storage folders created in Google Drive under "PostMule"
- Test email received at your `alert_email`
- Task Scheduler task visible in Windows Task Scheduler
