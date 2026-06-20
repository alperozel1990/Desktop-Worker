# Desktop-Worker

**AI-control-ready Windows desktop automation.** Desktop-Worker lets an AI agent
do real work on a Windows PC through the same surfaces a human uses — screen,
mouse, keyboard, clipboard, windows, files, browser, and CLI — built around a
disciplined loop:

> **observe → understand → plan → act → verify → log → continue / retry / ask / stop**

Safety, audit logging, an emergency stop, and an elevated CLI **broker** are
first-class from the first milestone — not bolted on later. There is **no raw
unrestricted shell**: every command is classified, gated, captured, and logged.

See [`docs/requirements.md`](docs/requirements.md) for the full product spec and
[`docs/dw/`](docs/dw/) for the live roadmap, backlog, and project state.

## Status

Phase 1 (Local Control Foundation) + Phase 2 loop skeleton + Phase 3 broker
foundation are implemented and unit-tested. See `docs/dw/dw_state.md`.

## Architecture

The codebase mirrors the layered architecture in requirements §5. Pure logic is
dependency-free and fully unit-testable; real desktop control lives in Windows
backends behind interfaces, with `Null` backends for headless/test runs.

```
src/desktop_worker/
  schema/       structured actions, observations, results (validated, no I/O)
  safety/       emergency stop + pause, permission/risk policy, limits
  audit/        JSONL audit log with secret redaction
  broker/       elevated/admin-capable CLI broker (the ONLY CLI path) + risk classifier
  observation/  desktop observation (screenshot, cursor, windows) — Windows + Null backends
  actions/      action executor + input backends (mouse/keyboard/clipboard) — Windows + Null
  loop/         the observe-plan-act-verify-log task loop + pluggable planner
  app.py        Session wiring
  __main__.py   CLI: status / observe / demo / estop / clear-stop
tests/          pytest suite (no display required)
```

## Quick start

```powershell
# Install (core has zero deps; extras enable real screenshots / OCR)
python -m pip install -e ".[dev]"
python -m pip install -e ".[windows]"   # optional: mss screenshots, pywin32

# Show config, backends, and process elevation
python -m desktop_worker status

# Capture one real structured observation (cursor, active window, screen)
python -m desktop_worker observe --no-screenshot

# Run the scripted demo task through the full loop (Null backends, safe)
python -m desktop_worker --null demo

# Emergency stop (writes a sentinel any running session will halt on)
python -m desktop_worker estop
python -m desktop_worker clear-stop
```

## Tests

```powershell
python -m pytest
```

The suite runs entirely on `Null` backends — no mouse moves, no display needed.

## Safety model (read before extending)

- **Emergency stop** is checked before every action and every loop step, via an
  in-process flag *and* a file sentinel an external process can set.
- **Every action and CLI command** is validated, risk-classified, approval-gated
  (high-risk denied by default headless), and written to a JSONL audit log.
- **CLI only runs through the broker.** Do not add `subprocess`/`os.system`
  calls elsewhere. The broker is the single controlled execution boundary.
- **Secrets** are redacted from audit entries by pattern.

## Elevated launch

The broker reports whether the process token is elevated. To run with admin
rights (so commands inherit elevation and their output is still captured), launch
via `docs/dw/start_dw_claude.bat`, which self-elevates through Windows UAC.
