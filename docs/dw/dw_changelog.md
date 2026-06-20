# dw_changelog.md — Changelog

> Append-only. Add entries at the bottom.

## 2026-06-20 | Bootstrap | Task: BOOTSTRAP-1

**Task ID:** BOOTSTRAP-1
**Type:** Bootstrap (+ Phase 1 implementation, user-authorized)
**Status:** Complete

**Files Created:**
- Package: `src/desktop_worker/{__init__,__main__,app,config,util}.py`
- `schema/{__init__,actions,observations,results}.py`
- `safety/{__init__,emergency_stop,policy}.py`
- `audit/{__init__,log}.py`
- `broker/{__init__,risk,cli_broker}.py`
- `observation/{__init__,backends,windows_backend,observer}.py`
- `actions/{__init__,backends,windows_input,executor}.py`
- `loop/{__init__,task_loop}.py`
- Tests: `tests/test_{actions_schema,risk_classifier,audit_log,emergency_stop,policy,cli_broker,executor,observer_and_loop}.py`
- Repo: `pyproject.toml`, `README.md`, `CLAUDE.md`, `.gitignore`
- Workspace: `docs/dw/dw_*.md`, `dw_tracker.html`, launchers `start_dw_claude.bat`,
  `continue_dw_claude.bat`, `status_dw.bat`

**Files Modified:** none (greenfield; only `docs/requirements.md` pre-existed, untouched).

**Tests / Validations Run:**
- `python -m pip install -e ".[dev]"` — OK
- `python -m pytest` — **71 passed**
- `python -m desktop_worker status` (Null + real backends) — OK
- `python -m desktop_worker observe` — returned **real** cursor/window/screen data
- `python -m desktop_worker --null demo` — full loop completed 5/5 steps

**Validation Level Reached:** **3** — unit tests + local runtime. Live-desktop
input motion (Level 4) NOT run (MANUAL-1). Real screenshots need `[windows]` (MANUAL-2).

**Result:** Stood up the Desktop-Worker Python foundation across all 8
architectural layers with safety, audit, emergency stop, and the elevated CLI
broker present from the start. The observe-plan-act-verify-log loop runs
end-to-end with a scripted planner; real Windows observation works on the dev
machine. Fixed a real CLI risk-classifier false positive (`.md` matching the
`md` mkdir alias). Seeded the full ease-me workspace and launchers.

**Risks Introduced:** Broker `shell=True` (gated); heuristic risk classifier;
"elevated by default" not yet true per-command from non-admin context (tracked
DW-CLI-ELEVATE). See `dw_state.md` Open risks.
**Risks Resolved:** Risk-classifier `.md`/`md` false positive fixed.

**Next Action:** DW-CLI-ELEVATE (or DW-INPUT-HARDEN / DW-PERCEPTION-OCR) — see
`dw_backlog.md`. Approval required before implementing.

---

## 2026-06-20 | Continue | Task: GIT-INIT

**Task ID:** GIT-INIT
**Type:** Continue (repo/version-control setup)
**Status:** Complete

**Files Created:** none (git history).
**Files Modified:** `dw_state.md`, `dw_manual_steps.md`, `dw_project_profile.md`,
`dw_changelog.md` (continuity updates for the commit/remote).

**Tests / Validations Run:** none beyond BOOTSTRAP-1 (no code change).

**Validation Level Reached:** 0 — docs/state updated; version control established.

**Result:** User created GitHub repo and authorized git workflow. Added remote
`origin` (github.com/alperozel1990/Desktop-Worker), renamed branch to `main`,
committed the bootstrap as `023b107`, and pushed to `origin/main`. Updated
continuity files; commit + push are now allowed for this project.

**Risks Introduced:** None.
**Risks Resolved:** MANUAL-3 (initial commit) closed.

**Next Action:** DW-CLI-ELEVATE — see `dw_backlog.md` (approval required before implementing).

---

## 2026-06-20 | Execute | Task: DW-LOOP-RECOVERY

**Task ID:** DW-LOOP-RECOVERY
**Type:** Execute (Phase 2 completion)
**Status:** Complete

**Files Created:** `tests/test_loop_recovery.py` (10 tests).
**Files Modified:** `src/desktop_worker/loop/task_loop.py`; continuity files
(`dw_state.md`, `dw_memory.md`, `dw_roadmap.md`, `dw_backlog.md`, `dw_tracker.html`).

**Tests / Validations Run:** `python -m pytest` → **80 passed** (+9).

**Validation Level Reached:** **3** — unit + local runtime. No human test required
for this card (pure loop logic; clock injected for determinism).

**Result:** Replaced the "fail → stop" stub with the full §15 recovery ladder:
re-observe after failure, bounded retry of *safe* actions only (non-idempotent
actions excluded), optional planner `replan()` (bounded), and a wall-clock task
limit enforced both at the outer loop and inside the recovery loop. All
transitions emit audit events (`step.retry`, `step.replanned`, `task.timeout`).
**Auditors:** Codex Auditor → APPROVE (after fixing: removed unexecutable
`window.focus`/`verify` from the retryable set, added in-recovery time guard,
fixed a re-plan off-by-one that made an extra planner call past the bound);
Northstar Auditor → ALIGNED.

**Risks Introduced:** None new. Re-plan bound reuses `max_retries` (documented).
**Risks Resolved:** Loop no longer stops on first transient failure; no unbounded
retry/re-plan; time limit now actually enforced.

**Next Action:** DW-CLI-ELEVATE — implementable autonomously to Level 3; true UAC
validation will be flagged as a user test (not blocking).

---

## 2026-06-20 | Execute | Task: DW-CLI-ELEVATE

**Task ID:** DW-CLI-ELEVATE
**Type:** Execute (Phase 3 completion)
**Status:** Complete

**Files Created:** `src/desktop_worker/broker/elevation.py`.
**Files Modified:** `src/desktop_worker/broker/cli_broker.py`, `tests/test_cli_broker.py`;
continuity files (state, memory, roadmap, backlog, manual_steps, tracker).

**Tests / Validations Run:** `python -m pytest` → **87 passed** (+7; 14 broker tests).

**Validation Level Reached:** **3** — unit + local runtime. Real UAC "runas" path
NOT machine-testable; needs human → MANUAL-4.

**Result:** Added an injectable per-command elevation strategy. `WindowsElevator`
re-launches a single command elevated via ShellExecuteEx "runas", wrapping it in an
app-controlled (mkstemp, unpredictable-name) .bat that redirects stdout/stderr to the
broker artifacts and writes the exit code to a sentinel; output + exit code recovered
after the elevated child exits. Broker splits `_run_inline` / `_run_elevated`;
`CliResult.elevated` now reflects ACTUAL elevation (honesty invariant) instead of mere
process-token state. Approval/risk/audit gating unchanged and still precedes any
elevation. **Auditors:** Codex APPROVE (after fixes: moved helper files off global
%TEMP% to the app dir to close a TOCTOU/local-EoP surface, finally-cleanup on timeout,
mbcs wrapper encoding, use_last_error); Northstar ALIGNED.

**Risks Introduced:** Real elevation path unverified until MANUAL-4. Non-admin parent
cannot kill an elevated child on timeout (documented; reported as timedOut).
**Risks Resolved:** "Elevated by default" is now genuine + honest; TOCTOU temp-file
surface removed.

**Next Action:** Phase 4 Perception — DW-PERCEPTION-OCR (then DW-PERCEPTION-UIA).
