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
  -ImapHost imap.gmail.com `
  -ImapUsername your@gmail.com `
  -ImapPassword "your-app-password" `
  -GeminiApiKey AIzaSy... `
  -MasterPassword "your master password" `
  -NoTaskScheduler
```

The manual steps below are for reference or if you prefer to run each step yourself.

## Requirements

- Python 3.12+ on Windows 11 (macOS/Linux may work with minor adjustments)
- A virtual mailbox service (VirtualPostMail, Earth Class Mail, Traveling Mailbox, PostScan)
- An email account accessible via IMAP (Gmail, Outlook, or any IMAP server)
  - Gmail users: generate an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- An API key for a supported LLM (default: Gemini 1.5 Flash — free tier)

**No Google Cloud Console setup required.** PostMule defaults to local file storage and IMAP email — no OAuth, no Drive API, no Sheets API. Google integrations are available as opt-in providers if you want cloud storage.

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

Both files are in `.gitignore` and will never be committed.

Edit `config.yaml`:
- Set `notifications.alert_email` to where you want alerts sent
- Set `email.providers[0].address` and `.host` for your IMAP account
- Set `mailbox.providers[0].service` to your virtual mailbox provider

Edit `credentials.yaml`:
- Set `accounts.main.username` and `.password` (your IMAP login / app password)
- Set `gemini.api_key` (get one free at [aistudio.google.com](https://aistudio.google.com))

See [Configuration Reference](configuration.md) for all available fields.

## Step 3 — Encrypt credentials

```powershell
postmule set-master-password
postmule encrypt-credentials
```

Your master password is stored in the Windows system keyring (DPAPI). After encrypting, you can delete `credentials.yaml`.

## Step 4 — Test and schedule

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
- Storage folders created at `C:\ProgramData\PostMule\files\` (or your configured `root_dir`)
- Test email received at your `alert_email`
- Task Scheduler task visible in Windows Task Scheduler

## Optional: Google Cloud setup

If you want Google Drive storage or Google Sheets view instead of local defaults:

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project
2. Enable the **Google Drive API** and/or **Google Sheets API**
3. Create an OAuth 2.0 Client ID (Desktop app type)
4. Run `postmule connect-google` to complete the OAuth consent flow
5. In `config.yaml`, change `storage.providers[0].service` to `google_drive` and/or `spreadsheet.providers[0].service` to `google_sheets`
