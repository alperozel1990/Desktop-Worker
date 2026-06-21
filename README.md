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
  loop/         observe-plan-act-verify-log loop + Claude-CLI AI planner (no API key)
  perception/   OCR + Windows UI Automation → structured Elements (UIA preferred)
  workflows/    deterministic desktop workflows (e.g. create-file demo)
  tools/        AI-callable reliable tools (create_text_file, open_app, open_url, focus_window)
  app.py        Session wiring
  __main__.py   CLI: do / create-file / status / observe / demo / report / estop
tests/          pytest suite (180+ tests, no display required)
```

## Quick start

```powershell
python -m pip install -e ".[dev,windows]"   # core + real desktop (mss, pywin32, uiautomation)
```

### Genuine live AI control (the headline)

Give a plain-language task and the AI decides + performs each action itself, live —
using your existing `claude` CLI login (no API key, no separate billing). It
observes the screen, reasons, acts through the safety-gated executor, verifies, and
continues until done. Every decision is printed and audited.

```powershell
python -m desktop_worker do "open the Calculator and compute 12 times 9"
python -m desktop_worker do "create a text file on the desktop and write a haiku in it"
```

Flags: `--vision` (let Claude SEE a screenshot on UIA-poor apps — costs more usage),
`--frugal` (leaner prompts = less usage/step), `--profile {standard|strict|headless}`
(how much it asks before risky actions). Emergency stop anytime:
`python -m desktop_worker estop`. Each run writes a browsable `replay.html`.

The agent can call **reliable tools** in one step instead of fumbling many GUI
actions: `create_text_file`, `open_app`, `open_url`, `focus_window`. It still has raw
mouse/keyboard for everything else; the AI chooses. Tools have **action/outcome
memory** (it sees what it tried and whether the screen changed) so it self-corrects.

### Other commands

```powershell
python -m desktop_worker status                 # config, backends, elevation
python -m desktop_worker observe --no-screenshot # one real structured observation
python -m desktop_worker create-file            # deterministic demo (no AI): make a desktop .txt
python -m desktop_worker --null demo            # scripted loop on Null backends (safe)
python -m desktop_worker report --session ai-do --task task  # HTML replay of a session
python -m desktop_worker estop / clear-stop     # emergency stop / clear
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
