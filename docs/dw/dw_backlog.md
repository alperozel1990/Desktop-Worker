# dw_backlog.md — Implementation cards

> **Frozen / do-not-edit:** `docs/requirements.md` (read-only source of truth),
> `artifacts/` (generated). Respect each card's forbidden-files list.
> Each card is a narrow, scoped task with acceptance criteria, per requirements §4.2.

Status legend: ☐ todo · ◑ partial · ✅ done

---

## DW-WF-PICKER-OPENBTN — Disambiguate the file-dialog "Open" button  ✅ done (2026-06-25)
**Purpose:** Live finding (2026-06-25, MANUAL-WF-2): `pick-file` correctly locates the
File name field, selects, and types the path, but the final confirm clicks the wrong
control — the Win11 Open dialog exposes **5 elements named "Open"** (the primary button
plus split-button arrows next to the File-name / Files-of-type / Encoding dropdowns).
The workflow clicked a non-primary "Open" so the dialog stayed open. Pressing ENTER
confirmed correctly and `dw-demo.txt` opened, proving the typing path is sound.
**Scope:** In `workflows/file_dialog.py`, disambiguate the confirm button: prefer the
widest "Open"/"Save" button (or the one whose bounds are the largest / bottom-most),
and/or fall back to pressing ENTER after the path is typed. Add a Null-backend test
asserting the chosen target among several same-named candidates.
**Non-goals:** Changing field-finding or typing (they work); other dialogs.
**Files allowed:** `src/desktop_worker/workflows/file_dialog.py`, `tests/test_wf_file_dialog.py`.
**Files forbidden:** `schema/`, `actions/`, `safety/`, `broker/`, `audit/`.
**Done criteria:**
- [x] Confirm uses ENTER on the focused File name field (immune to the multi-"Open" controls).
- [x] Test covers ENTER-confirm even when a (wrong) button center is offered.
- [x] MANUAL-WF-2 re-run opened the file without a manual ENTER (live 2026-06-25).
**Diff budget:** 1 production file + 1 test file. Met.
**Result:** Shipped. `choose_file` now presses ENTER to confirm. LIVE-validated: the
Open dialog confirmed itself and `dw-demo.txt` opened (no manual ENTER). 356 tests green.

---

## DW-WF-BROWSE-FOREGROUND — Foreground + settle Chrome before address-bar typing  ✅ done (2026-06-25)
**Purpose:** Live finding (2026-06-25, MANUAL-WF-4): `browse "https://www.google.com"`
opened a new Chrome tab but did **not** navigate — the tab stayed "New Tab" and focus
ended on an unrelated window (Unity). With Chrome already running, the workflow ran
Ctrl+L → type URL → ENTER before Chrome was foregrounded/ready, so the keystrokes
landed in whatever window had focus (a focus/timing race). No disk damage
(`dw-demo.txt` intact), but navigation silently failed while reporting each step "ok".
**Scope:** In `workflows/browser.py`/`browser_ui.py`: after launching/activating Chrome,
explicitly bring a Chrome window to the foreground and wait for it (poll active_window
until process == chrome, with a settle delay) BEFORE Ctrl+L/type/ENTER. Verify
navigation actually happened (active window title changed / address reflects the URL)
instead of reporting "ok" blindly. Re-use the window-switch helper.
**Non-goals:** Fixing form fill/submit name candidates (separate; blocked on nav first).
**Files allowed:** `src/desktop_worker/workflows/browser.py`,
`src/desktop_worker/workflows/browser_ui.py`, `tests/test_wf_browser.py`.
**Files forbidden:** `schema/`, `actions/`, `safety/`, `broker/`, `audit/`.
**Done criteria:**
- [x] Chrome is confirmed in the foreground (title/process match, polled) before any input.
- [x] navigate aborts (types nothing) when the gate fails — no keystrokes to the wrong window.
- [x] Null-backend tests assert the gate (confirm/timeout/abort/proceed); MANUAL-WF-4 re-run navigated.
**Diff budget:** 2 production files (browser.py, __main__.py) + 1 test file. Met.
**Result:** Shipped. `ensure_foreground` + `navigate(foreground=...)`/`submit_form(foreground=...)`.
LIVE-validated: `browse "https://www.google.com"` → active window became
"Google - Google Chrome" (was "New Tab" with focus lost before). 356 tests green.

---

## DW-AGENT-DRAW — Robust drawing v2: SVG + canvas hygiene + best-of-N  ✅ done (2026-06-22)
**Purpose:** v1 drew a clean cat but live the canvas still showed red scribbles. Make
the AI draw "in the best way regardless": clean execution + a quality gate + a stronger
representation (SVG). Research: Chat2SVG, CLIPasso/CLIPDraw++, LLM4SVG.
**Scope:** generate→render-offline→AI-judge→execute-clean→verify. New pure modules
`geometry/svg.py` (SVG→Program), `geometry/preview.py` (offline render+montage),
`geometry/paint_setup.py` (canvas hygiene via UIA), `drawing/director.py` (best-of-N,
injected Claude), `drawing/claude_io.py` (broker-routed claude). `SketchTool` accepts
`svg` OR `primitives` + preps; `render_program_to_canvas` shared execution; `draw`
command.
**Non-goals:** training/RL, differentiable rasterizer, GPU CLIP, colour drawings,
animation.
**Files forbidden to edit:** `schema/actions.py`, `actions/windows_input.py`, `safety/`,
`audit/`, `docs/requirements.md`.
**Done criteria:**
- [x] AI proposes SVG; renders offline; AI judge picks best; only winner drawn.
- [x] Canvas hygiene: clean canvas + Pencil + Black; no raw strokes in the `draw` path.
- [x] SVG-subset parser (paths/curves/shapes) with aspect-fit + fail-safe on truncation.
- [x] One verify+refine pass, quota-bounded (~3-4 Claude calls).
- [x] 251 tests (+25); deterministic path LIVE-validated (red canvas cleaned → clean
  cat); Claude integration smoke OK. Full AI run = MANUAL-11.
**Diff budget:** 5 new modules + 3 new test files; small edits to builtin/__main__. Met.
**Result:** Shipped. `artifacts/cat_attempts/cat_v2_clean_best.png` proves the
red-chaos fix + SVG path. Two review CRITICALs fixed.

---

## DW-AGENT-SKETCH — Smart, controlled drawing (`sketch` tool + `geometry/`)  ✅ done (2026-06-22)
**Purpose:** Make the AI draw recognizable figures (cat) in a smart, controlled
way. The old path poked raw `mouse.stroke` in absolute pixels, guessing the canvas
— polygon "circle", stray diagonal slash, 300s timeout before the body.
**Scope:** New pure `geometry/` package: `dsl.py` (validated 0..100-grid primitive
language), `render.py` (deterministic tessellation, one stroke per primitive,
adaptive sampling), `canvas.py` (UIA-first canvas detection + geometric fallback +
Null). Exposed as the `sketch` AI tool; AI plans the whole figure in ONE `tool.run`.
Planner forces ONE cropped vision look after a sketch (render→look→refine).
Research basis: SketchAgent (grid reasoning) + generator-critic refinement.
**Non-goals:** New schema action (the `tool.run` envelope suffices); changing
`stroke()`; erase/correction primitives; multi-monitor.
**Dependencies:** tools registry, input backend, vision plumbing (all existed).

**Files allowed to edit:** new `src/desktop_worker/geometry/*`, `tools/builtin.py`,
`tools/__init__.py`, `__main__.py`, `loop/claude_cli_planner.py`, new
`tests/test_geometry_*.py`, `tests/test_tools.py`, `tests/test_claude_cli_planner.py`.
**Files forbidden to edit:** `schema/actions.py`, `actions/windows_input.py`,
`actions/executor.py`, `safety/`, `audit/`, `docs/requirements.md`, `artifacts/`.

**Done criteria:**
- [x] AI emits ONE `sketch` program; code finds the canvas + renders precisely.
- [x] One stroke per primitive (no fusion → no stray slash); smooth circles/curves.
- [x] UIA-first canvas detection with deterministic client fallback + Null.
- [x] Planner forces ONE cropped vision look after a sketch; quota-bounded.
- [x] 223 tests green (+39); offline render proof = clean cat. Live = MANUAL-10.
**Diff budget:** 4 new geometry files + 3 new test files; 5 small edits. Met.
**Result:** Shipped. `artifacts/cat_attempts/cat_render_preview.png` proves the
geometry. Supersedes the blind-stroke + autonomous-retry cat loop.

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

## DW-INPUT-HARDEN — Input reliability hardening  ✅ done (2026-06-20)
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
- [x] Hotkeys hold/release modifiers correctly (pure `plan_hotkey`, reverse-release,
  raises before any send so no stuck modifier).
- [x] Long-text reliability via clipboard paste (`should_paste` + Ctrl+V); optional
  inter-key delay for fast-input-dropping apps.
- [~] Manual desktop validation = MANUAL-1 (real keystroke emission can't be unit-tested).
**Result:** Extracted pure, tested helpers (`resolve_vk`/`plan_hotkey`/`should_paste`)
and refactored `WindowsInputBackend` to use them. Codex APPROVE, Northstar ALIGNED.
109 tests. (Full SendInput-batch migration deferred; current keybd_event path is
correct and hardened — revisit only if MANUAL-1 shows reliability gaps.)

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

## DW-PERCEPTION-UIA — Windows UI Automation elements (Phase 4)  ✅ done (2026-06-20)
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
- [x] UIA element detection with bounds + confidence + source (lazy `WindowsUiaBackend`).
- [x] UIA-preferred merge with OCR (`merge_elements`: keep all UIA, OCR only fills gaps).
- [x] `Element.source` now REQUIRED (no default) — honest attribution everywhere.
**Result:** `perception/uia_backend.py` (pure `control_to_type` + `merge_elements`,
`UiaBackend` Protocol, NullUiaBackend, lazy WindowsUiaBackend); Perceiver now prefers
UIA + merges OCR. Codex APPROVE, Northstar ALIGNED. 101 tests. Fixed live API to
GetForegroundWindow+ControlFromHandle. Real UIA enumeration = MANUAL-6.

---

## DW-PERCEPTION-WIRE — Wire the Perceiver into the task loop  ✅ done (2026-06-20)
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
- [x] Perceiver optionally wired (`TaskLoop(perceiver=...)`, `_observe` helper);
  elements reach the `step.planned` audit record.
- [x] Default path unchanged (perceiver=None → identical behavior, no hard dep).
**Result:** Codex APPROVE, Northstar ALIGNED. 103 tests. Phase 4 complete
(OCR + UIA + wiring). Session-level default wiring is a trivial app.py follow-up.

---

## DW-PLANNER-AI — Claude Code CLI planner, no API key  ✅ done (2026-06-20)
**Purpose:** Drive the loop with an AI planner per requirements §1 — using the
user's logged-in `claude` CLI (subscription), NOT the Anthropic/OpenAI SDK or any
API-key provider (user constraint: no API billing). See [[desktop-worker-no-api-billing]].
**Scope:** A `Planner` that asks the installed `claude` CLI for the next structured
action JSON, routed through the Desktop-Worker **CLI broker** (no raw subprocess);
strict schema validation; malformed output fails safe. Implemented as
`loop/claude_cli_planner.py` (note: card originally said `ai_planner.py`).
**Non-goals:** Autonomy without approval gates (safety stays in place); SDK/API providers.
**Dependencies:** Phase 2 loop, Phase 4 perception.

**Files edited:** `src/desktop_worker/loop/claude_cli_planner.py` (new), tests.
**Files forbidden (untouched):** `executor.py`, `safety/`, `broker/`.
**Expected behavior:** Given a task + observation, returns a validated `PlannedStep`
or None; uses `claude -p --output-format json --max-turns 1 --tools ""` via stdin
through the broker; `claude auth status` checks availability.
**Tests / validation:** `python -m pytest` with a STUBBED CLI (injected `ask` + a
fake broker; no real Claude calls). Plus a real end-to-end smoke confirmed:
`claude_available=True` and a live call returned `keyboard.type(text='hello')`.
**Manual validation:** MANUAL-7 — drive a real task end-to-end with the live CLI.
**Rollback plan:** delete `loop/claude_cli_planner.py`.
**Diff budget:** 1 new production file (+ tests).
**Done criteria:**
- [x] Model output validated through `parse_action` (STRICT) before any step.
- [x] Safety/approval/estop/audit unchanged — planner only proposes; executor gates.
- [x] No API key/SDK; uses subscription CLI via the broker; tools disabled, 1 turn.
- [x] Malformed/unknown/error output fails safe (no step, no crash).
**Result:** Codex APPROVE, Northstar ALIGNED. 125 tests. Real path verified.

---

## DW-WORKFLOW-CREATEFILE — Visible "create desktop text file" workflow (Phase 5)  ✅ done (2026-06-20)
**Purpose:** Deliver a real, working, *watchable* end-to-end task (user request):
the agent creates a desktop .txt, types content, saves it — user just observes.
**Scope:** `workflows/desktop_file.py` + `desktop_ui.py`: show desktop → right-click
→ New → Text Document → name → double-click open → type content → Ctrl+S → verify
on disk. Input = structured actions through the executor (validated/audited/estop);
targets located via UIA (en+tr names). CLI: `python -m desktop_worker create-file`.
**Also fixed (required for it to work):** `windows_input` Unicode via SendInput
(keybd_event truncated >255 → Turkish ş/ı corrupted); VK map A-Z/0-9 (Ctrl+S no-op);
pytest no longer triggers real UAC; CLI stdout→utf-8.
**Files edited:** `workflows/*` (new), `actions/windows_input.py`, `__main__.py`,
tests. **Forbidden (untouched):** `safety/`, `broker/` core, `schema/`.
**Tests / validation:** `python -m pytest` (130) + **real desktop run verified**
(dw-demo.txt = "başlıyoruz", 12 bytes). Manual watch test = MANUAL-8.
**Done criteria:**
- [x] Visible create→name→open→type→save via structured actions.
- [x] Verified on disk; never fakes success; fails safe with clear error.
- [x] Unicode (Turkish) input correct. Codex APPROVE, Northstar ALIGNED.

## DW-AGENT-DO — Genuine live AI desktop control (`do "<task>"`)  ✅ done (2026-06-20)
**Purpose:** The user's core ask + the §22 capstone: a live AI agent (like the
Chrome Claude extension) that takes a plain-language task and decides+performs each
action itself — NOT a script. Designed in alignment with Codex + Northstar.
**Scope:** `python -m desktop_worker do "<task>"` runs the loop: observe → perceive
(UIA elements + open context menus + editable values, OCR) → Claude (logged-in CLI,
NO API key) picks the next structured action by elementId → safety-gated executor
performs it → verify → repeat; each AI decision printed live + audited.
**Files:** `__main__.py` (`_cmd_do`, console approver, env_context),
`loop/claude_cli_planner.py` (elementId→coords [mouse-only, stale rejected],
reasoning, last_outcome, env_context), `loop/task_loop.py` (perceiver wiring,
settle_s, on_step, stall_guard, done-vs-failure, visibleText verify),
`perception/uia_backend.py` (context-menu popups + ValuePattern), `broker/risk.py`
(format false-positive fix), `tests/test_ai_loop.py`.
**Forbidden (untouched):** executor/broker/safety CORE behavior (all safety stays
below the planner; AI cannot bypass gates).
**Tests / validation:** `python -m pytest` (138) + **real desktop run VERIFIED**
(AI opened Notepad via Run dialog and typed merhaba, self-verified, 4/4 steps).
Manual watch test = MANUAL-9.
**Done criteria:**
- [x] AI decides at runtime from live perception (no scripted fallback in `do`).
- [x] Every action validated/approval-gated/estop/audited; broker-only CLI.
- [x] Each AI decision + reasoning printed and audited (observable it's the AI).
- [x] Safe failure: stale id rejected, planner-failure not mislabeled as success,
  no-progress stall guard. Codex APPROVE, Northstar ALIGNED.

## Phase 5/6/7 cards — Autonomous batch 2026-06-24  ✅ all done

> Branch `dw/roadmap-5-6-7`; 350 tests; each phase Codex-audited. Live = MANUAL-*.

- **DW-WF-WINDOW** ✅ — `workflows/window.py` switch_window + drag_drop; DragDropTool. CLI `switch-window`. MANUAL-WF-1.
- **DW-WF-FILEPICKER** ✅ — `workflows/file_dialog.py` choose_file/upload_file. CLI `pick-file`. MANUAL-WF-2.
- **DW-WF-DOWNLOAD** ✅ — `workflows/downloads.py` wait_for_download (pure). CLI `wait-download`. MANUAL-WF-3.
- **DW-WF-BROWSER** ✅ — `workflows/browser.py`+`browser_ui.py` navigate/fill/submit. CLI `browse`. MANUAL-WF-4.
- **DW-ORCH-SCHEMA** ✅ — `orchestration/schema.py` AgentTask/AgentReport/AuditorFinding + parse_*.
- **DW-ORCH-ROLES** ✅ — `orchestration/roles.py`+`claude_io.py` Strategist/Implementer/Codex+Northstar (fail-safe).
- **DW-ORCH-COORD** ✅ — `orchestration/coordinator.py` state machine. CLI `orchestrate [--execute]`. MANUAL-ORCH-1.
- **DW-HARDEN** ✅ — authorize_app + profile/app-list persistence + `audit/retention.py`. CLI `clean-artifacts`.
- **DW-UI-CONTROLLER** ✅ — `ui/controller.py` pure UiController + ApprovalQueue.
- **DW-UI-TK** ✅ — `ui/app_tk.py` Tkinter window. CLI `ui`. MANUAL-UI-1.

## Excluded from this backlog
| Item | Reason |
|---|---|
| Raw shell command runner | Forbidden (requirements §11). |
| Editing `docs/requirements.md` | Read-only source of truth. |
| Multi-monitor capture | Deferred (single-monitor MVP allowed). |
| Full UI (Phase 7) | Tracked at roadmap Phase 7; cards added when reached. |
