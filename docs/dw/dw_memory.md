# dw_memory.md — Compact startup memory

> Read this FIRST at every session start, then `dw_state.md`.

## Project goal
Build an **AI-control-ready Windows desktop automation app** (Desktop-Worker)
that runs the loop: observe → understand → plan → act → verify → log → continue.
Source of truth: `docs/requirements.md`.

## Key architecture facts
- Python package at `src/desktop_worker/`, layered per requirements §5.
- **Core is dependency-free and unit-tested.** Real desktop control lives in
  Windows backends behind Protocols (`DesktopBackend`, `InputBackend`); `Null`
  backends make the whole loop + tests run headless.
- Layers: `schema/` (actions/observations/results), `safety/` (estop + policy),
  `audit/` (JSONL + redaction), `broker/` (elevated CLI — the ONLY CLI path),
  `observation/`, `actions/`, `loop/`, `app.py` (Session wiring), `__main__.py`.
- Entry: `python -m desktop_worker {status|observe|demo|estop|clear-stop}`.

## User hard preferences
- Requirements doc is source of truth; stay aligned to the AI-control-ready north star.
- Small, testable, structured. Prefer UI Automation over image-only (Phase 4).
- Stack chosen: **Python** (confirmed by user during bootstrap).

## Hard guardrails / do-not-break
- All CLI through the elevated broker. **No raw shell** (`subprocess`/`os.system`)
  anywhere outside `broker/cli_broker.py`.
- No high-risk action/command without policy approval (deny-by-default headless).
- Every action + command audited (JSONL). Emergency stop checked before every
  action and loop step. Secrets redacted in logs.
- Malformed actions never execute (schema validation first).

## Do-not-touch list
- `docs/requirements.md` (read-only source of truth — do not edit).
- `artifacts/` (generated output; git-ignored).

## Current roadmap position
- **PROJECT COMPLETE (2026-06-30), all merged to main + pushed (origin/main @ cb7f835), 400 tests.**
  On top of Phase 8: a **3D capability tier** + **input-reliability closeout**, all LIVE-validated:
  - 9 AI-callable tools now (added `inspect_3d` = multi-view montage 3D perception, `orbit` = eased
    middle-drag, `capture_burst` = timestamped snapshots-while-rotating; DXcam opt-in via `[capture]`).
    Eased/time-spaced orbit is REQUIRED — an instant mouse jump is dropped by Blender's GHOST layer.
  - Input fixes: clipboard set/get 64-bit handle bug (OverflowError) FIXED; `press_key`/`hotkey` gained
    numpad+nav keys; **`type_text` now reaches GHOST apps (Blender/games)** via VK keystrokes
    (VkKeyScanW), Unicode fallback for AltGr/off-layout — so typing into Blender works directly.
  - **User-scope `desktop-worker` skill** (`~/.claude/skills/desktop-worker/`): thin SKILL.md + living
    REFERENCE.md + per-app **playbooks** (INDEX + ltspice/blender/unity) with a verify-before-save,
    generic-entry, read-before/write-after protocol so ANY AI session can use the tool and self-improve
    from real runs. Update the skill's REFERENCE/playbooks (not core code) as the tool grows.
    See [[desktop-worker-skill-living-doc]], [[desktop-worker-playbook-generic]].
- **PHASE 8 — EXTERNAL AI INTERFACE (MCP server) DONE (2026-06-30).** Desktop-Worker is
  now usable BY OTHER AI AGENTS (the user's north-star: "another AI couldn't use this
  tool"). New `mcp_server/` package: pure dep-free `AgentBridge` maps observe/perceive/
  screenshot/mouse+keyboard+clipboard/`act`/`run_tool`/`run_cli`/status/estop onto the
  SAME `executor.execute(parse_action(...))` path — the external AI becomes the planner;
  validation/policy/estop/audit all stay BELOW it (it's exactly as constrained as the
  internal planner). Thin `server.py` registers 22 tools via lazily-imported FastMCP
  (`register()` is SDK-free + fake-server-tested); new `mcp` CLI command; `[mcp]` extra
  (`mcp>=1.2`). 373 tests. Validated Level 3+ (Null unit + real-FastMCP in-process e2e:
  observe/click/list_tools work, malformed rejected, estop halts). Branch `dw/phase8-mcp`,
  NOT pushed. Live external client = MANUAL-MCP-1 (priority scenarios incl. Unity Editor).
  KEY: package is named `mcp_server` (NOT `mcp`) so it never shadows the installed SDK;
  over stdio stdout is the JSON-RPC channel so human messages go to STDERR.
- **ALL 7 PHASES IMPLEMENTED (as of 2026-06-24).** Phases 5/6/7 completed in an
  autonomous batch on branch `dw/roadmap-5-6-7` (10 cards, 350 tests, each phase
  Codex-audited). NOT yet pushed — awaiting user approval + the MANUAL-* live tests.
  - Phase 5 (Browser/Desktop workflows): `workflows/{window,file_dialog,downloads,
    browser,browser_ui}.py`; CLI `switch-window`/`pick-file`/`wait-download`/`browse`;
    `DragDropTool`. Live = MANUAL-WF-1..4.
  - Phase 6 (Multi-agent orchestration): new `orchestration/` package
    (`schema`/`roles`/`claude_io`/`coordinator`); CLI `orchestrate [--execute]`
    (plan-only default; `--null` offline demo). Roles inject `ask` (default
    broker-routed claude w/ agent/role); auditors fail CLOSED. Live = MANUAL-ORCH-1.
  - Phase 7 (Hardening + UI): `PermissionPolicy.authorize_app` + app allow/deny +
    profile persistence in Config; `audit/retention.py` + CLI `clean-artifacts`;
    new `ui/` package — pure `UiController` (timeline/estop/pause/ApprovalQueue
    blocking handshake) + thin Tkinter `ui/app_tk.py`; CLI `ui`. GUI = MANUAL-UI-1.
- Phase 1 (Local Control Foundation): **implemented + tested**.
- Phase 2 (Structured Action Loop): **complete** — loop + DW-LOOP-RECOVERY
  (bounded retry/re-plan/safe-stop + time limit), auditor-approved.
- Phase 3 (Elevated CLI Broker): **complete** — DW-CLI-ELEVATE done (real
  per-command UAC elevation via `broker/elevation.py`, honesty invariant,
  auditor-approved). Real UAC prompt = user test MANUAL-4.
- Phase 4 (Perception): **complete** — OCR + UIA + loop-wiring. `perception/`:
  Element schema (source required), OcrBackend + UiaBackend, Perceiver (UIA-preferred
  merge + OCR fallback); `TaskLoop(perceiver=...)` feeds elements into the audit.
  Real OCR = MANUAL-5, real UIA = MANUAL-6.
- Input hardened (DW-INPUT-HARDEN): pure `plan_hotkey`/`resolve_vk`/`should_paste`;
  long text pastes via Ctrl+V. Real motion = MANUAL-1.
- **DW-PLANNER-AI DONE** — `loop/claude_cli_planner.py` drives the loop via the
  logged-in `claude` CLI (subscription, NO API key) through the broker; strict
  `parse_action` validation; fails safe; real path verified. See
  [[desktop-worker-no-api-billing]]. Full task = MANUAL-7.
- **GENUINE live AI control shipped (§22 realized).** `python -m desktop_worker
  do "<task>"` — the AI decides+performs each action live (like the Chrome
  extension): observe → perceive (UIA elements + context menus + values, OCR) →
  Claude (logged-in CLI, NO API key) picks next structured action by elementId →
  safety-gated executor → verify → repeat; each decision printed + audited.
  VERIFIED real desktop (AI opened Notepad via Run dialog + typed, self-verified).
  Key files: `__main__.py` `_cmd_do`, `loop/claude_cli_planner.py`, `loop/task_loop.py`.
  Reliability depends on UIA richness (Electron/Chromium apps expose little → degrades).
  Deterministic `create-file` workflow stays separate; `do` never delegates to it.
- **AI has action/outcome MEMORY** (DW-AGENT-MEMORY): each step the loop records
  what was tried + whether the screen changed + the AI's reasoning, and feeds the
  last 8 back so the AI self-corrects (won't repeat ineffective actions). This
  replaced an earlier "you're stuck" heuristic the user rejected. Principle: give
  the AI good information and let it reason — don't spoon-feed heuristics.
- **AI-callable TOOLS** (DW-AGENT-TOOLS): "brain + reliable hands". The AI can call
  a deterministic tool via a `tool.run` action instead of many fragile GUI steps.
  Registry in `tools/`; tools: `create_text_file` (writes+verifies+opens — RELIABLE,
  not flaky GUI), `open_app` (curated allowlist, shells excluded), `open_url`
  (http/https only, injection-safe), `focus_window` (by title). Also: `--vision`
  fallback (screenshot when UIA sparse, capped), `--frugal` (leaner prompts),
  `--profile {standard|strict|headless}` (§12 safety presets), session-replay HTML
  (`report` cmd / auto after `do`). 184 tests. All Codex+Northstar approved. Routed through the executor (per-tool
  risk: unknown⇒HIGH, create_text_file⇒MEDIUM; arg sanitization; nesting guard; fail
  safe). Lesson: a TOOL must GUARANTEE its result (verified file write), NOT replay a
  flaky GUI — the flaky right-click flow stays in the separate `create-file` demo.
  VERIFIED: AI chose the tool live; disk content exact.
- **VISION fallback** (DW-AGENT-VISION): `do "<task>" --vision` lets Claude SEE a
  screenshot when UIA is sparse (Electron/Chromium/custom apps). Adaptive + capped:
  off by default, only when elements < threshold, max 6 vision steps/task (each ~5x
  cost via `--max-turns 2 --allowedTools Read`). The user is QUOTA-SENSITIVE (hit a
  Claude spend limit) — keep vision cheap/optional. Each `do` step calls Claude =
  uses their subscription quota; if it fails with a spend-limit error the CLI now
  prints a clear note (claude.ai/settings/usage).
- Phase 5 also has: deterministic `workflows/desktop_file.py` (+`desktop_ui.py`):
  `create-file` builds a desktop .txt visibly, verified on disk.
- **SMART DRAWING (DW-AGENT-SKETCH).** New `geometry/` package (pure, dep-free core):
  `dsl.py` (validated 0..100-grid primitive language: line/polyline/circle/ellipse/
  arc/bezier/dot), `render.py` (deterministic tessellation → one stroke per primitive,
  adaptive sampling = smooth curves, affine map to canvas px), `canvas.py` (UIA-first
  canvas detection w/ geometric client fallback + Null; lazy ctypes/PIL). Exposed as
  the `sketch` AI tool (risk=low) so the AI plans a WHOLE figure in ONE `tool.run`
  instead of many blind strokes — fixes the old polygon-circle + stray-slash + timeout.
  Planner forces ONE cropped vision look after a sketch (render→look→refine, bounded
  for quota). Design rooted in SketchAgent (grid reasoning) + generator-critic
  refinement. NO new schema action (the `tool.run` envelope suffices); `stroke()`
  reused unchanged. **LIVE-VALIDATED (Level 4):** drove the real mouse + real UIA
  canvas detection in real Win11 Paint → clean recognizable cat
  (`artifacts/cat_attempts/cat_live_best.png`), no Claude quota used. Two fixes from
  observing the real app: (1) draw into `fit_square`+5% margin so circles stay round
  on a wide canvas; (2) after Select-All/clear Paint stays on the SELECT tool — pick a
  drawing tool (Pencil/Brush) before sketching (guidance added to `do`). Lesson:
  observing the REAL app surfaced two bugs unit tests + offline render could not.
- **DRAWING v2 (DW-AGENT-DRAW)** — robust + best-of-N + SVG. Fixes the "red scribbles"
  gap (no canvas hygiene; raw strokes still possible; no quality gate). Method
  (Chat2SVG/CLIPasso/LLM4SVG): generate→render-OFFLINE→AI-judge→execute-CLEAN→verify;
  the AI only PROPOSES (SVG), execution is deterministic. New: `geometry/svg.py`
  (SVG-subset→Program, aspect-fit to 0..100), `geometry/preview.py` (offline PNG +
  montage), `geometry/paint_setup.py` (`prepare_paint`: clean canvas + Pencil + Black
  via UIA, Null fallback), `drawing/director.py` (best-of-N orchestrator, Claude calls
  injected), `drawing/claude_io.py` (broker-routed claude). `SketchTool` accepts `svg`
  OR `primitives` + preps canvas; `tools.render_program_to_canvas` is the shared
  hygienic execution. Command: `desktop_worker draw "<subject>"`. LIVE-validated the
  deterministic path (cleaned a red-scribbled canvas → clean SVG cat,
  `cat_v2_clean_best.png`); full AI best-of-N = MANUAL-11. Lesson: give the AI a
  PROPOSE-only role + deterministic clean execution → robustness by construction.
- **CRITICAL input fix:** `windows_input.type_text` now uses **SendInput** (16-bit
  wScan + surrogate pairs) for Unicode — keybd_event truncated codepoints >255
  (Turkish ş/ı were corrupted). VK map now has full A-Z/0-9 (Ctrl+S was a no-op).
- Tests never trigger real UAC now (test brokers pass elevator=None). CLI stdout
  reconfigured to utf-8 (cp1252 console was crashing on Turkish).
- Remaining: more Phase 5 workflows, Phase 6 (multi-agent), Phase 7 (UI). User
  test guide: `dw_test_guide.md`; primary demo test = MANUAL-8 (run create-file).
- Modern Win11 Notepad restores unsaved session tabs — can hijack opens; the
  workflow mitigates via verify-on-disk + one retry. Don't clear user TabState.

## Operating model (since 2026-06-20)
- Autonomous per-card execution. Each card gated by **Codex Auditor** (code) +
  **Northstar Auditor** (direction) subagent sign-off, then commit + push.
- Pause ONLY for things the user must physically test (live mouse/keyboard, UAC
  prompt, real browser, Tesseract install). Batch those as a "test this" list.

## Current next action
**None mandatory — project complete + live-validated + merged to main.** Optional: install
`[capture]` and live-test `capture_burst fast:true` (DXcam high-FPS); delete merged feature
branches. Otherwise growth comes from real runs feeding the per-app **playbooks** in the
user-scope `desktop-worker` skill — update REFERENCE.md/playbooks, not core code.

## Important assumptions
- Python 3.11+ (dev machine has 3.14.0). Windows 11. `claude.exe` at
  `%USERPROFILE%\.local\bin\claude.exe`.
- Single-monitor MVP is acceptable (per requirements §6).

## Manual-tool limitations
- Real screenshots need the `[windows]` extra (`mss`); without it screenshot
  capture returns a placeholder (loop still runs). OCR (Phase 4) needs Tesseract.
- Live desktop input validation (real mouse/keyboard moving) must be run by a
  human on a Windows desktop session — CI/headless uses Null backends.
