# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-03-29 (7): Branding/docs cleanup — README now surfaces postmule.com; decisions.md updated with logo usage rules, favicon generation process, and landing page setup. All actionable issues closed; three remain blocked (see below).

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED — requires live credentials for Gmail, VPM, Gemini, Drive)

**Backlog:** #87 (vectorize logo — manual step, requires external tool, skip in code sessions). Otherwise empty — check `gh issue list --repo PostMule/app` before starting.

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon".

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
