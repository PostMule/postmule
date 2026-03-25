# PostMule — Configuration Reference

All configuration lives in `config.yaml` (created from `config.example.yaml`). This file is in `.gitignore` and never committed. Sensitive secrets belong in `credentials.yaml`, not here.

---

## `app`

Top-level application settings.

| Field | Default | Description |
|---|---|---|
| `name` | `PostMule` | Application name (used in logs and notifications) |
| `version` | `"0.1.0"` | Version string |
| `install_dir` | `C:\ProgramData\PostMule` | Local directory for logs and local data cache |
| `dry_run` | `false` | `true` = simulate all actions; no writes, moves, or emails sent. Safe for testing. |

---

## `schedule`

When the daily pipeline runs. Changes here are written to Windows Task Scheduler on save.

| Field | Default | Description |
|---|---|---|
| `run_time` | `"02:00"` | Time of day in 24h format (local time) |
| `timezone` | `"America/Los_Angeles"` | IANA timezone name |

---

## `logging`

| Field | Default | Description |
|---|---|---|
| `verbose_days` | `7` | Rolling days of verbose logs to keep |
| `processing_years` | `3` | Years of annual processing logs to keep |
| `level` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## `notifications`

| Field | Default | Description |
|---|---|---|
| `providers` | `[{type: email, enabled: true}]` | List of notification providers |
| `alert_email` | `""` | **Required.** Email address to receive daily summaries and alerts |
| `forward_to_me_urgent` | `true` | Send immediate alert when ForwardToMe mail is detected (not just daily summary) |
| `bill_due_alert_days` | `7` | Send proactive alert when a bill is due within this many days |

---

## `mailbox`

Physical mail provider configuration.

| Field | Default | Description |
|---|---|---|
| `providers[].service` | `vpm` | Provider: `vpm`, `earth_class`, `traveling_mailbox`, `postscan` |
| `providers[].enabled` | `true` | Enable/disable this provider |
| `providers[].scan_sender` | `noreply@virtualpostmail.com` | Email address that sends scan notifications |
| `providers[].scan_subject_prefix` | `[Scan Request]` | Subject prefix that identifies scan notification emails |

---

## `email`

Email account(s) for ingestion. Supports multiple accounts with different roles.

| Field | Description |
|---|---|
| `providers[].service` | `gmail`, `outlook_com`, `outlook_365`, `proton`, `imap` |
| `providers[].enabled` | Enable/disable this account |
| `providers[].role` | `mailbox_notifications` (receives VPM alerts) or `bill_intake` (receives biller PDFs) |
| `providers[].address` | Email address of the account |
| `providers[].label` | Gmail label applied to processed emails |

---

## `storage`

Cloud file storage for PDFs and JSON data.

| Field | Default | Description |
|---|---|---|
| `providers[].service` | `google_drive` | `google_drive`, `s3`, `dropbox`, `onedrive` |
| `providers[].root_folder` | `PostMule` | Top-level folder name in the storage provider |
| `providers[].folders.*` | see example | Sub-folder names (inbox, bills, notices, etc.) — change only if needed |

---

## `spreadsheet`

The spreadsheet is a **generated view** — rebuilt from JSON on each run. Never edit it directly.

| Field | Default | Description |
|---|---|---|
| `providers[].service` | `google_sheets` | `google_sheets`, `excel_online`, `none` |
| `providers[].workbook_name` | `PostMule` | Name of the workbook/spreadsheet |
| `providers[].sheets` | see example | List of sheet tabs to generate |

---

## `llm`

LLM provider for classification and field extraction.

| Field | Default | Description |
|---|---|---|
| `providers[].service` | `gemini` | `gemini`, `openai`, `anthropic`, `ollama` |
| `providers[].model` | `gemini-1.5-flash` | Model name (provider-specific) |
| `classification_confidence_threshold` | `0.80` | Below this confidence score → file goes to NeedsReview |

---

## `api_safety`

Hard limits to prevent runaway LLM costs. Applied to the active provider.

| Field | Default | Description |
|---|---|---|
| `daily_request_limit` | `1400` | Hard stop on API requests per day (default matches Gemini free tier) |
| `daily_token_limit` | `900000` | Hard stop on tokens per day |
| `warn_at_percent` | `80` | Warn in logs when this % of any limit is reached |
| `monthly_cost_budget_usd` | `0.00` | Stop if projected monthly cost exceeds this; `0` = free tier only |

---

## `classification`

| Field | Default | Description |
|---|---|---|
| `categories` | see example | List of classification categories (do not remove or rename) |
| `forward_to_me_keywords` | see example | Keywords that always trigger ForwardToMe classification, regardless of LLM output |

---

## `entities`

| Field | Default | Description |
|---|---|---|
| `known_names` | `[]` | Seed names for entity discovery (optional) |
| `fuzzy_match_threshold` | `0.85` | Similarity score (0–1) to propose an alias match |
| `auto_approve_after_days` | `7` | Auto-approve pending matches after this many days without human action |

---

## `finance`

| Field | Default | Description |
|---|---|---|
| `providers[].service` | — | `ynab`, `plaid`, `simplifi`, `monarch` |
| `providers[].enabled` | `false` | Enable/disable this provider |
| `bill_matching.require_manual_approval` | `true` | Require human approval for each bill/transaction match |
| `bill_matching.amount_tolerance_cents` | `0` | Allow matches within this many cents (0 = exact) |

---

## `data_protection`

| Field | Default | Description |
|---|---|---|
| `soft_deletes_only` | `true` | Never permanently delete files automatically (do not change) |
| `trash_retention_days` | `90` | Days before trash items are flagged for manual review |
| `max_files_moved_per_run` | `50` | Safety cap — pipeline stops and alerts if this is exceeded |
| `write_verification` | `true` | Read back + hash every write to cloud storage (3-layer redundancy) |

---

## `backups`

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable encrypted daily backups of JSON data |
| `retain_days` | `180` | Days of backups to retain (6 months default) |
| `destination` | `google_drive` | Storage provider to write backups to |

---

## `integrity`

| Field | Default | Description |
|---|---|---|
| `run_monitor` | `true` | Alert if a daily run is missed |
| `gap_detector.enabled` | `true` | Weekly scan for gaps in mail processing history |
| `gap_detector.run_day` | `sunday` | Day of week for gap scan |
| `integrity_verifier.enabled` | `true` | Weekly storage consistency verification |
| `duplicate_detector.enabled` | `true` | Daily duplicate file detection |

---

## `deployment`

| Field | Default | Description |
|---|---|---|
| `dashboard_port` | `5000` | Port for the local web dashboard |
| `tailscale_enabled` | `false` | `true` = dashboard accessible via Tailscale on your network |
| `task_scheduler_task_name` | `PostMule Daily Run` | Name of the Windows Task Scheduler task |
