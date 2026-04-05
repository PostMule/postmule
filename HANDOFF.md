# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-05 (3): Fixed two more installer issues — #99 (hatchling build backend, now closed) and #100 (Task Scheduler admin check, now closed). PostMule installed at C:\Users\openclaw0123\PostMule. setup.ps1 ran but died before dry-run due to Task Scheduler access denied. Config files exist but "Pattern not matched" warnings suggest values may not have been written. Owner needs to: (1) verify config.yaml and credentials.yaml have correct values, (2) run `postmule --dry-run` manually.

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**In progress:** Live validation (#30) — PostMule installed at C:\Users\openclaw0123\PostMule. Next step: run `powershell -ExecutionPolicy Bypass -File .\setup.ps1` to complete config wizard (alert email, VPM sender, Gemini key, master password), then `postmule --dry-run`. See memory/setup_validation.md for full config details.

**Other open issues (blocked):**
- #97 — Cloud deployment investigation (owner must decide platform/cost tradeoffs first)
- #96 — Installer validation (requires owner to run on fresh Windows 11 machine)
- #93 — VPM API confirmation (requires live VPM account)
- #91 — Configure DNS for postmule.com (manual registrar step)
- #87 — Vectorize logo (requires designer/Illustrator)

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon".

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
