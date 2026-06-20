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
- Phase 2 (Structured Action Loop): **skeleton implemented + tested** (scripted planner).
- Phase 3 (Elevated CLI Broker): **foundation implemented + tested**; true
  per-command UAC re-elevation with captured output is the open card DW-CLI-ELEVATE.
- Phases 4–7: not started.

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
