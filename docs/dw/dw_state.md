# dw_state.md — Authoritative state file

> Update after every task. This file — not chat history — is the source of truth
> for "where are we".

## Session info
- **Last updated:** 2026-07-22
- **Repo path:** `C:\Desktop-Worker`
- **Workspace path:** `C:\Desktop-Worker\docs\dw`
- **Current branch:** `main` (Phase 8 + clipboard/keys fixes + 3D Tier 1/Tier 3 merged & pushed
  2026-06-30, `10942cd..797e75d`). Tier 2 (DXcam capture_burst + orbit) on a fresh branch next.
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
| Clipboard set/get (64-bit handles) | fixed (DW-CLIP-FIX); was OverflowError on every call; LIVE round-trip verified |
| **GENUINE live AI control** (`do "<task>"`) | complete (DW-AGENT-DO); VERIFIED real desktop |
| Perception: context menus + editable values | complete (AI sees menus + what it typed) |
| AI action/outcome memory + vision fallback (`--vision`) | complete (DW-AGENT-MEMORY / VISION) |
| AI-callable tools: create_text_file, open_app, open_url, focus_window | complete (DW-AGENT-TOOLS+) |
| Smart drawing: `sketch` tool + `geometry/` (DSL, renderer, canvas detection) | complete (DW-AGENT-SKETCH); LIVE-validated |
| Drawing v2: SVG + canvas hygiene + best-of-N `draw` command (`drawing/`) | complete (DW-AGENT-DRAW); deterministic path LIVE-validated, AI best-of-N = MANUAL-11 |
| Frugal mode (`--frugal`) | complete (leaner prompts, less Claude usage) |
| Session replay HTML (`report` cmd + auto) | complete (DW-REPLAY); §16 audit viewer |
| **External AI interface — MCP server** (`mcp` CLI) | complete (Phase 8, DW-MCP-SERVER); pure AgentBridge + thin FastMCP; live external client = MANUAL-MCP-1 |
| 3D perception: `inspect_3d` (multi-view montage) | complete (Tier 3, DW-3D-INSPECT); LIVE-validated on Blender (eased orbit + crop + distinct-view warning) |
| 3D capability: `orbit` + `capture_burst` (+DXcam opt-in) | complete (Tier 2, DW-3D-CAPTURE); capture_burst LIVE-validated on Blender (turntable + ms timestamps) |
| Clipboard 64-bit fix + numpad/nav keys | complete (DW-CLIP-FIX, DW-KEYS-NUMPAD); clipboard LIVE round-trip verified |
| `type_text` reaches GHOST apps (Blender/games) | complete (DW-INPUT-GHOST); VK keystrokes via VkKeyScanW; LIVE-validated in Blender (console/rename/Turkish); Unicode fallback for AltGr/off-layout |
| **Eval harness — success rate / steps / latency / round-trips** | complete (Phase 10, DW-EVAL-HARNESS); `eval/` package + `eval` CLI; **A1 + A2 baselines recorded, MANUAL-EVAL-1 DONE (Level 4)** |
| **`focus_window` actually foregrounds windows** | complete (DW-FOCUS-RELIABLE); AttachThreadInput + verify vs GetForegroundWindow; **0/5 -> 5/5 apps live** |
| Phase 11 — inline screenshot image over MCP | complete (DW-MCP-IMAGE); A2 INLINE-IMAGE 0/3 -> **3/3** live |
| Phase 11 — stable element ids + click_element | complete (DW-ELEM-STABLE); A2 ID-STABLE 0/5 -> **5/5**; zero positional ids remain |
| Phase 11 — perceive ranking + truncation signal | complete (DW-PERCEIVE-RANK); TRUNCATION 0/5 -> **5/5**; Paint drops only labels |
| Phase 11 — act_many batching | complete (DW-ACT-BATCH); 4 round-trips -> **1**; safety still per-action |
| Phase 11 — settle_ms + post-action diff | complete (DW-ACT-SETTLE); settle honored + silentNoOp surfaced |

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
None in progress. **PHASE 11 COMPLETE** (all 5 cards, each with a live measured delta).

## LATEST (2026-07-22, later) — open threads closed
- **OCR preflight (DW-OCR-PREFLIGHT):** `ocr_status()` checks pytesseract + Pillow + the
  tesseract BINARY on PATH; surfaced in CLI/bridge `status` and as `perception.ocrWarning`.
  Found + fixed a HARD CRASH: binary-off-PATH made `perceive(screenshot=True)` throw
  `TesseractNotFoundError`; the factory now probes the binary and falls back to Null. Live-
  verified both directions.
- **Tier B grown 4 -> 7** from real audit failures (clipboard OverflowError regression,
  focus/typing race, denied-destructive refusal). Live run scored feasible 5/5 but exposed a
  HARNESS scoring bug on the infeasible axis: the AI refused both tasks honestly, yet the
  harness read `completed=True` as "claimed success". Fixed (DW-PLANNER-INFEASIBLE): "done"
  now distinguishes achieved vs refused via a structured `infeasible` flag. **Corrected Tier
  B: 7/7.** Re-verified live.
- **524 tests.** Pushed.

## Earlier 2026-07-22 — A2 at 100%, Tier B live, docs pushed
- **A2 tool-surface suite: 90/90 = 100%** (CI [95.9%, 100%]), 30 tasks x 3 trials, 7 apps
  open (Notepad, Paint, Calculator, Blender, KiCad, Chrome, Unity).
- **Tier B (DW-EVAL-TIERB) shipped and run live: 4/4 on 12 Claude calls.**
  `dw-eval-tierb.txt` verified ON DISK. Cost ceiling enforced via `--max-ai-steps`.
- **Unity measured on a THROWAWAY project** — 22 UIA + 8 OCR = 30 elements. This
  CONTRADICTED the prediction that Unity would stress the 200-element cap; it is the
  low-UIA extreme like Blender. Strategy for Unity is vision, not element hunting.
- Two more defects found, both in the MEASUREMENT not the product: the Tier B cost counter
  read a non-existent field and silently reported 0 spent (a ceiling that can never halt),
  and `A2-SURFACE-ELEMENT-FOUND` asserted `control_type="edit"` which is not in our type
  vocabulary. Both fixed with regression tests.
- **508 tests.** Pushed to origin/main.

## PHASE 11 RESULT (2026-07-21) — measured, not asserted
| Suite | Before | After |
|---|---|---|
| **A1 feasible** | 33.3% (CI [19.2, 51.2]) | **100%, 8/8** |
| **A2 feasible** | 33.3% (CI [24.4, 43.6]) | **70.0% (CI [59.9, 78.5])** |
| A2 FOCUS / ID-STABLE / TRUNCATION | 0/5 each | **5/5 each** |
| A2 INLINE-IMAGE | 0/3 | **3/3** |
| 4-action sequence | 4 MCP round-trips | **1 (-75%)** |
Tests **400 -> 492**. MCP tools 22 -> 24 (`click_element`, `act_many`).
Commits: 103749e, 0c3a5ed, ea837a5, b01fddd (+ the Phase 10 harness work). NOT pushed.

Remaining A2 red is ENVIRONMENTAL, not product: Notepad would not stay open on this
machine (Win11 session restore), and Unity needs an open project — deliberately not opened,
since a version-upgrade prompt would modify the user's real projects.

## Last completed task (2026-07-21) — DW-FOCUS-RELIABLE + honest A2 baseline
- **Found by running the harness, not by reading code.** The first live A2 run scored
  44.4% with KiCad tasks PASSING — KiCad is not installed. Every app returned the same
  40 elements: the suite was measuring the Windows taskbar 90 times.
- **Product bug fixed:** `_win_focus` used bare `SetForegroundWindow`, which Windows
  refuses for a background process (the MCP server is one). Now AttachThreadInput +
  BringWindowToTop + verify against `GetForegroundWindow()` with a bounded retry, and a
  specific failure reason instead of `{}`. **0/5 -> 5/5 apps focusable, live-verified.**
- **Four harness defects fixed:** silent pass on the wrong window (added `gated()`);
  swallowed setup failures (schema field is `tool`, not `name` — every setup action was
  being rejected and ignored); an over-broad `deny_all` approver that starved `open_app`
  (MEDIUM risk); and state leaking across trials (one run spawned 12 Paint windows).
- **One probe was too weak:** ID-STABLE passed everywhere, which would have wrongly
  cleared DW-ELEM-STABLE. Strengthened to detect purely positional `uia-<index>` ids;
  it now correctly reports 0/5.
- **Tests: 437 -> 445.** Validation level **4 (live real desktop)**.

## HONEST A2 BASELINE (2026-07-21, zero Claude quota)
`docs/dw/eval/baseline_a2.json` — feasible **33.3%**, 95% CI [24.4%, 43.6%];
2.5 round-trips, 589 ms mean per trial.
| Probe | Result | Meaning |
|---|---|---|
| FOCUS | **5/5** | fixed this session (was 0/5) |
| ID-STABLE | **0/5** | all ids positional -> DW-ELEM-STABLE confirmed necessary |
| TRUNCATION | **0/5** | no `truncated` flag; **Paint hits exactly 200 = AT CAP AND SILENT** |
| INLINE-IMAGE | **0/3** | `keys=['ok','path']` -> DW-MCP-IMAGE confirmed |
| PAYLOAD | measured | Blender 6 (~252 tok) · Chrome 50 (~2223) · Notepad 54 (~2243) · Calculator 82 (~3430) · **Paint 200 (~8258, capped)** |
**CORRECTED 2026-07-21:** KiCad WAS installed (per-user, `%LOCALAPPDATA%\Programs\KiCad.0`)
— my "not installed" call came from probing only `%ProgramFiles%`. Tesseract 5.4.0 has since
been installed (+ added to User PATH), so OCR now contributes. True agent-facing payload
(UIA + OCR): Blender 8 (~333 tok) · Chrome 61 (~2 702) · Notepad 78 (~3 202) ·
Calculator 130 (~5 287) · **KiCad 193 (~7 902, 76% from OCR)** · **Paint 200 (~8 258, AT CAP)**.
KiCad measured without Tesseract would have read 46 — a 4x undercount.
**Blender stays nearly blind at 8 elements even with OCR** — for GHOST apps inline vision
is the only channel, which strengthens DW-MCP-IMAGE.
**NOT MEASURED:** Unity only — real projects exist (`C:\BurnNotice`, `C:\DiceNDecks`) but
opening one can trigger a version-upgrade prompt that modifies the user's project; not done
without explicit consent.
**Fidelity caveat:** the payload probe uses `perceive(screenshot=False)`, so
`baseline_a2.json` numbers are UIA-only and understate reality. Queued as a suite defect.

## Last completed task (2026-07-21) — Phase 10: eval harness (DW-EVAL-HARNESS)
- **What:** Built the measurement instrument BEFORE the Phase 11 improvements it will
  grade. New `eval/` package (spec / oracles / runner / suite) + `eval` CLI subcommand.
  Driven by a deep-research pass (26 sources, 25 adversarially verified claims: 17
  confirmed, 8 refuted) plus a local code audit.
- **Three tiers:** A1 (Null, CI, zero quota) · A2 (live apps, zero quota — grades the tool
  surface, which is what Phase 11 changes) · B (full AI runs, SPENDS QUOTA, `--allow-ai`
  gated, verified exit 2 without it).
- **Tests:** 400 -> **437 passed, 1 skipped** (+38).
- **Validation level: 3+** — unit tests AND a real end-to-end A1 run writing
  `docs/dw/eval/baseline_a1.json`. Level 4 = MANUAL-EVAL-1 (never run yet).
- **BASELINE (5 trials/task):** feasible **33.3%**, 95% CI [19.2%, 51.2%]; infeasible
  10/10 on its own axis. 4 safety invariants PASS; 4 Phase 11 criteria FAIL by design.
- **Two defects found while validating and fixed:** the harness would have BLOCKED on an
  interactive `[y/N]` approval prompt (now `deny_all` — measurement must never wait on a
  human); and A1 with real backends would have moved the user's real mouse (A1 now forces
  Null regardless of `--null`).
- **Files:** new `src/desktop_worker/eval/{__init__,spec,oracles,runner,suite}.py`;
  changed `__main__.py`; new `tests/test_eval_{oracles,runner}.py`; new
  `docs/dw/eval/baseline_a1.json`. Diff budget raised to 5 new production files with
  explicit user approval at the gate.
- **Deliberately NOT touched:** `schema/`, `safety/`, `audit/`, `broker/`, `perception/`,
  `mcp_server/`, `actions/executor.py`. The harness observes the system under test; if it
  modified that system, every before/after comparison would be invalid.

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

## Next recommended task (2026-07-21, after MANUAL-EVAL-1)
**Phase 11, in measured order. Every card now has a live before-number to beat.**
1. **DW-PERCEIVE-RANK** — promoted to first. Paint proves the defect is real: exactly
   200 elements, at cap, with no signal, ~8 258 tokens of payload. An agent cannot tell
   "not there" from "not told".
2. **DW-MCP-IMAGE** (the vision half is entirely
   disconnected over MCP — a defect, not an optimisation), then DW-ELEM-STABLE,
   DW-PERCEIVE-RANK, DW-ACT-BATCH, DW-ACT-SETTLE.
3. Each Phase 11 card must land with a **measured before/after delta** from the harness,
   not an assertion. That is the whole point of Phase 10.
4. Optional follow-up: **DW-EVAL-TIERB** — wire `do` runs into tier B. Deferred so that
   Phase 10 did not have to spend Claude quota to prove itself.

**Research-backed deprioritisations (do not resurrect without new evidence):** a local GPU
grounding model (2026 data refutes the premise — frontier VLMs score ~0.88 on
ScreenSpot-Pro); DXcam capture-rate work (capture is 1-3% of latency vs 87-97% for model
round-trips). See `dw_roadmap.md` Excluded table.

## Earlier recommended task (superseded)
**All three 3D tiers done + LIVE-validated** (Tier 1 docs, Tier 3 `inspect_3d`, Tier 2
`orbit`/`capture_burst`+DXcam). Branch `dw/tier2-capture` merges to main. Remaining is optional:
- DXcam `fast:true` path only verified by fallback (dxcam not installed here) → install
  `[capture]` + live-test the genuine high-FPS grab if real continuous-motion capture is wanted.
- Otherwise the desktop tool + the user-scope `desktop-worker` skill (REFERENCE + per-app playbooks)
  are the product; growth now comes from real runs feeding the playbooks, not new core code.

Earlier context — Phase 8 (MCP server) is the project's functional finish line: an external AI
agent can now drive Desktop-Worker. Live MANUAL items remaining are user-interactive validation:
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
- **Type:** `python -m pytest` — **378** (377 passed + 1 skipped). New: 14 AgentBridge
  Null-backend tests + 3 server-register tests + **5 real-FastMCP e2e tests**
  (`test_mcp_server_e2e.py`, skipped when the SDK is absent): built the actual `FastMCP`
  server, registered the bridge (22 tools, schemas inferred from type hints), and called
  tools through it — `observe`→structured state, `click`→routed through the executor,
  `list_tools`→6 tools, malformed `act`→rejected, and after `emergency_stop` the next
  `click` was **halted**. The in-process smoke is now a permanent regression guard against
  SDK API drift.
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
