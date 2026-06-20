# dw_backlog.md — Implementation cards

> **Frozen / do-not-edit:** `docs/requirements.md` (read-only source of truth),
> `artifacts/` (generated). Respect each card's forbidden-files list.
> Each card is a narrow, scoped task with acceptance criteria, per requirements §4.2.

Status legend: ☐ todo · ◑ partial · ✅ done

---

## DW-CLI-ELEVATE — True per-command UAC elevation with captured output  ✅ done (2026-06-20)
**Purpose:** Make "elevated by default" real even when Desktop-Worker starts from
a non-admin context, without losing stdout/stderr/exit capture.
**Scope:** Add an elevation strategy to the broker that re-launches a single
command elevated (ShellExecute "runas") while redirecting its output to the
existing `cli/NNNN.stdout.txt` / `.stderr.txt` artifacts and recovering the exit
code (e.g. via a wrapper cmd that writes an exit-code file).
**Non-goals:** Changing the approval/risk model; sandboxing the shell.
**Dependencies:** none (broker exists).

**Inspect before coding:**
- `src/desktop_worker/broker/cli_broker.py`
- `src/desktop_worker/schema/results.py` (CliResult.elevated)
- `tests/test_cli_broker.py`

**Files allowed to edit:** `src/desktop_worker/broker/cli_broker.py`, new
`src/desktop_worker/broker/elevation.py`, `tests/test_cli_broker.py`.
**Files forbidden to edit:** `safety/`, `audit/`, `schema/actions.py`, anything outside `broker/`.

**Expected behavior:** When `elevated=True` and the process is not already admin,
the command runs in an elevated child; `CliResult.elevated` is True only when
elevation actually happened; output and exit code are still captured.
**Tests / validation:** `python -m pytest tests/test_cli_broker.py`. Mock/guard
the runas path on non-admin CI; add a manual UAC test step.
**Manual validation:** From a non-admin shell, run a low-risk elevated command and
confirm the UAC prompt + captured output (MANUAL step to be added).
**Rollback plan:** `git checkout -- src/desktop_worker/broker/`.
**Diff budget:** 2 production files changed, 1 new file.
**Done criteria:**
- [x] Elevated child output + exit code captured to artifacts (wrapper .bat redirect + exit sentinel).
- [x] `elevated` flag never overstates privilege (honesty invariant; auditor-verified).
- [x] Tests green (14 broker tests, injected FakeElevator); manual UAC step = MANUAL-4.
**Result:** Implemented `broker/elevation.py` (injectable `Elevator`, real `WindowsElevator`
via ShellExecuteEx runas). Codex APPROVE (after security fixes: app-controlled mkstemp
helper files, finally-cleanup, mbcs encoding, use_last_error), Northstar ALIGNED.
Real UAC path needs human validation → MANUAL-4.

---

## DW-INPUT-HARDEN — Input reliability hardening  ☐
**Purpose:** Make real mouse/keyboard input robust (requirements §9 reliability).
**Scope:** Migrate keyboard/mouse to a single `SendInput` batch API; configurable
inter-key delay; correct modifier hold/release for hotkeys; verify unicode typing;
optional clipboard-paste path for long text.
**Non-goals:** UIA-based input (that's Phase 4/5).
**Dependencies:** none.

**Inspect before coding:**
- `src/desktop_worker/actions/windows_input.py`
- `src/desktop_worker/actions/backends.py` (Protocol — keep stable)
- `tests/test_executor.py`

**Files allowed to edit:** `src/desktop_worker/actions/windows_input.py`, tests.
**Files forbidden to edit:** `actions/backends.py` Protocol signatures (keep the
NullInputBackend contract), `executor.py` dispatch logic.

**Expected behavior:** Typing and hotkeys are reliable across layouts; no dropped
keys; drag is smooth.
**Tests / validation:** `python -m pytest` (Null backend asserts dispatch);
manual desktop test for real motion (MANUAL-1).
**Manual validation:** Type into Notepad, send Ctrl+A/Ctrl+C, drag a window.
**Rollback plan:** `git checkout -- src/desktop_worker/actions/windows_input.py`.
**Diff budget:** 1 production file changed.
**Done criteria:**
- [ ] SendInput batch path implemented.
- [ ] Hotkeys hold/release modifiers correctly.
- [ ] Manual desktop validation logged.

---

## DW-LOOP-RECOVERY — Retry / re-plan / safe-stop in the loop  ✅ done (2026-06-20)
**Purpose:** Satisfy requirements §15 (error handling & recovery) beyond safe-stop.
**Scope:** In `TaskLoop`, on failed action or failed verification: re-observe,
retry safe actions up to `Limits.max_retries`, then ask planner for a revised
step, then safe-stop. Add max-time enforcement (`Limits.max_task_seconds`).
**Non-goals:** AI planner logic (interface only).
**Dependencies:** Phase 2.

**Inspect before coding:**
- `src/desktop_worker/loop/task_loop.py`
- `src/desktop_worker/config.py` (Limits)
- `tests/test_observer_and_loop.py`

**Files allowed to edit:** `src/desktop_worker/loop/task_loop.py`, tests.
**Files forbidden to edit:** `executor.py`, `safety/`.

**Expected behavior:** Transient failures retry; persistent failures re-plan then
stop safely; time/action/retry limits enforced and logged.
**Tests / validation:** `python -m pytest tests/test_observer_and_loop.py`.
**Manual validation:** none required.
**Rollback plan:** `git checkout -- src/desktop_worker/loop/task_loop.py`.
**Diff budget:** 1 production file changed.
**Done criteria:**
- [x] Retry honored up to max_retries with re-observe (bounded; tested).
- [x] Re-plan path invoked before stop (optional `Planner.replan`; bounded; tested).
- [x] Time limit enforced (outer + in-recovery guard); all transitions audited
  (`step.retry` / `step.replanned` / `task.timeout`).
**Result:** Implemented; Codex Auditor APPROVE, Northstar ALIGNED. 80 tests pass.

---

## DW-PERCEPTION-OCR — OCR perception (Phase 4 start)  ✅ done (2026-06-20)
**Purpose:** Give the AI visible-text understanding (requirements §7).
**Scope:** New `perception/` package: OCR backend (pytesseract) producing
structured elements (text, bounds, confidence, source="ocr"); Null OCR backend
for tests; integrate into `Observation` as optional `elements`.
**Non-goals:** UIA element detection (separate card DW-PERCEPTION-UIA).
**Dependencies:** Phase 1 observation.

**Inspect before coding:**
- `src/desktop_worker/observation/observer.py`
- `src/desktop_worker/schema/observations.py`
- requirements §7 (perception output example)

**Files allowed to edit:** new `src/desktop_worker/perception/*`,
`src/desktop_worker/schema/observations.py` (add Element + elements field), tests.
**Files forbidden to edit:** `actions/`, `broker/`, `safety/`.

**Expected behavior:** When OCR available, observations include detected text
elements with bounds/confidence; absent Tesseract, degrades to empty list.
**Tests / validation:** `python -m pytest` with a Null OCR backend.
**Manual validation:** Run OCR on a real screenshot (needs Tesseract + `[ocr]` extra).
**Rollback plan:** `git checkout -- src/desktop_worker/perception src/desktop_worker/schema/observations.py`.
**Diff budget:** 2 production files changed, 3 new files.
**Done criteria:**
- [x] Structured OCR elements in observation schema (`Element` + `elements` field).
- [x] Graceful degradation without Tesseract (lazy import; NullOcrBackend fallback).
- [x] Source attribution = "ocr"; confidence present (normalized 0..1).
**Result:** `perception/` package (OcrBackend Protocol, pure `data_to_elements`,
lazy TesseractOcrBackend, Perceiver enriches frozen Observation). Codex APPROVE,
Northstar ALIGNED. 95 tests. Real Tesseract OCR = MANUAL-5. Follow-up: wire
Perceiver into the loop (DW-PERCEPTION-WIRE) so elements reach the AI/audit.

---

## DW-PERCEPTION-UIA — Windows UI Automation elements (Phase 4)  ☐
**Purpose:** Prefer UIA over image-only automation (requirements §7 key rule).
**Scope:** UIA backend (`uiautomation`/comtypes) enumerating controls (button,
input, checkbox, etc.) with bounds + source="uia"; merge with OCR results
(UIA preferred). Null backend for tests.
**Dependencies:** DW-PERCEPTION-OCR (shared Element schema).

**Inspect before coding:** `src/desktop_worker/perception/*` (after OCR card),
`src/desktop_worker/schema/observations.py`.
**Files allowed to edit:** `src/desktop_worker/perception/*`, tests.
**Files forbidden to edit:** `schema/observations.py` Element shape (reuse it),
`actions/`, `broker/`.
**Expected behavior:** Common controls detected via UIA with high confidence;
results take precedence over OCR for the same region.
**Tests / validation:** `python -m pytest` (Null UIA backend).
**Manual validation:** Enumerate controls in a real window.
**Rollback plan:** `git checkout -- src/desktop_worker/perception`.
**Diff budget:** 2 new files, 1 changed.
**Done criteria:**
- [ ] UIA element detection with bounds + confidence + source.
- [ ] UIA-preferred merge with OCR.
- [ ] Make `Element.source` a REQUIRED field (no default) so every backend
  attributes honestly (Northstar guidance from DW-PERCEPTION-OCR review).

---

## DW-PERCEPTION-WIRE — Wire the Perceiver into the task loop  ☐
**Purpose:** Make detected elements actually reach the AI prompt + audit (today
`Observation.elements` is always empty in the live loop). Closes the §2/§7 gap
flagged by both auditors on DW-PERCEPTION-OCR.
**Scope:** Optionally enrich before/after observations in `TaskLoop` via a
`Perceiver` (off by default until a real backend is available), so `elements`
flow into `step.planned`/`step.completed` audit records.
**Dependencies:** DW-PERCEPTION-OCR (done); ideally DW-PERCEPTION-UIA first.
**Inspect before coding:** `loop/task_loop.py`, `observation/observer.py`,
`perception/perceiver.py`.
**Files allowed to edit:** `loop/task_loop.py` (or `observation/observer.py`), tests.
**Files forbidden to edit:** `actions/`, `broker/`, `safety/`.
**Expected behavior:** When a perceiver is provided, observations carry elements;
when not, behavior is unchanged (no regression, no forced OCR dependency).
**Tests / validation:** `python -m pytest` with a fake perceiver asserting
elements appear in the audited observation.
**Rollback plan:** `git checkout -- src/desktop_worker/loop/task_loop.py`.
**Diff budget:** 1–2 production files changed.
**Done criteria:**
- [ ] Perceiver optionally wired; elements reach audit/prompt.
- [ ] Default path unchanged (no new hard dependency).

---

## DW-PLANNER-AI — Pluggable AI planner (Claude)  ☐
**Purpose:** Drive the loop with an AI planner per requirements §1.
**Scope:** Implement a `Planner` that turns observation + task text into the next
structured `PlannedStep` via an LLM; strict schema validation of model output;
provider-agnostic interface. Keep `ScriptedPlanner` for tests.
**Non-goals:** Autonomy without approval gates (safety stays in place).
**Dependencies:** Phase 2 loop, Phase 4 perception (better context).

**Inspect before coding:** `src/desktop_worker/loop/task_loop.py` (Planner Protocol),
`src/desktop_worker/schema/actions.py`.
**Files allowed to edit:** new `src/desktop_worker/loop/ai_planner.py`, tests.
**Files forbidden to edit:** `executor.py`, `safety/`, `broker/`.
**Expected behavior:** Given a task + observation, returns a validated step or
None; malformed model output is rejected, never executed.
**Tests / validation:** `python -m pytest` with a stubbed model client.
**Manual validation:** End-to-end task with a real model + human approval.
**Rollback plan:** delete `ai_planner.py`.
**Diff budget:** 1 new file.
**Done criteria:**
- [ ] Model output validated through `parse_action`.
- [ ] Safety/approval unchanged and enforced.

---

## Excluded from this backlog
| Item | Reason |
|---|---|
| Raw shell command runner | Forbidden (requirements §11). |
| Editing `docs/requirements.md` | Read-only source of truth. |
| Multi-monitor capture | Deferred (single-monitor MVP allowed). |
| Full UI (Phase 7) | Tracked at roadmap Phase 7; cards added when reached. |
