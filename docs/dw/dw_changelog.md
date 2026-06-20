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

---

## 2026-06-20 | Execute | Task: DW-PERCEPTION-OCR

**Task ID:** DW-PERCEPTION-OCR
**Type:** Execute (Phase 4 start)
**Status:** Complete

**Files Created:** `src/desktop_worker/perception/{__init__,backends,perceiver}.py`,
`tests/test_perception_ocr.py`.
**Files Modified:** `src/desktop_worker/schema/observations.py` (Element + elements),
`src/desktop_worker/schema/__init__.py`; continuity files + new backlog cards
(DW-PERCEPTION-WIRE; UIA card gains "make source required").

**Tests / Validations Run:** `python -m pytest` → **95 passed** (+8).

**Validation Level Reached:** **3** — unit + local runtime. Real Tesseract OCR not
machine-testable (engine + extra absent) → MANUAL-5.

**Result:** Added the Perception layer's OCR path: structured `Element`
(bounds/confidence/source) on the immutable `Observation`; an `OcrBackend` Protocol
with a pure, fully-tested `data_to_elements` parser, a lazy `TesseractOcrBackend`,
and a `Perceiver` that enriches a frozen observation (via `dataclasses.replace`) and
refuses to OCR the Null backend's placeholder. Degrades honestly to zero elements
without Tesseract. **Auditors:** Codex APPROVE, Northstar ALIGNED. Applied nits:
contiguous emitted-element IDs + ragged/bad-input robustness tests.

**Risks Introduced:** Elements not yet wired into the live loop (tracked
DW-PERCEPTION-WIRE) — AI still sees raw coords until then. Real OCR unverified (MANUAL-5).
**Risks Resolved:** None outstanding from prior cards.

**Next Action:** DW-PERCEPTION-UIA (the §7 preferred path) + DW-PERCEPTION-WIRE.

---

## 2026-06-20 | Execute | Task: DW-PERCEPTION-UIA

**Task ID:** DW-PERCEPTION-UIA
**Type:** Execute (Phase 4 — the §7 preferred path)
**Status:** Complete

**Files Created:** `src/desktop_worker/perception/uia_backend.py`,
`tests/test_perception_uia.py`.
**Files Modified:** `perception/perceiver.py` (UIA-preferred merge),
`perception/__init__.py` (exports), `schema/observations.py` (`Element.source`
now required); continuity files.

**Tests / Validations Run:** `python -m pytest` → **101 passed** (+6).

**Validation Level Reached:** **3** — unit + local runtime. Real UIA enumeration
needs the `uiautomation` lib + a live window → MANUAL-6.

**Result:** Implemented the §7 preferred perception path. Pure, tested
`control_to_type` (UIA ControlType → element type) and `merge_elements` (keep all
UIA; OCR only fills spatial gaps → UIA genuinely preferred). `UiaBackend` Protocol,
NullUiaBackend, lazy `WindowsUiaBackend`. Perceiver now gathers UIA first (even with
no screenshot) and merges OCR. Made `Element.source` a required field so attribution
is never silently defaulted. **Auditors:** Codex APPROVE, Northstar ALIGNED. Applied:
removed dead imports; fixed the live API to GetForegroundWindow+ControlFromHandle
(Codex F2 — real path was likely a silent no-op); zero-area skip now `or`.

**Risks Introduced:** Real UIA API names unverified until MANUAL-6 (degrades to []
if wrong, never crashes). Elements still not wired into the live loop (DW-PERCEPTION-WIRE).
**Risks Resolved:** Attribution honesty enforced (source required).

**Next Action:** DW-PERCEPTION-WIRE — wire the Perceiver into the loop.

---

## 2026-06-20 | Execute | Task: DW-PERCEPTION-WIRE

**Task ID:** DW-PERCEPTION-WIRE
**Type:** Execute (Phase 4 completion)
**Status:** Complete

**Files Created:** `tests/test_loop_perception_wire.py`.
**Files Modified:** `src/desktop_worker/loop/task_loop.py`; continuity files.

**Tests / Validations Run:** `python -m pytest` → **103 passed** (+2).

**Validation Level Reached:** **3** — unit + local runtime.

**Result:** Wired perception into the loop. `TaskLoop` takes an optional
`perceiver`; a new `_observe(label)` helper observes then enriches (UIA-preferred +
OCR) when a perceiver is present; before/after observations use it; `step.planned`
audit now carries `elements`. Default path (no perceiver) is unchanged with no new
hard dependency (decoupled via a `_PerceiverLike` Protocol). **Phase 4 complete.**
**Auditors:** Codex APPROVE, Northstar ALIGNED.

**Risks Introduced:** A misbehaving injected perceiver could raise (contract:
`perceive -> Observation`); default path unaffected.
**Risks Resolved:** §7/§2 gap closed — structured elements now reach the audit/AI.

**Next Action:** DW-INPUT-HARDEN (autonomous), then DW-PLANNER-AI (needs a user
decision on model/provider + API key).

---

## 2026-06-20 | Execute | Task: DW-INPUT-HARDEN

**Task ID:** DW-INPUT-HARDEN
**Type:** Execute (input reliability, requirements §9)
**Status:** Complete

**Files Created:** `tests/test_input_hardening.py`.
**Files Modified:** `src/desktop_worker/actions/windows_input.py`; continuity files.

**Tests / Validations Run:** `python -m pytest` → **109 passed** (+6).

**Validation Level Reached:** **3** — unit (pure planning helpers). Real keystroke
emission on a live desktop = MANUAL-1.

**Result:** Extracted the testable core of input handling: pure `resolve_vk`,
`plan_hotkey` (modifiers held, released in reverse, raises before sending so an
unknown key can't leave a modifier stuck down), and `should_paste`. Refactored
`WindowsInputBackend` to paste long text via clipboard+Ctrl+V and to support an
optional inter-key delay. Protocol/Null backend unchanged. **Auditors:** Codex
APPROVE, Northstar ALIGNED.

**Risks Introduced:** Paste path overwrites the clipboard (expected); real emission
unverified until MANUAL-1.
**Risks Resolved:** Stuck-modifier-on-unknown-key avoided and now tested.

**Next Action:** DW-PLANNER-AI — BLOCKED on a user decision (model/provider + API key).
