# dw_state.md — Authoritative state file

> Update after every task. This file — not chat history — is the source of truth
> for "where are we".

## Session info
- **Last updated:** 2026-06-30
- **Repo path:** `C:\Desktop-Worker`
- **Workspace path:** `C:\Desktop-Worker\docs\dw`
- **Current branch:** `dw/phase8-mcp` (Phase 8 MCP server; NOT pushed)
- **Remote:** `origin` → https://github.com/alperozel1990/Desktop-Worker.git
- **Last commit hash:** pushed to origin/main (see `dw_changelog.md` for hashes)
- **Operating model:** autonomous per-card execution gated by **Codex Auditor**
  (code) + **Northstar Auditor** (direction) sign-off; pause only for items the
  user must physically test (live input, UAC, browser, Tesseract).

## Implementation allowed
**YES — scoped.** User explicitly authorized building the Phase 1 minimal
working foundation during bootstrap. Future cards: follow the Pre-Implementation
Gate and only implement when the selected card is explicitly approved.

## Assumed defaults (inferred without asking)
- Task file prefix: `dw`. Workspace: `docs/dw/`.
- Python 3.11+ target (dev machine 3.14.0). Core has zero runtime deps.
- Single-monitor MVP acceptable for now (requirements §6 allows it).
- HTML tracker: yes. Elevated `.bat` launchers: yes. Commit/push: no.
- Approval model headless = deny-by-default; demo uses auto-approve to show the path.

## Current repo status
| Feature area | Status |
|---|---|
| Action schema (structured, validated) | complete |
| Observation schema + Observer | complete |
| Result records (action/cli/verification) | complete |
| Emergency stop + pause | complete |
| Permission/risk policy + limits | complete |
| Audit log (JSONL + redaction) | complete |
| CLI risk classifier | complete |
| Elevated CLI broker (capture/preview/approval/audit) | complete |
| Per-command UAC re-elevation w/ captured output | complete (DW-CLI-ELEVATE); real UAC = MANUAL-4 |
| Desktop observation backend (Windows + Null) | complete (single-monitor) |
| Input backend (Windows + Null) | complete + hardened (DW-INPUT-HARDEN); real motion = MANUAL-1 |
| Action executor | complete |
| Observe-plan-act-verify-log loop | complete (scripted planner) |
| Loop recovery / retry / re-plan / time limit | complete (DW-LOOP-RECOVERY) |
| Perception — OCR (elements, schema, Perceiver) | complete (DW-PERCEPTION-OCR); real OCR = MANUAL-5 |
| Perception — UI Automation (elements, UIA-preferred merge) | complete (DW-PERCEPTION-UIA); real UIA = MANUAL-6 |
| Perception — loop wiring (elements → audit/AI) | complete (DW-PERCEPTION-WIRE) |
| Browser/desktop workflows | complete (Phase 5): window/drag, file picker, download, Chrome form; live = MANUAL-WF-1..4 |
| Multi-agent orchestration | complete (Phase 6): schema + roles + coordinator; `orchestrate` CLI; live = MANUAL-ORCH-1 |
| UI (inspect/control) | complete (Phase 7): Tkinter control window over a pure controller; `ui` CLI; GUI = MANUAL-UI-1 |
| Hardening: app allow/deny + profile persistence + artifact retention | complete (Phase 7, DW-HARDEN) |
| AI planner (Claude Code CLI, no API key, via broker) | complete (DW-PLANNER-AI); real path verified, full task = MANUAL-7 |
| Phase 5 workflow: create desktop text file (visible) | complete (DW-WORKFLOW-CREATEFILE); VERIFIED real desktop |
| Input Unicode (Turkish ş/ı) via SendInput | fixed (was keybd_event byte-truncation) |
| **GENUINE live AI control** (`do "<task>"`) | complete (DW-AGENT-DO); VERIFIED real desktop |
| Perception: context menus + editable values | complete (AI sees menus + what it typed) |
| AI action/outcome memory + vision fallback (`--vision`) | complete (DW-AGENT-MEMORY / VISION) |
| AI-callable tools: create_text_file, open_app, open_url, focus_window | complete (DW-AGENT-TOOLS+) |
| Smart drawing: `sketch` tool + `geometry/` (DSL, renderer, canvas detection) | complete (DW-AGENT-SKETCH); LIVE-validated |
| Drawing v2: SVG + canvas hygiene + best-of-N `draw` command (`drawing/`) | complete (DW-AGENT-DRAW); deterministic path LIVE-validated, AI best-of-N = MANUAL-11 |
| Frugal mode (`--frugal`) | complete (leaner prompts, less Claude usage) |
| Session replay HTML (`report` cmd + auto) | complete (DW-REPLAY); §16 audit viewer |
| **External AI interface — MCP server** (`mcp` CLI) | complete (Phase 8, DW-MCP-SERVER); pure AgentBridge + thin FastMCP; live external client = MANUAL-MCP-1 |

## Last completed task
- **Task:** DW-PLANNER-AI — Claude Code CLI planner (no API key), via the broker.
- **Date:** 2026-06-20.
- **Summary:** `loop/claude_cli_planner.py` drives the loop using the logged-in
  `claude` CLI (subscription) through the broker — `claude -p --output-format json
  --max-turns 1 --tools ""`, prompt via stdin. Strict `parse_action` validation;
  malformed output fails safe. Tests stub the CLI. **Real path verified**
  (`claude_available=True`; live call → `keyboard.type(text='hello')`). Codex
  APPROVE, Northstar ALIGNED. 125 tests (+17). Full task end-to-end = MANUAL-7.
- **Files:** `loop/claude_cli_planner.py` (new), `tests/test_claude_cli_planner.py`.

## Current task
None in progress. (Just completed DW-MCP-SERVER — Phase 8.)

## Last completed task (2026-06-30) — Phase 8: MCP server (DW-MCP-SERVER)
- **What:** Made Desktop-Worker usable BY OTHER AI AGENTS via an MCP (stdio) server —
  the user's new north-star ("another AI couldn't use this tool"). New `mcp_server/`
  package: pure dependency-free `AgentBridge` (maps observe/perceive/screenshot/mouse+
  keyboard+clipboard/`act`/`run_tool`/`run_cli`/status/estop onto the SAME audited,
  estop-gated, policy-checked `executor.execute(parse_action(...))` path — the external
  AI becomes the planner, all safety stays below) + thin `server.py` (lazy FastMCP;
  `register()` is SDK-free + fake-server-tested) + new `mcp` CLI command + `[mcp]` extra.
- **Tests:** 373 (372 pass + 1 skip), +17. **Validation level: 3+** — Null-backend unit
  tests AND a real-FastMCP in-process e2e smoke (22 tools; observe/click/list_tools work;
  malformed action rejected; emergency_stop halts following actions). Live external client
  = MANUAL-MCP-1.
- **Files:** new `src/desktop_worker/mcp_server/{__init__,bridge,server}.py`; changed
  `__main__.py`, `pyproject.toml`; new `tests/test_mcp_bridge.py`,
  `tests/test_mcp_server_register.py`. Branch `dw/phase8-mcp`, NOT pushed.

## Most recent batch (2026-06-24) — Phases 5→6→7 complete (10 cards)
- **What:** Autonomous overnight run on branch `dw/roadmap-5-6-7` (13 commits).
  Implemented ALL remaining roadmap phases: Phase 5 browser/desktop workflows
  (DW-WF-WINDOW/FILEPICKER/DOWNLOAD/BROWSER), Phase 6 multi-agent orchestration
  (DW-ORCH-SCHEMA/ROLES/COORD, new `orchestration/`), Phase 7 hardening + UI
  (DW-HARDEN, DW-UI-CONTROLLER, DW-UI-TK with Tkinter `ui` command).
- **Tests:** **350 pass** (+99). Each card Null-backend unit-tested; each phase
  passed a Codex (code-reviewer) audit with findings fixed.
- **New CLI:** `switch-window`, `pick-file`, `wait-download`, `browse`,
  `orchestrate [--execute]`, `clean-artifacts`, `ui`.
- **Status:** committed locally; **NOT pushed** (awaiting user approval). Live
  validation pending: MANUAL-WF-1..4, MANUAL-ORCH-1, MANUAL-UI-1.

## Most recent task (2026-06-22) — Drawing v2
- **Task:** DW-AGENT-DRAW — robust, best-of-N, multi-representation drawing. New
  `geometry/svg.py` (SVG→Program), `geometry/preview.py` (offline render+montage),
  `geometry/paint_setup.py` (canvas hygiene: clean canvas + Pencil + Black via UIA),
  `drawing/director.py` (generate→render→AI-judge→execute-clean→verify; Claude calls
  injected), `drawing/claude_io.py` (broker-routed claude). `SketchTool` now accepts
  `svg` OR `primitives` and preps the canvas. New command:
  `python -m desktop_worker draw "<subject>"`. **251 tests** (+25). LIVE-validated the
  deterministic path (cleaned the red-scribbled canvas → clean SVG cat in real Paint,
  `cat_v2_clean_best.png`); Claude integration smoke OK. Full AI run = MANUAL-11.
  Fixes the "red scribbles" gap: canvas hygiene + no raw strokes in the `draw` path.
- **Files:** `geometry/{svg,preview,paint_setup}.py`, `drawing/{__init__,director,
  claude_io}.py` (new), `tools/builtin.py`, `__main__.py`, `tests/test_*` (new+updated).

## Earlier task (2026-06-22)
- **Task:** DW-AGENT-SKETCH — smart, controlled drawing. New `geometry/` package
  (DSL on a 0..100 grid + deterministic tessellation + UIA-first canvas detection)
  exposed as the `sketch` AI tool; the AI plans a whole figure in ONE call and code
  renders it precisely (smooth circles, one stroke per primitive → no stray slash).
  Planner forces ONE cropped vision look after a sketch. Replaces the old blind
  raw-`mouse.stroke` drawing. **223 tests pass** (+39). Offline-proven:
  `artifacts/cat_attempts/cat_render_preview.png` is a clean cat. Live = MANUAL-10.
- **Files:** `geometry/{__init__,dsl,render,canvas}.py` (new),
  `tools/builtin.py`, `tools/__init__.py`, `__main__.py`,
  `loop/claude_cli_planner.py`, `tests/test_geometry_*.py` (new), `tests/test_tools.py`,
  `tests/test_claude_cli_planner.py`.

## Milestone
**GENUINE live AI desktop control shipped (§22 realized).** Give a plain-language
task and the AI decides + performs each action live, like the Chrome extension:
`python -m desktop_worker do "<task>"` (VERIFIED real desktop, Level 4 — the AI
opened Notepad via Run dialog and typed text, self-verifying, all on its own).
Also: deterministic `create-file` workflow (separate, reliable).

## Last completed task
- **Task:** Autonomous batch (2026-06-21): open_url + focus_window tools, session
  replay HTML, frugal mode. All Codex+Northstar approved. 176 tests. See changelog.
- **Earlier capstone:** DW-AGENT-DO — genuine live AI desktop control.
- **Date:** 2026-06-21.
- **Summary:** `do "<task>"` runs the live loop: observe → perceive (UIA elements +
  context menus + values, OCR) → Claude (logged-in CLI, no API key) picks the next
  structured action by elementId → safety-gated executor performs it → verify →
  repeat; each AI decision printed + audited. Perception gained context-menu popups
  + editable VALUES (typed-text feedback); planner gained elementId→coords (mouse-
  only, stale rejected) + reasoning + outcome + env_context; loop gained settle,
  on_step, stall_guard, done-vs-failure, visibleText verify; fixed a risk-classifier
  false positive. Codex APPROVE, Northstar ALIGNED. 138 tests; real run verified.
- **Files:** `__main__.py`, `loop/claude_cli_planner.py`, `loop/task_loop.py`,
  `perception/uia_backend.py`, `broker/risk.py`, `tests/test_ai_loop.py`.

## Branch / release status (2026-06-25)
- **`dw/roadmap-5-6-7` merged into `main` (fast-forward) and pushed to origin**
  (`e850563..cdcc763`). Phases 5/6/7 on the default branch. Current branch: `main`.
- **Live-validated this session (Level 4):** MANUAL-1, -2, -6, -8, -9, plus WF-1
  (switch-window), WF-3 (download). WF-2 + WF-4 hit real bugs, **fixed + re-validated
  live** (DW-WF-PICKER-OPENBTN, DW-WF-BROWSE-FOREGROUND). 356 tests green.
- **Test count:** 350 → **356** (+6 for the two WF fixes).

## Next recommended task
Phase 8 (MCP server) is the project's functional finish line: an external AI agent can
now drive Desktop-Worker. Remaining work is user-interactive live validation + tuning:
1. **MANUAL-MCP-1 (headline):** register `python -m desktop_worker mcp` in a real MCP
   client (Claude Desktop/Code) and drive the priority scenarios (multi-step app,
   browser, file/system, draw, **Unity Editor manual tasks**). Report what worked vs.
   failed + what `perceive` returned on failures → that drives the reliability tuning
   that actually closes the "another AI couldn't do it" gap.
2. Then approve **merge + push of `dw/phase8-mcp` → main**.
3. Reliability follow-ups likely surfaced by MANUAL-MCP-1: richer perception for
   low-UIA apps (vision-assist over MCP), perceive id-stability across calls, a
   higher per-task action budget for complex chains.
4. Still open (non-blocking): MANUAL-WF-4 form-fill, ORCH-1, UI-1. Not testable here:
   MANUAL-4 (UAC — already admin), MANUAL-5 (OCR — `pytesseract` not installed).

## Open risks
| Risk | Severity | Mitigation |
|---|---|---|
| Broker `shell=True` runs cmd.exe strings | Medium | Gated by classify+approval+audit; no passthrough API. Consider arg-list mode + allowlist later. |
| "elevated by default" not yet true per-command from non-admin context | Medium | Broker reports actual token; DW-CLI-ELEVATE closes the gap. Don't overstate in logs. |
| Real input not validated on a live desktop yet | Medium | Manual step MANUAL-1; Null backend covers logic only. |
| Risk classifier is heuristic (may miss novel dangerous commands) | Medium | Deny-toward-caution; expand patterns; add allow/deny lists (Phase 7). |
| Windows-only ctypes paths untested on non-Windows CI | Low | Factory falls back to Null; guarded by `sys.platform`. |

## Open questions
| # | Question | Blocking? | Answer/default |
|---|---|---|---|
| 1 | Which AI provider/model drives the planner? | No | Default: Claude (per requirements agent model). Interface is provider-agnostic. |
| 2 | UI: web dashboard vs native (Phase 7)? | No | Decide at Phase 7; CLI suffices until then. |
| 3 | Make the initial git commit now? | No | DONE — committed `023b107` and pushed to GitHub (user requested). Commit/push now allowed for this project. |

## Manual steps waiting (user tests — none block further implementation)
See `dw_manual_steps.md`: **MANUAL-10 (watch the AI draw a cat with the new `sketch`
pipeline — the headline drawing demo)**, MANUAL-1 (validate real input on a desktop),
MANUAL-2 (install `[windows]` extra for real screenshots), MANUAL-3 (DONE — git),
**MANUAL-4 (validate real UAC elevation from a non-admin shell)**,
**MANUAL-5 (install Tesseract + `[ocr]` and validate real OCR)**,
**MANUAL-6 (install `uiautomation` and validate real UIA enumeration)**,
**MANUAL-7 (drive a real task end-to-end with the Claude CLI planner)**.

## Last validation results
- **Date:** 2026-06-30 (DW-MCP-SERVER, Phase 8).
- **Type:** `python -m pytest` — **373** (372 passed + 1 skipped). New: 14 AgentBridge
  Null-backend tests + 3 server-register tests. PLUS a real-FastMCP in-process e2e smoke:
  built the actual `FastMCP` server, registered the bridge (22 tools, schemas inferred
  from type hints), and called tools through it — `observe`→structured state, `click`→
  routed through the executor, `list_tools`→6 tools, malformed `act`→rejected, and after
  `emergency_stop` the next `click` was **halted**. Confirmed no SDK API drift.
- **Validation level reached:** **3+** for DW-MCP-SERVER (unit + real-SDK in-process e2e).
  Level 4 (external client process driving a live desktop) = MANUAL-MCP-1.
- **Prior (2026-06-24):** `python -m pytest` — 350 passed; Phases 5/6/7 Codex-audited.

## Earlier validation results
- **Date:** 2026-06-22.
- **Type:** `python -m pytest` (224 tests) + **LIVE real-desktop draw** of the `sketch`
  pipeline in real Win11 Paint.
- **Result:** **224 passed.** LIVE: the `sketch` tool drove the real mouse + real UIA
  canvas detection to draw a clean, recognizable cat in real Paint —
  `artifacts/cat_attempts/cat_live_best.png` (no stray slash, round circles). This also
  incidentally validated MANUAL-1 (real input motion), MANUAL-2 (real screenshots), and
  MANUAL-6 (real UIA enumeration / canvas detection).
- **Validation level reached:** **4 (live real desktop)** for the `sketch` drawing path
  (deterministic — no Claude quota used) and the planner→broker→claude path (earlier);
  **3** elsewhere. Remaining live user tests: MANUAL-10 (AI-driven `do` cat), MANUAL-4
  (UAC), MANUAL-5 (Tesseract OCR), MANUAL-7 (full AI task).

## Continuity rules
After every task: update this file's status table + Last completed/Next, append a
`dw_changelog.md` entry, refresh `dw_tracker.html`, and add any `dw_manual_steps.md`
entries. Never claim validation not actually run.
