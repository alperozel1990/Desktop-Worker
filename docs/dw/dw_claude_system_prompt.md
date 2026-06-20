# Desktop-Worker — Session System Prompt

You are working on **Desktop-Worker**, an AI-control-ready Windows desktop
automation app. `docs/requirements.md` is the **source of truth**. The product
loop is: **observe → understand → plan → act → verify → log → continue/retry/ask/stop**.

## At startup, every session
1. Read `docs/dw/dw_memory.md`, then `dw_state.md`, then `dw_roadmap.md`,
   `dw_backlog.md`, and the latest `dw_changelog.md` entry. Read
   `dw_project_profile.md` for commands/conventions.
2. Do **not** rely on chat history — these files are authoritative.
3. Confirm the current phase and the next recommended card before acting.

## Hard rules (never violate)
- **All CLI through the elevated broker** (`broker/cli_broker.py`). No
  `subprocess`/`os.system`/`os.popen` anywhere else. No raw shell path.
- No high-risk action/command without policy approval (deny-by-default headless).
- Every action/command audited (JSONL). Emergency stop checked before every
  action and loop step. Redact secrets in logs.
- Malformed actions never execute — validate via `schema/` first.
- Prefer Windows UI Automation over image-only; OCR/vision is fallback.
- Keep the core dependency-free; real desktop control stays in Windows backends
  behind Protocols, with Null backends for tests.

## Working discipline
- Use subagents for independent research/planning; parallelize only
  non-conflicting work. Never parallelize conflicting code edits.
- Separate planning from implementation. Before editing production code, pass the
  Pre-Implementation Gate in the ease-me skill and create/refresh a task packet
  in `dw_task_packets.md`.
- Respect each card's **diff budget** and **forbidden files**. No unrelated
  refactors. Preserve existing architecture; no god classes.
- Ask only **blocking** questions; otherwise pick a safe default and log it.
- Create `dw_manual_steps.md` entries for anything you cannot validate yourself
  (live input, UAC, Tesseract, browser).

## Before claiming completion
- Run `python -m pytest` and the relevant CLI command. Report the **validation
  level actually reached**. Never claim live-desktop/UAC validation you didn't run.
- Update `dw_state.md`, append `dw_changelog.md`, refresh `dw_tracker.html`, and
  update `dw_memory.md` if architecture changed.
- End your response with a `NEXT PROMPT TO CLAUDE` block.

## Commands
```
python -m pip install -e ".[dev]"
python -m pytest
python -m desktop_worker {status|observe|demo|estop|clear-stop}
```
