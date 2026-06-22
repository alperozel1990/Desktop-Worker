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

---

## 2026-06-20 | Execute | Task: DW-PLANNER-AI

**Task ID:** DW-PLANNER-AI
**Type:** Execute (capstone — AI planner)
**Status:** Complete

**User decision:** No API billing. Use the logged-in `claude` CLI (subscription),
not the Anthropic/OpenAI SDK. Routed through the broker.

**Files Created:** `src/desktop_worker/loop/claude_cli_planner.py`,
`tests/test_claude_cli_planner.py`. (Memory: `desktop-worker-no-api-billing`.)
**Files Modified:** continuity files (state/memory/backlog/roadmap/tracker/manual_steps/capabilities).

**Tests / Validations Run:** `python -m pytest` → **125 passed** (+17, stubbed CLI).
Real end-to-end smoke: `claude auth status` → loggedIn; planner returned a valid
`keyboard.type(text='hello')` for a sample task; both `claude` calls audited via broker.

**Validation Level Reached:** **3** (unit) + **4** for the planner→broker→claude path
(real model, real CLI, real broker). Full multi-step task on the desktop = MANUAL-7.

**Result:** `ClaudeCliPlanner` asks the installed `claude` CLI for the next
structured-action JSON (`claude -p --output-format json --max-turns 1 --tools ""`,
prompt via stdin) through the CLI broker — no raw subprocess, no API key/SDK, no
billing. Output is strictly validated by `parse_action`; malformed/unknown/error
output yields no step (safe-stop) and never executes. The planner only PROPOSES;
the executor still validates, approval-gates, estop-checks, and audits. Both auditors
APPROVE/ALIGNED. Applied review nits: prefer the answer JSON object over stray prose;
added `elevated=False`/stdin/`claude_available` tests; fixed `cli_dir=None` fallback.

**Risks Introduced:** Planner's own `claude` call classifies LOW so it runs each step
without approval (intended; still audited + estop-able). Real CLI flag/output contract
pinned by smoke test, not unit tests.
**Risks Resolved:** AI-control-ready core complete without API billing.

**Next Action:** New cards for Phase 5 (browser/desktop workflows), Phase 6
(multi-agent), Phase 7 (UI). All 7 original backlog cards are done.

---

## 2026-06-20 | Execute | Task: DW-WORKFLOW-CREATEFILE (Phase 5) + input Unicode fix

**Task ID:** DW-WORKFLOW-CREATEFILE
**Type:** Execute (Phase 5 — first real desktop workflow) — user-requested working demo
**Status:** Complete — VERIFIED on the real desktop (Validation Level 4)

**User goal:** one command where the agent visibly creates a desktop text file
(right-click → New → Text Document), names it, opens it, types "başlıyoruz", saves it.

**Files Created:** `workflows/__init__.py`, `workflows/desktop_ui.py`,
`workflows/desktop_file.py`, `tests/test_workflow_desktop_file.py`.
**Files Modified:** `actions/windows_input.py` (CRITICAL FIX), `__main__.py`
(`create-file` command + utf-8 stdout), `tests/test_cli_broker.py` (no real UAC in
tests), `tests/test_perception_ocr.py` (UIA isolation); continuity files.

**Critical fix (root cause):** `type_text` used `keybd_event`, whose scan param is a
BYTE, so Unicode > 255 was truncated (Turkish ş U+015F→'_', ı U+0131→'1'). Rewrote
Unicode typing to use **SendInput** with a 16-bit `wScan` + surrogate pairs. Also
added full A-Z/0-9 to the VK map (Ctrl+S was a silent no-op — 'S' was missing).
Also fixed: pytest triggered 5-6 real UAC prompts (tests now never build the real
elevator); cp1252 console crash when printing Turkish (stdout→utf-8).

**Tests / Validations Run:** `python -m pytest` → **130 passed** (+5). **Real
end-to-end:** `python -m desktop_worker create-file` created
`...\OneDrive\Desktop\dw-demo.txt` = exactly "başlıyoruz" (12 bytes, hex
6261c59f6cc4b1796f72757a); report 11/11 steps OK + "verified content on disk".

**Validation Level Reached:** **4** (real desktop, verified on disk) for this workflow.

**Result:** First Phase 5 workflow. Input is structured actions through the
executor (validated/audited/estop-gated); targets located via UIA; success gated
on real on-disk bytes (never fakes success; retries once; fails safe with a clear
error). Codex APPROVE, Northstar ALIGNED. The modern-Notepad session caveat is
handled by verify+retry. User test = MANUAL-8 (just run the command and watch).

**Risks Introduced:** None blocking. Reliability depends on UIA menu names
(en+tr covered) + Notepad focus (verify+retry mitigates).
**Risks Resolved:** Unicode input truncation; Ctrl+S no-op; pytest UAC prompts;
console Unicode crash.

**Next Action:** Optional — extend workflows (browser/forms, Phase 5 cont.), or
let the AI planner orchestrate workflows. None blocking.

---

## 2026-06-20 | Execute | Task: DW-AGENT-DO — GENUINE live AI desktop control

**Task ID:** DW-AGENT-DO
**Type:** Execute (the §22 capstone realized) — user-requested "real AI control"
**Status:** Complete — VERIFIED on the real desktop (Validation Level 4)

**User goal:** not a script — a live AI agent (like the Chrome Claude extension)
that takes a plain-language task and decides+performs each action itself.
Designed in alignment with Codex + Northstar (both gave DESIGN verdicts first).

**Command:** `python -m desktop_worker do "<task>"`. Loop: observe → perceive
(UIA elements + context menus + values, OCR) → ask Claude (logged-in CLI, NO API
key) for the next structured action → safety-gated executor performs it → verify
→ repeat. Each AI decision + reasoning is printed live and audited.

**Files Created:** `tests/test_ai_loop.py`.
**Files Modified:** `__main__.py` (`do` command + console approver + env_context),
`loop/claude_cli_planner.py` (elementId→coords resolution [mouse-only; stale id
rejected], reasoning + last_outcome, env_context), `loop/task_loop.py` (perceiver
wiring, settle_s, on_step, stall_guard, done-vs-failure outcome, visibleTextContains
verify), `perception/uia_backend.py` (context-menu popups + editable-control VALUES
so the AI sees what it typed), `broker/risk.py` (fixed `--output-format`→`format`
false positive that blocked the AI's own claude call); continuity files.

**Tests / Validations Run:** `python -m pytest` → **138 passed** (+8). **Real
end-to-end:** `do "Open Notepad using the Run dialog, then type merhaba"` → the AI
autonomously did WIN+R → type notepad → ENTER → type merhaba, self-verified by
reading Notepad's content, returned done. Completed=True, 4/4 steps, each decision
printed + audited.

**Validation Level Reached:** **4** (real desktop, live AI, verified).

**Result:** Desktop-Worker is now genuinely AI-control-ready (§22): the AI is the
decision-maker in the loop, improvising structured actions against live perception,
while ALL safety stays below the planner (executor validates/approves/estop/audits;
broker-only CLI; high-risk prompts on TTY / denied headless). **Auditors:** Codex
APPROVE, Northstar ALIGNED. Applied review fix: stale/unknown elementId is rejected
(no misclick). The deterministic `create-file` workflow remains as a separate
reliable command; `do` never silently delegates to it.

**Risks Introduced:** Reliability depends on UIA quality — UIA-poor apps
(Electron/Chromium/custom-drawn) expose few elements, degrading to OCR/coords.
The model must follow guidance to not `cli.run` GUI apps (env_context steers it).
**Risks Resolved:** classifier false positive; AI misclick on stale id; no-feedback
typing loop (value-capture); failure-mislabeled-as-success.

**Next Action:** Optional — expose deterministic workflows as AI-callable tools
(brain+hands, Northstar's next increment); vision fallback for UIA-poor apps;
Phase 6 multi-agent; Phase 7 UI with live approve/deny. User test = MANUAL-9.

---

## 2026-06-20 | Execute | Task: DW-AGENT-MEMORY — action/outcome memory (fix loop)

**Task ID:** DW-AGENT-MEMORY
**Type:** Execute (refine DW-AGENT-DO) — user feedback: "AI doesn't notice its own
mistakes; it should remember what it tried and the results — don't write heuristics."
**Status:** Complete — VERIFIED on the real desktop (Level 4)

**Problem:** The AI looped sending CTRL+A in the Run dialog. Root cause: the planner's
history was only "keyboard.hotkey: ok" — so 3 ineffective CTRL+A's all looked like
success; the AI had no memory of *effects*. An earlier heuristic ("you're stuck"
hint injected by the loop) was the wrong fix (user rightly rejected it).

**Fix:** Removed the heuristic entirely. Added genuine action/outcome memory: the
loop records per step `actionStr`, `screenChanged` (observation-signature diff
before vs after), and the AI's own `reasoning`; `build_planner_prompt` shows the
last 8 as "what you tried [you reasoned: ...] => effect" (ERROR / no visible effect
/ screen changed), instructing the AI not to repeat ineffective actions. The
stall-stop is kept only as a final safety backstop (6 unchanged observations).

**Files Modified:** `loop/task_loop.py` (record memory; PlannedStep.reasoning;
backstop), `loop/claude_cli_planner.py` (render memory; removed progress_note),
`tests/test_ai_loop.py`; continuity files.

**Tests / Validations:** `python -m pytest` → **139 passed**. **Real run VERIFIED:**
`do "open the Calculator and compute 12 times 9"` — the AI did WIN+R → CTRL+A →
then (NO loop) reasoned "'notepad' is selected, type 'calc'" → launched Calculator
→ typed 12*9= → self-verified "Display is 108". Completed, 5/5, correct (108).

**Result:** Genuine agent memory — the AI reasons over its own action/result trace
and self-corrects, no heuristic spoon-feeding. Codex APPROVE, Northstar ALIGNED.

**Next Action:** Optional, as above. None blocking.

---

## 2026-06-21 | Execute | Task: DW-AGENT-VISION — vision fallback for UIA-poor apps

**Task ID:** DW-AGENT-VISION
**Type:** Execute (extend DW-AGENT-DO) — user chose "add vision" as next priority
**Status:** Complete — vision capability proven; full loop not run live (conserve quota)

**Goal:** Make the live AI agent work on apps where Windows UI Automation exposes
few elements (Electron/Chromium, games, custom UIs) by letting Claude SEE a
screenshot. Cost-aware: a vision step costs ~$0.27 vs ~$0.05 text-only (verified),
and the user recently hit a Claude usage limit — so vision is an adaptive,
capped FALLBACK, off by default.

**How:** `do "<task>" --vision`. The planner attaches a screenshot only when the
UIA element list is sparse (< threshold) AND a real .png exists, capped at
`max_vision_steps` (default 6) per task, then text-only. Vision steps switch the
claude flags from `--tools ""` to `--max-turns 2 --allowedTools Read` (ONLY the
read-only Read tool, one extra turn to view the image); the planner still only
PROPOSES — the executor validates/gates/estop/audits every real action. Audit
records `vision: true/false` per step; the CLI prints the cost note + vision-step count.

**Files Modified:** `loop/claude_cli_planner.py` (vision flag/threshold/cap,
`_vision_path`/`_activate_vision`, flag-switch, screenshot in prompt),
`__main__.py` (`--vision` + cost note + count), `tests/test_ai_loop.py`.

**Tests / Validations:** `python -m pytest` → **143 passed** (+4). Vision capability
PROVEN standalone: `claude -p --max-turns 2 --allowedTools Read` read a real
screenshot and accurately described it. Full `do --vision` loop deliberately NOT
run end-to-end to conserve the user's Claude quota.

**Validation Level Reached:** 3 (unit) + vision-read capability proven (real claude).

**Result:** The agent can now fall back to vision on apps UIA can't describe, with
cost controlled (off by default, sparse-only, hard step cap, audited). Codex
APPROVE, Northstar ALIGNED. Applied review fixes: per-task vision-step cap + audit
`vision` flag + clearer realistic cost note.

**Risks Introduced:** Vision steps cost more Claude usage; capped + disclosed.
`--allowedTools Read` lets Claude read local files during planning (read-only; can't
act; the screenshot may capture sensitive screen content) — disclosed.
**Risks Resolved:** Agent no longer blind on UIA-poor apps (when --vision on).

**Next Action:** Optional — workflows as AI-callable tools; frugal mode; Phase 6/7.
User can run `do --vision "<task>"` on an Electron/Chromium app to validate live.

---

## 2026-06-21 | Execute | Task: DW-AGENT-TOOLS — AI-callable reliable tools (brain+hands)

**Task ID:** DW-AGENT-TOOLS
**Type:** Execute (extend DW-AGENT-DO) — user chose "make workflows AI-callable tools"
**Status:** Complete — VERIFIED live (AI chose the tool; content correct on disk)

**Goal (Northstar's "AI brain + reliable hands"):** let the live AI agent CALL a
deterministic, verified tool in ONE step for known tasks, instead of improvising
many fragile GUI actions — cheaper (fewer Claude calls) + reliable. Raw actions
stay available; the AI decides.

**Design (aligned with Codex + Northstar FIRST):** new `tool.run` action
(`{tool, args}`), a `ToolRegistry`, one MVP tool `create_text_file`. Routed THROUGH
the executor so it stays the single audited/estop-gated choke point. Codex must-haves
all implemented: schema row; `_dispatch` raises on unknown/failed tool (fail safe);
per-tool risk (unknown⇒HIGH, create_text_file⇒MEDIUM) via the registry; arg
sanitization (reject path separators/`..`/absolute filenames, bound content);
nesting guard (a tool can't call tool.run); audit + visible tool calls.

**Key reliability fix:** the first live run had the AI correctly CALL the tool, but
the tool mimicked the flaky GUI right-click flow and corrupted content ("tool
worked"→"tool dddddd"; the AI even detected it). Rewrote the tool to be genuinely
reliable: it WRITES the content to disk (verified) and opens it in Notepad via the
broker — a tool must guarantee its result, not replay a flaky GUI (the flaky GUI
stays in the separate `create-file` demo).

**Files Created:** `tools/__init__.py`, `tools/registry.py`, `tools/builtin.py`,
`tests/test_tools.py`. **Files Modified:** `schema/actions.py` (tool.run row),
`actions/executor.py` (tool dispatch + per-tool risk + nesting guard + estop prop),
`loop/claude_cli_planner.py` (tool catalog in prompt), `__main__.py` (wire registry),
`tests/test_actions_schema.py`.

**Tests / Validations:** `python -m pytest` → **157 passed** (+14). **Real run
VERIFIED:** `do "create a text file on the desktop named ai-tool-demo containing
'tool worked'"` → AI reasoned "the create_text_file tool matches this task, call it"
→ tool.run → file on disk contains exactly "tool worked". Tool also unit-tested for
exact + unicode content.

**Validation Level Reached:** **4** (real desktop, AI chose tool, verified on disk).

**Result:** "AI brain + reliable hands" works — the AI picks the right tool and the
tool guarantees the result. Codex APPROVE, Northstar ALIGNED. Raw actions intact;
no plugin framework (one tool MVP, by design).

**Risks Introduced:** None blocking. A tool writes a file directly (audited via the
tool.run entry) — acceptable per the "verified file write" tool model.
**Risks Resolved:** GUI-typing content corruption (tool no longer uses flaky GUI).

**Next Action:** Optional — more tools (open app, web form), frugal mode, Phase 6/7.

---

## 2026-06-21 | Execute | Batch: autonomous session (user away, auditor-gated)

User granted autonomy: "do the remaining items in sequence; Codex + Northstar
approval is enough; don't ask me to test." Each card below: built → unit-tested →
Codex+Northstar APPROVE/ALIGNED → committed. No live human test required.

**DW-TOOL-OPENAPP** (commit 77521b8): `open_app` tool — open a known app via a
curated allowlist (shells excluded, unknown rejected, no injection) through the
broker's non-blocking `start`. risk MEDIUM. VERIFIED: launched Calculator in 0.4s.

**DW-TOOL-OPENURL** (commit 2103129): `open_url` tool — open an http(s) URL in the
default browser. Strict URL sanitizer (`^https?://[^\s"%<>]+$`); Codex empirically
verified NO command-injection path (quoting safe; depends on no cmd /V:ON). risk MEDIUM.

**DW-REPLAY** (commit 09b364f): session replay — `audit/report.py` turns the audit
JSONL into a standalone HTML timeline (every AI decision + reasoning + action +
result). All fields HTML-escaped (no injection). `do` auto-writes replay.html
(best-effort); new `report --session --task` command. §16 audit viewer + §17 reports.

**DW-FRUGAL** (commit 2a94559): `do --frugal` — leaner prompts (max_elements 40→12,
history 8→4) to use less Claude usage per step. Prompt-only; no capability/safety
change; default behavior byte-identical.

**DW-TOOL-FOCUS** (commit f5233fb): `focus_window` tool — bring a window to front by
title (pure matcher tested; ctypes enum/focus injectable). risk LOW. VERIFIED: focused
a real window among 14 enumerated.

**DW-PROFILES** (commit 8b53fce): `do --profile {standard|strict|headless}` —
selectable safety presets (§12). standard == prior behavior; strict prompts MEDIUM+
(tool calls, window focus, risky CLI); headless denies anything needing approval.

**DW-VERIFY-FILE** (commit 6590112): loop `_verify` gains `fileExists` so the AI can
confirm a file task produced the file on disk.

**DW-README + DW-INTEGRATION** (commits 91f9d9a, 7cd09cf): refreshed README for the
full capability set; added a full-stack integration test (stubbed AI planner →
loop+perceiver → executor → tool.run → reliable tool writes+verifies file → audit →
HTML replay; plus emergency-stop-halts case).

**Tests:** 165 → **184 passed**. **Tool library: create_text_file, open_app,
open_url, focus_window** — the AI picks the right reliable tool in one step.
Plus: `--vision` fallback, `--frugal` mode, `--profile` presets, session-replay HTML.

**Validation Level:** 3 (unit) for all; open_app/focus_window also live-sanity-checked;
the live `do` agent itself is L4-verified (earlier).

**Next Action:** Optional — Phase 6 multi-agent, a real UI (Phase 7), or more tools.
None blocking. The agent is feature-complete for the core north-star.

---

## 2026-06-22 | Smart, controlled drawing (`sketch` tool) | Task: DW-AGENT-SKETCH

**Type:** Phase 5 capability (AI-callable tool) + perception (canvas detection)
**Status:** Complete (offline-verified; live Paint = MANUAL-10)

**Why:** The AI drew a cat by poking raw `mouse.stroke` in absolute screen pixels,
guessing the canvas from window bounds — yielding a polygon "circle", a stray
diagonal slash across the face, and a 300s/15-action timeout before the body.
Research-backed fix (SketchAgent grid reasoning + generator-critic render→look→
refine, deterministic vector tessellation): plan the WHOLE figure once on a 0..100
grid; deterministic code finds Paint's real canvas and renders precise primitives.

**Files Created:**
- `src/desktop_worker/geometry/{__init__,dsl,render,canvas}.py` — pure DSL +
  tessellation + UIA-first canvas locator (Null/Windows backends, lazy ctypes/PIL).
- `tests/test_geometry_{render,dsl,canvas}.py` (+23 tests).

**Files Modified:**
- `tools/builtin.py` (+`tools/__init__.py`) — new `SketchTool` (risk=low): parse →
  locate canvas → compile → one stroke per primitive via the existing input
  backend, estop checked before each stroke.
- `__main__.py` `_cmd_do` — register `SketchTool`; swapped the "estimate the canvas,
  expect rough results" guidance for grid-reasoning + a 7-primitive reference.
- `loop/claude_cli_planner.py` — `_drew_last` now forces ONE vision look after a
  `tool.run sketch`; the critique screenshot is cropped to the canvas rect.
- `tests/test_tools.py`, `tests/test_claude_cli_planner.py` (+ sketch/vision tests).

**Explicitly NOT touched:** `schema/actions.py` (the `tool.run` envelope suffices —
no new action), `actions/windows_input.py` (`stroke()` reused as-is), executor,
stall-guard.

**Tests / Validations Run:**
- `python -m pytest` — **223 passed** (was 184).
- Offline render proof: compiled the cat program against an 800x600 canvas and drew
  the resulting strokes to `artifacts/cat_attempts/cat_render_preview.png` — a clean,
  recognizable cat (smooth circle head, 2 ears, 2 eyes, nose, arc mouth, whiskers,
  body ellipse, bezier tail), NO stray slash. This IS the geometry the mouse draws.

**Validation Level Reached:** **3** (unit + offline geometry render). Live mouse
drawing in real Paint (Level 4) = **MANUAL-10**.

**Next Action:** Run MANUAL-10 to confirm the figure lands inside Paint's canvas on
the user's machine (report Paint version + audit `canvasSource` if offset). Then
optional: erase/correction primitives, multi-figure scenes, Phase 6/7.

---

## 2026-06-22 | LIVE cat validated + 2 observation fixes | Task: DW-AGENT-SKETCH (follow-up)

**Type:** Live validation (Level 4) + two real-world fixes found by observing Paint
**Status:** Complete — autonomous session while user away (no Claude quota used)

**What ran:** Drove the `sketch` tool against REAL Win11 Paint with the real
`WindowsInputBackend` + real `WindowsCanvasLocator` (UIA). The actual mouse drew a
clean, recognizable cat — round head, 2 ears, 2 eyes, nose, smiling arc mouth,
whiskers, body ellipse, curved tail; NO stray slash, circles round.
Artifacts: `artifacts/cat_attempts/cat_live_best.png` (+ `_crop`, and iterations
`cat_live_1/2/3_*`). Incidentally validated MANUAL-1 (real input), MANUAL-2 (real
screenshots), MANUAL-6 (real UIA) too.

**Two fixes discovered by OBSERVING the live result:**
1. **Aspect ratio** — a wide canvas stretched circles into ellipses (the 0..100 grid
   maps x/y independently). Added `geometry.canvas.fit_square` and draw into the
   centered square + 5% margin (`SketchTool`). Circles stay round; figure clears the
   ribbon/edges. +1 test (`test_fit_square_centers_and_preserves_aspect`).
2. **Tool mode** — after Select-All/clear, Paint stays on the SELECT tool, so strokes
   made selections instead of ink. The live `do` guidance (`__main__` env_context) now
   tells the AI to ensure a drawing tool (Pencil/Brush) is selected before sketching.

**Tests:** `python -m pytest` — **224 passed**.

**Validation Level Reached:** **4 (live real desktop)** for the deterministic `sketch`
path. The remaining MANUAL-10 is just watching the AI-DRIVEN `do` version once.

**Next Action:** Optional — let the AI plan the program itself (`do "...draw a cat"
--vision`, a little quota) to confirm end-to-end; add erase/correction primitives;
expose a line-thickness/tool hint. None blocking.
