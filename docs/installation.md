# PostMule — Installation Guide

## Requirements

- **Python 3.12+** (Windows 11 primary target; macOS/Linux may work with minor adjustments)
- A **virtual mailbox service** (VirtualPostMail, Earth Class Mail, Traveling Mailbox, PostScan)
- A **Gmail account** (or other supported email provider) to receive mailbox notifications
- A **Google account** for Google Drive + Sheets storage (or configure an alternative)
- An API key for a **supported LLM** (default: Gemini 1.5 Flash, free tier)

---

## Step 1 — Clone and install

```powershell
git clone https://github.com/PostMule/app.git PostMule
cd PostMule
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Verify the install:
```powershell
postmule --version
```

---

## Step 2 — Create config files

Copy the example templates:
```powershell
copy config.example.yaml config.yaml
copy credentials.example.yaml credentials.yaml
```

`config.yaml` is in `.gitignore` — it will never be committed. `credentials.yaml` contains placeholder keys and is also never committed; your actual secrets go into it locally and are then encrypted.

---

## Step 3 — Configure `config.yaml`

Open `config.yaml` and set at minimum:

```yaml
notifications:
  alert_email: "your@email.com"   # Where daily summaries and alerts are sent

email:
  providers:
    - service: gmail
      address: "your-postmule-gmail@gmail.com"  # Gmail account that receives VPM notifications

mailbox:
  providers:
    - service: vpm               # Or: earth_class, traveling_mailbox, postscan
```

Everything else has working defaults. See [configuration.md](configuration.md) for all options.

---

## Step 4 — Set up Google OAuth (Drive + Sheets)

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project (e.g. "PostMule").
3. Enable the **Google Drive API** and **Google Sheets API**.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**.
5. Application type: **Desktop app**.
6. Download the JSON file and save it as `credentials.json` in the PostMule directory.
7. On first run, PostMule will open a browser window for OAuth consent. Approve access.

---

## Step 5 — Get a Gemini API key

1. Go to [aistudio.google.com](https://aistudio.google.com).
2. Click **Get API key**.
3. Copy the key.

---

## Step 6 — Fill in `credentials.yaml`

Open `credentials.yaml` and fill in your secrets:

```yaml
google:
  oauth_client_id: "..."          # From the credentials.json you downloaded
  oauth_client_secret: "..."
  gemini_api_key: "..."           # From AI Studio
```

See `credentials.example.yaml` for the full list of fields.

---

## Step 7 — Encrypt credentials

PostMule stores credentials encrypted at rest using Fernet symmetric encryption. The master password is stored in your system keyring (Windows DPAPI).

Set your master password (only done once):
```powershell
postmule set-master-password
```

Encrypt the credentials file:
```powershell
postmule encrypt-credentials
```

This creates `credentials.enc`. You can now delete `credentials.yaml` — PostMule will decrypt on startup.

---

## Step 8 — Test with a dry run

```powershell
postmule --dry-run
```

This runs the full pipeline but makes no writes, sends no emails, and moves no files. Check the log output for any configuration errors.

---

## Step 9 — Schedule the daily run

PostMule runs on Windows Task Scheduler. Register the daily task:

```powershell
postmule install-task
```

This creates a task named "PostMule Daily Run" that runs at 2:00 AM Pacific (configurable in `config.yaml` → `schedule`).

To run immediately:
```powershell
postmule run
```

---

## Step 10 — Open the dashboard

Start the web dashboard:
```powershell
postmule dashboard
```

Open [http://localhost:5000](http://localhost:5000) in your browser. The default login is configured in `config.yaml` → `app`.

---

## First-Run Checklist

- [ ] `postmule --dry-run` completes without errors
- [ ] Dashboard loads at localhost:5000
- [ ] Storage folders created in Google Drive under "PostMule"
- [ ] Test email received at `alert_email`
- [ ] Task Scheduler task visible in Windows Task Scheduler
- [ ] (Optional) Finance provider configured and pulling transactions

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'postmule'`**
→ Make sure you activated the venv: `.venv\Scripts\activate`

**Google OAuth error on first run**
→ Make sure you enabled both the Drive API and Sheets API in Google Cloud Console.

**No PDFs downloaded from VPM**
→ Check that `email.providers[0].address` matches the Gmail account that receives VPM notifications, and that IMAP is enabled in Gmail settings.

**LLM quota exceeded**
→ Check `api_safety.daily_request_limit` — it defaults to 1,400 to stay under Gemini's 1,500/day free tier.
