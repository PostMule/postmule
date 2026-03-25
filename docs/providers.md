# PostMule — Provider Guide

Every external service in PostMule is abstracted behind a provider interface. You can swap any provider with a single line in `config.yaml` — no code changes required.

Provider interfaces live in `postmule/providers/*/base.py`. Concrete implementations are alongside their base class.

---

## Email

Monitors one or more email accounts. Two roles:
- **`mailbox_notifications`** — receives scan notification emails from your virtual mailbox provider.
- **`bill_intake`** — receives biller-sent PDF attachments directly (e.g. AT&T emails your bill as a PDF).

Both roles feed the same downstream OCR → classification pipeline.

| Provider | `service` value | Setup notes |
|---|---|---|
| **Gmail** (default) | `gmail` | Enable IMAP in Gmail settings; use an App Password if 2FA is on |
| Outlook.com | `outlook_com` | Enable IMAP; use App Password |
| Microsoft 365 | `outlook_365` | Enable IMAP; configure OAuth or App Password |
| Proton Mail | `proton` | Requires Proton Mail Bridge running locally |
| Any IMAP server | `imap` | Set `host`, `port`, `username`, `password` in credentials |

**Recommendation:** Gmail is the easiest to set up and most reliable for this use case.

---

## Physical Mail (Virtual Mailbox)

PostMule supports any virtual mailbox provider that sends scan notification emails. The mailbox agent monitors your email inbox for these notifications and downloads the PDFs.

| Provider | `service` value | Notes |
|---|---|---|
| **VirtualPostMail** (default) | `vpm` | Sends notifications from `noreply@virtualpostmail.com` |
| Earth Class Mail | `earth_class` | Configure `scan_sender` and `scan_subject_prefix` |
| Traveling Mailbox | `traveling_mailbox` | Configure `scan_sender` and `scan_subject_prefix` |
| PostScan Mail | `postscan` | Configure `scan_sender` and `scan_subject_prefix` |

To use a provider not listed, set the `scan_sender` and `scan_subject_prefix` fields to match that provider's notification emails.

---

## Storage

Stores PDFs and JSON data files. Cloud storage is intentional: files survive local PC failure and PostMule can be reinstalled on any machine and immediately pick up where it left off.

| Provider | `service` value | Setup notes |
|---|---|---|
| **Google Drive** (default) | `google_drive` | Create OAuth credentials in Google Cloud Console; download `credentials.json` |
| Amazon S3 | `s3` | Create an IAM user with S3 permissions; set `access_key_id` and `secret_access_key` in credentials |
| Dropbox | `dropbox` | Create a Dropbox app; set `access_token` in credentials |
| OneDrive | `onedrive` | Register an Azure app; set OAuth credentials |

**Recommendation:** Google Drive pairs naturally with Google Sheets (the default spreadsheet provider) and has a generous free tier (15GB).

---

## Spreadsheet

The spreadsheet is a **generated view** — it is rebuilt from JSON on demand. Never edit it directly; changes will be overwritten on the next run.

| Provider | `service` value | Notes |
|---|---|---|
| **Google Sheets** (default) | `google_sheets` | Uses the same OAuth credentials as Google Drive |
| Excel Online | `excel_online` | Requires Microsoft 365 subscription |
| None | `none` | Disables the spreadsheet view entirely |

**Recommendation:** Google Sheets is free and integrates seamlessly with Google Drive.

---

## AI / LLM

Used for document classification (Bill / Notice / ForwardToMe / Personal / Junk), field extraction (sender, amount, due date), entity enrichment, and alias matching.

| Provider | `service` value | Model | Cost |
|---|---|---|---|
| **Gemini** (default) | `gemini` | `gemini-1.5-flash` | Free tier: 1,500 req/day |
| OpenAI | `openai` | `gpt-4o-mini` (recommended) | Pay per token |
| Anthropic | `anthropic` | `claude-haiku-4-5` (recommended) | Pay per token |
| Ollama (local) | `ollama` | Any local model | Free; requires local GPU |

The `api_safety` config section enforces hard limits on daily requests and tokens to prevent runaway costs. The default limits match Gemini's free tier.

**Recommendation:** Gemini 1.5 Flash is the best starting point — free tier covers typical household mail volumes easily.

---

## Finance

Pulls bank transactions for bill reconciliation. Bill matching requires: exact dollar amount + statement date. Company name is deliberately excluded (finance providers normalize transaction names inconsistently).

| Provider | `service` value | API type | Cost |
|---|---|---|---|
| **YNAB** | `ynab` | Official REST API | Free Personal Access Token |
| Plaid | `plaid` | Official REST API | Free development tier (up to 100 institutions) |
| Simplifi by Quicken | `simplifi` | Browser automation | Requires Simplifi subscription (EXPERIMENTAL) |
| Monarch Money | `monarch` | Browser automation | Requires Monarch subscription (EXPERIMENTAL) |

**YNAB setup:**
1. Go to app.ynab.com → Account Settings → Developer Settings.
2. Create a Personal Access Token.
3. Add the token to `credentials.yaml` under `ynab.personal_access_token`.

**Plaid setup:**
1. Register at dashboard.plaid.com (free developer account).
2. Run Plaid Link once per bank to obtain an `access_token`.
3. Add `client_id`, `secret`, and `access_token` to `credentials.yaml`.

**Note:** Simplifi and Monarch use browser automation and may break when those apps update their UI. Use only if neither YNAB nor Plaid is an option.

---

## Notifications

Sends the daily summary email and urgent alerts.

| Provider | `service` value | Notes |
|---|---|---|
| **Email** (default) | `email` | Uses the configured email provider (Gmail, etc.) |

Additional notification providers (Slack, SMS, webhook) are planned for a future release.
