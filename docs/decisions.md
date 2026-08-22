# PostMule — Design Decisions

Non-obvious decisions that would surprise a new contributor or be hard to infer from the code alone. Each entry notes the reasoning and links to the originating issue where one exists.

---

## The E2E ship gate must be able to fail (2026-08-22)

**The gate now derives every asserted value from the document and runs the real Drive path.** The
previous gate could not fail. `FixtureLLMProvider.classify()` never read its `ocr_text` argument — it
returned module constants — and the gate then asserted the stored bill equalled those same constants.
It also filed through `LocalStorageProvider`, whose file id is a filesystem path and which has no
checksum concept, so the execute → MD5-verify path in the architecture invariants was never exercised
by the one test that certifies a release.

This was measured, not inferred: running the previous gate with `extract_text` monkeypatched to return
`""` produces **E2E_PASS**, including its check named "one PDF was OCR'd and classified".

Three changes make it falsifiable. `DocumentReadingLLM` has no canned answers — every field is parsed
out of the OCR text at call time and confidence is computed from how much of the document was legible,
so broken OCR collapses it. `tests/fixtures/e2e/sample_bill.expected.json` records what the document
SAYS, authored by reading the PDF; the extractor and the expectations have no shared source, so
agreement is evidence. And the gate runs the real `DriveProvider` over `scripts/fake_drive.py`, a
transport double storing real bytes and real MD5s, so the provider's upload, checksum read-back, move
and rename all execute — only the network is replaced.

Six negative controls in `tests/integration/test_e2e_fixture_gate.py` assert the gate goes red when OCR
returns nothing, reads a different document, or reads part of one; when Drive reports a mismatched
checksum; and when the expectations and the document disagree. **If one of those has to be deleted to
make the suite pass, the gate has regressed into a tautology — fix the gate, not the test.** Checks
went 10 → 21. See #113.

**Gap found and deliberately not papered over:** the invariant "All Drive writes: execute → MD5 verify
→ audit log" is only half implemented. MD5 verification exists (`upload_pdf(verify=True)`) and is now
covered. There is no audit log anywhere in `postmule/` — `grep -rn "audit" postmule/` returns nothing
outside the web layer. The gate asserts the halves that exist and invents nothing. The invariant
describes a control that was never built; it needs either an implementation or an honest amendment.

## Bill matching is amount-exact, date-tolerant, human-approved (owner ruling 2026-08-22)

**Owner ruling on #118 / ops owner-64: reconcile the documentation to the code, not the reverse.** The
rule is: amount exact (`amount_tolerance_cents` defaults to 0), date within a configurable tolerance
(`date_tolerance_days` defaults to 7), and every match surfaced as a ranked candidate requiring manual
approval before anything is applied.

`CLAUDE.md:28` currently states the opposite ("Exact amount + exact date required"). The code has
always done tolerance matching — `match_bills_to_transactions` emits `exact` / `fuzzy_date` /
`fuzzy_amount` / `fuzzy_both` tiers and writes to `pending/bill_matches.json` for review. The ruling
resolves the contradiction in favour of the shipped behaviour: nothing auto-applies, so a permissive
window costs a reviewer a glance, while a strict filter silently hides real payments.

Also to fix under the same task, and independent of the ruling: `_run_bill_matching`
(`pipeline.py:897`) selects `bills_YYYY.json` using the **local** year (`_d.today().year`) while the
rest of the pipeline stamps year in **UTC**. Around the New-Year boundary the two disagree and a valid
match is missed. The clock needs injecting so a test can pin the boundary.

**Status: ruled, NOT yet implemented.** `CLAUDE.md:28`, `config.example.yaml`, `docs/configuration.md`
and the web settings copy still describe the old rule.

## Outlook / Microsoft Graph is cut from v0.1.0 (owner ruling 2026-08-22)

**Owner ruling on #119 / ops owner-65: stub `_graph.py` and add it to the coverage omit list.** This
applies a cut that #105 effectively already made — `outlook_365.py` and `outlook_com.py`, its only
consumers, were stubbed then, and both are already in `[tool.coverage.run] omit`. `_graph.py` is the
one provider implementation at 0% coverage that is *not* omitted, so its 104 uncovered statements drag
the core coverage denominator for code nothing runs.

It also carries an unescaped OData filter (`_build_graph_filter` interpolates `processed_category`,
`sender` and `subject` into single-quoted OData literals without doubling embedded quotes). Currently
unreachable — no live caller constructs `GraphEmailProvider` — so stubbing retires the defect with the
code. If Outlook is ever un-cut, the escaping must be fixed before it is wired to anything.

**Status: ruled, NOT yet implemented.**

## Gemini's SDK is end-of-life (2026-08-22)

`google-generativeai` (pinned 0.8.6, `requirements.txt`/`requirements-lock.txt`) emits a hard
deprecation notice on import: all support has ended, migrate to `google-genai`. It still works, and the
suite passes with it, but it is the default LLM path for the product and it is unmaintained. Needs a
migration issue before v0.1.0 ships.

## Crash recovery across the Drive↔JSON boundary (2026-06-26)

**The pipeline brackets each file's Drive move and JSON store with a write-ahead journal, and reconciles on the next run.** A crash between moving a file on Drive and writing its JSON record used to leave the file in a destination folder with no record (or a double-move on re-run). `postmule/data/journal.py` writes an entry (the intended destination, filename, category, and the exact record dict) atomically before the Drive move and removes it after the store commits. `postmule/agents/reconcile.py` runs at pipeline start and replays any leftover entry idempotently — using the stable Drive file id as the join key — without re-running OCR/LLM: it writes the missing record if the file already moved, redoes the move if not, and flags divergence (never deletes) if the file has vanished from Drive. The JSON store (`add_bill`/`add_notice`/`add_item`) is idempotent by a non-empty `drive_file_id`, so a replay or a double run cannot create a second record.

Alternatives rejected: a stateless Drive-vs-JSON sweep (needs re-OCR/LLM to rebuild lost metadata — costs money, non-deterministic); moving the source of truth into SQLite/ACID (breaks the swappable-spreadsheet-provider design and the JSON-is-source-of-truth invariant); a Drive staging folder (extra round-trip per file, same crash window remains). Reconcile assumes Drive's stable-id semantics (ids survive move/rename); local storage changes ids on move, but Drive is the ship target (#122). Owner intake ops #62 / app #115.

**A single-instance run lock prevents overlapping pipeline runs.** `postmule/core/run_lock.py` holds an `msvcrt` byte-range lock on a file under `data_dir` for the whole run; a scheduled run colliding with a manual run is refused (status `skipped`, no work). The OS releases the lock when the holder closes the handle or dies, so a crashed run leaves no stale lock to detect — chosen over a pidfile with liveness reclaim because a reliable dead-pid check on Windows is awkward (`os.kill(pid, 0)` terminates rather than probes). A run writes an `in-progress` run-log marker at start, finalized at end; reconcile relabels an orphaned marker `crashed`. Windows-only (`msvcrt` is stdlib, no new dependency). Dry runs perform no writes and skip the lock entirely.

---

## Bill Matching

**Company name is not used for matching.**
Finance providers (YNAB, Simplifi, Plaid) overwrite the merchant name on transactions with their own normalized strings. These rarely match the biller name extracted from the PDF. See #27 for the planned addition of ACH descriptor and statement date fields, which will make matching more reliable.

> **Superseded in part (2026-08-22).** The clause "matching uses exact amount + exact statement date
> only" was never true of the code and is overruled by the owner ruling above — amount exact, date
> within a configurable tolerance (default 7 days), every match human-approved. The company-name point
> stands. See #118.

---

## Entity Model

**One entity per account number.**
AT&T Mobile (****1234) and AT&T Internet (****5678) are two separate entity records, not one entity with two accounts. This prevents ambiguous bill assignment and makes account-level matching precise. See #32.

**Friendly name is primary and must be unique.**
`friendly_name` is the user-editable label shown prominently in the UI. The canonical `name` (what the LLM/OCR extracts — e.g. "AT&T Mobility LLC") is shown as secondary muted text below it. Validation must block saving if `friendly_name` is already used by another entity. See #32.

**Account number is stored in full; displayed masked.**
Strip all spaces and special characters from the raw account number, then show the last 4 digits as `****1234`. The full value is stored in `entities.json` for matching. See #32, #33.

**Last Payment column shows matched payment only.**
Displays the most recent *matched* payment date and amount (e.g. "Mar 18 · $94.00"). Shows `—` if no payment has ever been matched to this entity. Unmatched pending bills do not contribute to this value. See #33.

**Aliases are only visible in the expanded detail panel.**
Aliases are never shown in the main entity table row — only in the chevron-expanded detail section below the row. This keeps the table scannable. See #33.

---

## Mail Reassignment

**Reassignment is inline, not a modal.**
Each mail item has a small "Edit" link. Clicking it expands a row directly below the item. The user clicks the category badge to pick a new category, or the entity name to pick from an alphabetical list of friendly names. Save commits; Cancel collapses without saving. See #34.

---

## Data Storage

**Google Sheets is a generated view and is never written to directly.**
All writes go to JSON files in `_System/data/`. The Sheets view is rebuilt from JSON on demand. If a user edits a cell in Sheets it will be overwritten on the next sync. This is intentional and must remain true even as new providers are added. See #14.

---

## Dashboard & Email Templates

**`mockup_dashboard.html` is the living mockup for the web dashboard.**
It is the design source of truth for the dashboard UI. `brand_reference.html` is the brand reference it was derived from. Any visual change to the dashboard must be reflected in `mockup_dashboard.html`.

**`mockup_email_daily.html` is the design reference for the daily summary email.**
The production Jinja2 template at `postmule/web/templates/email_daily.html` is derived from it. Any change to the email design should update both files together. See #52.

---

## Branding & Logo

**`logo_face.png` is used for nav, favicon, and email header. `logo2.png` is for full-body contexts.**
`docs/logo_face.png` (470×420, head/ears crop) reads clearly at small sizes and is used in the dashboard nav, login page, email header, and as the favicon source. `docs/logo2.png` (full body) is used for splash screens, letterhead, and the landing page hero. Both are AI-generated raster images (Microsoft Designer / DALL-E 3). See #88, #89. `docs/logo.svg` (vectorized) is the target for print use — see #87.

**`logo_face.png` is copied to `postmule/web/static/logo_face.png` for Flask to serve.**
The docs/ source file is the canonical copy. The static/ copy is what the running app serves at `/static/logo_face.png`. Both must be kept in sync if the logo is ever updated. The email template uses `{{ dashboard_url }}/static/logo_face.png` as an absolute URL so email clients can load it.

**Favicons are generated from `logo_face.png` via Pillow (center-crop → resize).**
`postmule/web/static/favicon.ico` (32×32), `favicon-64.png` (64×64), and `apple-touch-icon.png` (180×180) were generated by center-cropping the 470×420 source to a 420×420 square, then resizing. Regenerate with Pillow if the logo changes. See #89.

---

## Testing

**CLI log-path tests isolate via an overridable candidates function, not an env var.**
`postmule/cli.py`'s `logs` command checks a hardcoded fallback path
(`C:/ProgramData/PostMule/logs/verbose`) so it works on a live install with no config.
The "no log file" test failed on machines where that path had a log for today. Fixed
by extracting `_log_candidates(today)` so the test can monkeypatch the search paths
directly, rather than introducing a `POSTMULE_CONFIG`-based redirect that the command
itself doesn't otherwise use. See #103.

---

## MVP Scope (v0.1.0)

**`entity_discovery` is MVP-core.**
The 2026-04-04 architecture council marked this CONFIRM; the #105 MVP scope review (2026-06-14) raises it to KEEP. Entity/account matching is the mechanism behind filing a bill into the correct folder, which is part of the v0.1.0 success scenario (one fixture email fetched, OCR'd, classified, filed, recorded, and visible in the dashboard, in a dry run). See #105.

**`backup` is MVP-core and gains a dedicated test; `retroactive` is post-release.**
A system-of-record for financial documents ships with a working snapshot, so `backup` is KEEP with a new test covering snapshot write and restore under the platform path layer. `retroactive` is a one-time migration tool for the 130 CONFLICT PDFs, run once by the owner and off the v0.1.0 E2E path; the code stays but is out of scope and out of the gate. See #105.

**The autopilot Python harness rewrite is deferred past v0.1.0; the PowerShell harness is frozen.**
The dependency-free Python core (`harness/` package, `config.py` + `state.py`, 55 tests) is kept as already-built work, but Track B steps 2-4 do not continue until v0.1.0 ships. The existing PowerShell harness in ops `scripts/` takes no new features through v0.1.0. See #105, ops PLAN §16.

**14 untested providers are stubbed, not cut.**
imap, outlook_365, outlook_com, proton, dropbox, onedrive, s3, airtable, excel_online, anthropic, openai, traveling_mailbox, postscan, and earth_class keep `base.py` and a registry entry that raises a clear "not implemented in this build" error. Per the soft-delete invariant, stubbing removes only the body; `test_provider_completeness.py` is updated in the same commit so it does not import deleted bodies. See #105.

**`ollama` is KEEP+test; Gemini remains the default until it is validated on real mail.**
The 2026-04-04 council grouped `ollama` with the untested LLM providers for STUB. The #105 review overturns this: the provider is already built against the same JSON-schema prompt as Gemini, bill classification is bounded structured extraction that suits a local model, and a local/private LLM path is the direct expression of the project's "user owns their financial documents" value proposition, which the council applied to storage and email but not the LLM. `ollama` gets a dedicated test against the committed fixtures (needs Ollama running with a pulled model); Gemini stays the validated default until the local path is proven on real mail, post-release. See #105.

**A runtime/operational product premortem runs as an owner-attended pre-P1 gate.**
The 2026-04-04 council never examined the cloud-LLM dependency, token cost, or pipeline runtime failure modes, and is 69 days old relative to the cross-platform and MVP-scope decisions. A focused premortem using the `council-this` skill runs before the P1 grind, scoped to runtime/operational failure modes (not a re-run of the architecture council). Its output is a short risk list mirroring the harness failure catalog (ops PLAN §18). See #105.

---

## Storage Provider Interface

**`StorageProvider.move_file` and `rename_file` return `str | None` (the new file_id), not `None`.**
The p1-e2e-fixture-gate run (PLAN 14.18) found that `run_daily_pipeline` called `move_file()` then
`rename_file()` with the same file_id, but for `LocalStorageProvider` the file_id is the absolute
path, and `move_file` already relocated the file — so `rename_file` looked for it at the old path
and failed with a warning. Cloud providers (Drive, S3, etc.) use stable opaque IDs that don't
change on move/rename, so this only surfaced once a path-based local backend existed. The
Protocol, `LocalStorageProvider`, and `pipeline.py` now chain the returned id through both calls
and into JSON storage; cloud providers may continue returning `None` (id unchanged). See #105,
PLAN 14.18.

---

## Platform Paths

**Per-OS default config/install dirs live in `postmule/core/platform_paths.py` (2026-06-15).**
`cli.py`'s config search, log-file fallback, and uninstall default, plus `pipeline.py`'s
default local storage `root_dir`, previously hardcoded `%APPDATA%` and
`C:\ProgramData\PostMule`. `default_install_dir()` and `user_config_dir()` keep those exact
values on Windows (no behavior change for existing installs) and add macOS
(`~/Library/Application Support/PostMule`) and Linux (XDG `config`/`data` dirs, falling back
to `~/.config` and `~/.local/share`) equivalents. `config.example.yaml` and the install docs
remain Windows-specific since they describe the Windows installer's generated config; the
per-OS defaults only apply when `install_dir`/`root_dir` are absent from config. See #105.

---

## Scheduler Adapter

**Per-OS scheduler adapter lives in `postmule/core/scheduler.py` (2026-06-15).**
`cli.py`'s `install-task`/`uninstall-task` commands and the `configure` (installer wizard)
command now go through `get_scheduler()`, which returns a `WindowsScheduler` or
`MacScheduler`. Windows keeps the existing `Register-ScheduledTask`/`Unregister-ScheduledTask`
PowerShell calls (task name `PostMule Daily Run`, daily trigger at the configured local
HH:MM, unchanged for existing installs). macOS registers a per-user LaunchAgents plist
(`com.postmule.dailyrun`) with a `StartCalendarInterval` daily trigger via `launchctl
bootstrap`/`bootout`. The macOS command resolves to `shutil.which("postmule")` if a console
script is on PATH, else falls back to `[sys.executable, "-m", "postmule.cli"]` — this is
forward-compatible with whatever the macOS install contract (pending) produces. The macOS
path is implemented but untested on real hardware; verify at bring-up. See #105.

---

## macOS Install Contract

**`setup.sh` (repo root, 2026-06-15) is the macOS/Linux counterpart to `setup.ps1`.**
Same contract: venv + console-script install (`pip install -e .`), interactive or
silent config of `alert_email`/`scan_sender`/Gemini key, credential encryption via
`postmule.core.credentials` (keyring already cross-platform — Keychain on macOS), then
a dry run. On macOS it also calls `postmule install-task` to register the launchd job
added by the scheduler adapter; Linux has no scheduler adapter yet, so the step is
skipped with a warning to use cron manually. No Inno Setup port for macOS — `setup.sh`
is the only supported install path there. Per-OS `INSTALL_CMD`/`INSTALL_SMOKE_CMD` are
documented in `docs/install-cli.md` under "Install contract (per-OS)". See #105.

---

## LLM Cost Cap

**Monthly dollar cap accrues across days and is on by default; cost books only on success (2026-06-27).**
`core/api_safety.py` previously compared a monthly budget against `estimated_cost_usd`,
a counter `_maybe_reset_for_new_day` zeroed every midnight, so the cap could never reach a
realistic monthly figure; the default budget was also 0.0 (the check is gated on `> 0`), so
it was off out of the box. The fix splits the dollar accounting from the daily request/token
counters: `DayUsage` carries `month` + `monthly_cost_usd`; the daily reset zeroes only the
daily fields, and a separate `_maybe_reset_for_new_month` clears the monthly accumulator on a
month change. `check_and_record` enforces the budget against projected month-to-date spend
*before* the call and books no dollars; a new `record_cost()` books the actual cost only after
a successful response, so failed calls and retries cost nothing.

Default `monthly_cost_budget_usd` is now 5.00 (was 0.00). Pricing is a config number
`api_safety.usd_per_1k_tokens`, default 0.0. Rejected alternatives: defaulting the price to the
published paid Gemini rate (would accrue phantom cost on free-tier runs and could false-stop an
autonomous run); making `monthly_cost_budget_usd` a daily cap (contradicts the name and the
owner's monthly intent); a model→price lookup table (goes stale, larger surface). The $5.00
default and the price-0.0 posture are recommendations the owner can override in one config line;
both are flagged in the owner-63 plan's Dissent. See app #116 / ops issue #63.

---

## Public Website

**`docs/index.html` is the public landing page, served at postmule.com via GitHub Pages.**
GitHub Pages serves from `docs/` on the `main` branch. The landing page uses relative paths to `logo_face.png` and `mockup_dashboard.html` — keep all three files in `docs/` together. DNS configuration and CNAME setup are tracked in issue #91: once DNS A records point to GitHub Pages, add `docs/CNAME` containing `postmule.com` to enable the custom domain.
