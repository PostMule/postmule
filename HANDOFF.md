# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-05 (4): Completed live validation setup (#30 still open — no VPM mail to process yet). PostMule at C:\Users\openclaw0123\PostMule now runs clean dry-runs with Gmail + Gemini credentials loading correctly. Identified and filed #102 (first-run web wizard) as the root cause fix for the painful manual setup experience. Issue #102 fully detailed and ready to build.

---

## Next

> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Recommended:** Build issue #102 — first-run web wizard. This is the highest-leverage item: unblocks #96 (installer validation), eliminates the manual setup pain discovered in #30, and closes #101. Full spec is in the issue.

**In progress:** Live validation (#30) — PostMule installed and running at C:\Users\openclaw0123\PostMule. Dry runs pass clean. Next step after #102: trigger a real run once a VPM scan notification email arrives.

**Other open issues (blocked):**
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
