# dw_self_check.md — Self-check checklists

## Bootstrap self-check (BOOTSTRAP-1)
- [x] All workspace files exist (`dw_*.md`, `dw_tracker.html`, 3 `.bat`).
- [x] Repo path (`C:\Desktop-Worker`) and workspace path (`docs\dw`) correct.
- [x] Launcher paths correct (`where claude` → `C:\Users\Alper\.local\bin\claude.exe`).
- [x] No dangerous flags in launchers (no `--dangerously-skip-permissions`).
- [x] State/memory files readable and complete.
- [x] Roadmap and backlog aligned (phases ↔ cards).
- [x] Tracker HTML opens standalone (inline data, no server/fetch).
- [x] Next action unambiguous (DW-CLI-ELEVATE recommended).
- [~] Implementation gate: first session is normally planning-only, **but the
  user explicitly authorized the Phase 1 foundation** — implemented and tested.
  Further cards remain gated.
- [x] "NEXT PROMPT TO CLAUDE" block included in the response.

## Additional bootstrap verification (this project)
- [x] `python -m pytest` → 71 passed.
- [x] `python -m desktop_worker --null demo` → loop completed 5/5.
- [x] `python -m desktop_worker observe` → real desktop data returned.
- [x] No CLI execution path exists outside the broker (grep `subprocess`/`os.system`).
- [x] Emergency stop honored before actions and loop steps (tests cover it).

## Per-task self-check (use for every future card)
- [ ] Pre-implementation gate passed (ease-me skill).
- [ ] Only allowed files changed; diff budget respected; forbidden files untouched.
- [ ] `dw_state.md` updated; `dw_memory.md` updated if architecture changed.
- [ ] `dw_changelog.md` entry appended; `dw_tracker.html` refreshed.
- [ ] Manual steps logged for anything not self-validated.
- [ ] `python -m pytest` run; validation level reported honestly.
- [ ] Next action clear; "NEXT PROMPT TO CLAUDE" block included.
