# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-04 (3): Stack-ranked open issues by code-actionable impact. Two issues are actionable now; all others are blocked, deferred, or non-code. No code changes this session.

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED — requires live credentials for Gmail, VPM, Gemini, Drive; developer must run this themselves before any public release)
- #93 — VPM API confirmation (BLOCKED — requires live VPM account)
- #95 — Bill matching ACH tolerance (DEFERRED — run #30 first to understand real failure rate)
- #96 — Installer validation (DEFERRED — complete #30 and #94 first)

**Backlog — stack ranked by code-actionable impact:**
1. **#94** — Local-first default config: local storage + IMAP/SMTP as defaults. Closes deal-breaker #3 (Google Cloud gate blocks every new user). Unblocks #96. Also reduces #92 scope (local path has no OAuth). Large scope — adds ≥2 new providers + config + docs. Start here.
2. **#92** — Pipeline failure alerting + OAuth re-auth UI. Closes deal-breaker #1 (silent 2am failure with no recovery path). Medium-large scope: pipeline + dashboard + notifications. Scope shrinks after #94 ships (local path has no OAuth expiry).

**Not actionable (do not action):**
- #97 — Cloud deployment investigation (deferred until #30 is complete)
- #91 — Configure DNS for postmule.com (manual registrar step, not a code task)
- #87 — Vectorize logo (manual, external tool)

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon". Hold until #94 and #92 are complete.

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
