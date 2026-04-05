# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-05: Fixed setup.ps1 parse errors on Windows (issue #98, now closed) — two root causes: LF line endings (.gitattributes added) and em dashes misread as curly quotes by PowerShell 5.1 CP1252. Also fixed pyproject.toml build backend. Owner is attempting live validation (#30) from a fresh install at C:\Users\openclaw0123\PostMule. setup.ps1 fixes applied to that clone directly; GitHub is up to date (commit 84d6bbf).

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**In progress:** Live validation (#30) — owner has VPM, Gmail app password, and Gemini API key. Fresh clone at C:\Users\openclaw0123\PostMule. Next step: re-run `powershell -ExecutionPolicy Bypass -File .\setup.ps1` after em dash fix. See memory/setup_validation.md for full config details.

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
