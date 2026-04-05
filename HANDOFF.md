# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-04 (2): Explored cloud deployment options to simplify PostMule for non-technical users while keeping developer off user data. Top options: Docker Compose (bundle Python/Tesseract, replace Task Scheduler with container cron) and Railway/Render one-click deploy to user's own account. Created issue #97 to track investigation. No code changes this session.

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED — requires live credentials for Gmail, VPM, Gemini, Drive; developer must run this themselves before any public release)
- #93 — VPM API confirmation (BLOCKED — requires live VPM account)
- #95 — Bill matching ACH tolerance (DEFERRED — run #30 first to understand real failure rate)
- #96 — Installer validation (DEFERRED — complete #30 and #94 first)

**Backlog (actionable in code sessions):**
- #92 — Pipeline failure alerting + OAuth re-auth UI (no live credentials needed)
- #94 — Local-first default config: local storage + IMAP/SMTP as defaults (no live credentials needed; highest-leverage change before public release)
- #97 — Cloud deployment investigation: Docker Compose + Railway/Render deploy button (deferred until #30 is complete)
- #91 — Configure DNS for postmule.com (manual registrar step, not a code task)
- #87 — Vectorize logo (manual, external tool)

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon". Hold until #94 and #92 are complete.

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
