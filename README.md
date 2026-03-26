# PostMule

> PostMule automatically sorts your physical mail and bills, tracks due dates, and matches payments to your bank — running privately on your own computer, with no subscription fee.

It replaces services like PayTrust and PayMyBills. Your documents stay in your own Google Drive. Nothing is sent to any third-party server.

---

## Get Started

### Option A — Windows Installer *(recommended)*

Download the latest installer from the [Releases page](https://github.com/PostMule/app/releases). Double-click and follow the setup wizard. No technical knowledge required.

### Option B — Command Line

For advanced users, self-hosters, and automation.

<details>
<summary><strong>Prerequisites</strong></summary>

- **Python 3.12+** — download from [python.org/downloads](https://python.org/downloads). During install, check **"Add Python to PATH"**.
- **git** — download from [git-scm.com](https://git-scm.com/downloads). Accept the default "Add Git to PATH" option. (Only needed to clone the repo — not required after setup.)

</details>

Clone the repo and run the setup script:

```powershell
git clone https://github.com/PostMule/app.git PostMule
cd PostMule
.\setup.ps1
```

The script checks prerequisites, creates a virtual environment, prompts for your email and API key, encrypts credentials, and registers the daily scheduled task. See the [CLI Install Guide](docs/install-cli.md) for the manual steps or silent-install flags.

---

## Features

- **Automatic mail sorting** — Every day, PostMule checks your virtual mailbox and email for new items, reads each one, and files it into the right category automatically.
- **Bill tracking** — Extracts amounts and due dates from bills. Sends you a reminder before anything is due.
- **Payment matching** — Connects to your bank (via YNAB or similar) and marks bills paid when it finds the matching transaction.
- **Forward-to-me alerts** — Detects physical items that need to be mailed to you (checks, gift cards, etc.) and sends an immediate alert.
- **Web dashboard** — Review your mail, manage bills, and change settings in a browser. No technical knowledge needed. Accessible remotely via Tailscale.
- **Your data stays yours** — All files stored in your own Google Drive. All data stored as plain JSON files. No lock-in.
- **Privacy-first** — Runs on your own computer. Credentials are encrypted; the master password lives in your system keyring, never on disk.
- **Swappable providers** — Change your virtual mailbox service, email provider, cloud storage, AI model, or finance app with one line in settings.

---

## Supported Providers

| Category | Default | Alternatives |
|---|---|---|
| Virtual mailbox | VirtualPostMail | Earth Class Mail, Traveling Mailbox, PostScan |
| Email | Gmail | Outlook.com, Proton Mail, any IMAP |
| Storage | Google Drive | Dropbox, OneDrive, S3 |
| Spreadsheet | Google Sheets | Excel Online, Airtable |
| AI (mail classification) | Gemini 1.5 Flash (free) | OpenAI, Anthropic, Ollama |
| Finance | — | YNAB, Plaid, Simplifi (experimental), Monarch (experimental) |

---

## Status

PostMule is in early development. The core features are built and tested, but it hasn't yet been validated against a live mailbox service. Expect rough edges.

---

## Technical Reference

For developers, self-hosters comfortable with the CLI, and contributors:

- [Architecture](docs/architecture.md) — component diagram and provider pattern
- [Daily Workflow](docs/workflows.md) — step-by-step pipeline detail
- [Providers](docs/providers.md) — how to configure each provider
- [CLI Install Guide](docs/install-cli.md) — command-line installation
- [Configuration Reference](docs/configuration.md) — all config.yaml fields
- [Contributing](CONTRIBUTING.md) — development setup and contribution guide

---

## License

MIT — see [LICENSE](LICENSE).

## Attribution

See [ATTRIBUTION.md](ATTRIBUTION.md).
