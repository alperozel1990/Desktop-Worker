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
- Phase 5 also has: deterministic `workflows/desktop_file.py` (+`desktop_ui.py`):
  `create-file` builds a desktop .txt visibly, verified on disk.
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
Pick from `dw_backlog.md`. Recommended: **DW-CLI-ELEVATE** (real per-command
elevation) or **DW-INPUT-HARDEN** (input reliability) or **DW-PERCEPTION-OCR**
(start Phase 4). All have acceptance criteria in the backlog.

## Important assumptions
- Python 3.11+ (dev machine has 3.14.0). Windows 11. `claude.exe` at
  `%USERPROFILE%\.local\bin\claude.exe`.
- Single-monitor MVP is acceptable (per requirements §6).

## Manual-tool limitations
- Real screenshots need the `[windows]` extra (`mss`); without it screenshot
  capture returns a placeholder (loop still runs). OCR (Phase 4) needs Tesseract.
- Live desktop input validation (real mouse/keyboard moving) must be run by a
  human on a Windows desktop session — CI/headless uses Null backends.
