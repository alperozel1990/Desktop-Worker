# dw_state.md — Authoritative state file

> Update after every task. This file — not chat history — is the source of truth
> for "where are we".

## Session info
- **Last updated:** 2026-06-20
- **Repo path:** `C:\Desktop-Worker`
- **Workspace path:** `C:\Desktop-Worker\docs\dw`
- **Current branch:** `main`
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
| Browser/desktop workflows | not started (Phase 5) |
| Multi-agent orchestration | not started (Phase 6) |
| UI (inspect/control) | not started (Phase 7); CLI only today |
| AI planner (Claude Code CLI, no API key, via broker) | complete (DW-PLANNER-AI); real path verified, full task = MANUAL-7 |
| Phase 5 workflow: create desktop text file (visible) | complete (DW-WORKFLOW-CREATEFILE); VERIFIED real desktop |
| Input Unicode (Turkish ş/ı) via SendInput | fixed (was keybd_event byte-truncation) |
| **GENUINE live AI control** (`do "<task>"`) | complete (DW-AGENT-DO); VERIFIED real desktop |
| Perception: context menus + editable values | complete (AI sees menus + what it typed) |
| AI action/outcome memory + vision fallback (`--vision`) | complete (DW-AGENT-MEMORY / VISION) |
| AI-callable tools: create_text_file, open_app, open_url, focus_window | complete (DW-AGENT-TOOLS+) |
| Frugal mode (`--frugal`) | complete (leaner prompts, less Claude usage) |
| Session replay HTML (`report` cmd + auto) | complete (DW-REPLAY); §16 audit viewer |

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
None in progress.

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

## Next recommended task
Optional / not blocking: expose deterministic workflows as AI-callable tools
(brain+hands); vision fallback for UIA-poor apps (Electron/Chromium); Phase 6
(multi-agent), Phase 7 (UI with live approve/deny). User test: **MANUAL-9**
(run `do "<task>"` and watch the AI) — the headline AI-control demo.

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
See `dw_manual_steps.md`: MANUAL-1 (validate real input on a desktop),
MANUAL-2 (install `[windows]` extra for real screenshots), MANUAL-3 (DONE — git),
**MANUAL-4 (validate real UAC elevation from a non-admin shell)**,
**MANUAL-5 (install Tesseract + `[ocr]` and validate real OCR)**,
**MANUAL-6 (install `uiautomation` and validate real UIA enumeration)**,
**MANUAL-7 (drive a real task end-to-end with the Claude CLI planner)**.

## Last validation results
- **Date:** 2026-06-20.
- **Type:** `python -m pytest` (125 tests) + demo + real planner smoke.
- **Result:** 125 passed. Demo loop 5/5. Real `observe` returned genuine
  cursor/window/screen data. **Real Claude CLI planner verified** (Level 4 for the
  planner path): `claude_available=True`, live call returned a valid action.
- **Validation level reached:** **3** overall (unit + local runtime); **4** for the
  planner→broker→claude path. Live-desktop input/UAC/OCR/UIA = MANUAL-1/4/5/6/7.

## Continuity rules
After every task: update this file's status table + Last completed/Next, append a
`dw_changelog.md` entry, refresh `dw_tracker.html`, and add any `dw_manual_steps.md`
entries. Never claim validation not actually run.
