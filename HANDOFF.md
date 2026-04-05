# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-05 (5): Built #102 chunk 1 — setup wizard skeleton. `postmule serve` now auto-opens browser. First-run detection via `_setup_required()`. New `setup_bp` blueprint with `/setup/step/1-4` + `/setup/finish`. Full 4-step wizard HTML (`setup.html`). Auth guard bypasses setup routes. Finish route writes config.yaml via PyYAML and encrypts credentials.enc. Tests green (1077 pass). Filed #103 (pre-existing logs test failure). Filed #104 (Expert Directory bootstrapping). Pushed commit `422f097`.

---

## Next

> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Recommended:** Continue #102 chunk 2 — connection testers. Add `POST /setup/api/test-gmail` (IMAP login test) and `POST /setup/api/test-gemini` (minimal Gemini API call), both returning JSON `{ok, error}`. Add inline JS to steps 2 and 3 that calls the tester before allowing Next, showing green checkmark or red error with plain-English message.

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
