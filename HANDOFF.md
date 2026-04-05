# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Session 2026-04-04 (4): Completed #92 (pipeline failure alerting + OAuth re-auth + stale-run banner) and #95 (configurable bill matching tolerances + refined confidence values). 1078 unit tests. Both pushed and closed on GitHub. All remaining open issues are blocked (require live credentials, hardware, or owner decisions) — blocked comments added to #87, #91, #93, #96, #97.

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**All open issues are currently blocked — see comments on each:**
- #97 — Cloud deployment investigation (owner must decide platform/cost tradeoffs first)
- #96 — Installer validation (requires owner to run on fresh Windows 11 machine)
- #93 — VPM API confirmation (requires live VPM account)
- #91 — Configure DNS for postmule.com (manual registrar step)
- #87 — Vectorize logo (requires designer/Illustrator)
- #30 — End-to-end validation (requires live credentials for Gmail, VPM, Gemini, Drive)

**Pending (not a code task):** Push a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the first release. After that, update README Option A to link to the Releases page instead of "coming soon".

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
