# CLAUDE.md — Desktop-Worker

Guidance for any AI/agent session working in this repository.

## What this project is

An **AI-control-ready Windows desktop automation app**. The product north star
and full spec live in `docs/requirements.md` — **treat it as the source of
truth.** The live plan/state lives in `docs/dw/` (read `dw_memory.md` then
`dw_state.md` first).

## The loop is the point

Everything serves the loop: **observe → understand → plan → act → verify → log
→ continue/retry/ask/stop**. A change that adds an action but skips
verification, logging, or safety is incomplete.

## Hard rules (do not violate)

1. **All CLI goes through the elevated broker** (`broker/cli_broker.py`). Never
   add `subprocess`, `os.system`, or `os.popen` anywhere else. There is no raw
   shell path, by design.
2. **Never execute high-risk actions/commands without policy approval.** Headless
   default is deny.
3. **Every meaningful operation is audited** (`audit/log.py`, JSONL). Keep it so.
4. **Emergency stop is sacred** — checked before every action and loop step.
   Don't add execution paths that bypass `EmergencyStop.check()`.
5. **Prefer Windows UI Automation** (Phase 4) over image-only automation; use
   screenshot/OCR/vision as fallback, not the only strategy.
6. **Structured actions and observations only** — validate via `schema/` before
   executing. Malformed actions must never run.
7. **Keep the core dependency-free and testable.** Real desktop control belongs
   in Windows backends behind the `DesktopBackend` / `InputBackend` protocols,
   with `Null` backends for tests. Heavy libs import lazily.

## Working style

- Use the **ease-me** workflow. Read `docs/dw/dw_memory.md` and `dw_state.md` at
  startup; update `dw_state.md`, `dw_changelog.md`, and `dw_tracker.html` after
  every task. Don't rely on chat history alone.
- Respect the **diff budget** and **forbidden files** in each backlog card.
- Run `python -m pytest` before claiming completion; report the validation level
  actually reached. Don't claim live-desktop validation you didn't run.

## Commands

```powershell
python -m pip install -e ".[dev]"     # install + dev deps
python -m pytest                       # run tests (Null backends, no display)
python -m desktop_worker status        # config + backends + elevation
python -m desktop_worker observe       # one real structured observation
python -m desktop_worker --null demo   # full loop, safe, Null backends
```
