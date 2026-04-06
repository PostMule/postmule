# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-05 (6): Built #102 chunk 2 — connection testers. Added `POST /setup/api/test-gmail` (IMAP4_SSL login to imap.gmail.com:993) and `POST /setup/api/test-gemini` (via `_probe_gemini_key()` helper, patchable for tests). Steps 2 and 3 now intercept "Next" with inline JS, POST to the tester, show green/red status, and auto-advance on success. 13 new tests (1090 total passing). Pushed commit `3adc680`.

---

## Next

> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Recommended:** Continue #102 chunk 3 — polish and close. Remaining work: (a) test the wizard end-to-end against a real Gmail + Gemini account to confirm no edge cases, (b) close #101 (setup.ps1 Gemini regex bug — superseded by the wizard), (c) close #102 if wizard is feature-complete. Also check if step 4 (master password) needs a tester or if it's fine as-is (no external service to test).

**After #102:** Build #104 — Expert Directory. Run the bootstrapping session using `.claude/skills/Expert-framework-prompt.md`. Start with `frontend_developer` and `ux_designer`. Produces `.claude/experts/EXPERT_DIRECTORY.md`.

**In progress:** Live validation (#30) — PostMule installed and running at C:\Users\openclaw0123\PostMule. Dry runs pass clean. Next step: trigger a real run once a VPM scan notification email arrives.

**Other open issues (blocked):**
- #103 — logs test fails on machines with live install (pre-existing; easy fix)
- #101 — setup.ps1 Gemini regex bug (will be closed when #102 is built)
- #97 — Cloud deployment investigation (owner must decide platform/cost tradeoffs first)
- #96 — Installer validation (unblocked once #102 is done)
- #93 — VPM API confirmation (requires live VPM account)
- #91 — Configure DNS for postmule.com (manual registrar step)
- #87 — Vectorize logo (requires designer/Illustrator)

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon".

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
