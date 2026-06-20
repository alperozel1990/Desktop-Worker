# dw_capabilities.md — Capability registry

## Things Claude can do directly (this repo, this environment)
- Read/write code, run `python -m pytest`, run the CLI (`status/observe/demo/estop`).
- Capture a **real** structured observation on this Windows machine (cursor,
  active window/process, screen size, visible windows) via ctypes — confirmed.
- Run CLI commands through the broker (low-risk auto; high-risk gated).
- Generate/maintain the ease-me workspace, roadmap, backlog, tracker.

## Things requiring user / manual action
- Validating **real mouse/keyboard motion & drag** on a live desktop — Tool: Windows desktop session (MANUAL-1).
- Installing the **`[windows]`** extra for real screenshots (`mss`) — Tool: terminal (MANUAL-2).
- Installing **Tesseract** for OCR (Phase 4) — Tool: installer + `[ocr]` extra.
- Testing **true UAC elevation** of a single command — Tool: non-admin shell + UAC prompt.
- Making the **initial git commit** (policy: no commit without permission) — Tool: terminal (MANUAL-3).

## Things requiring external tools or access not available now
- Browser-driven workflows at scale (Phase 5) — needs a real Chrome session.
- OCR/UIA element detection — needs Tesseract / uiautomation installed.

## Known missing capabilities (impact on roadmap)
- No real screenshot without `mss` → screenshot refs are placeholders; loop and
  audit chain still work. Impact: Phase 4 perception blocked until installed.
- No AI planner yet → tasks run via scripted/structured steps only. Impact:
  autonomy waits on DW-PLANNER-AI.

## Suggested future automations
- A `setup` CLI subcommand that installs extras and verifies Tesseract.
- A self-test command that exercises real input into a scratch Notepad and
  auto-verifies via clipboard/UIA.

## Manual tool requirements for this task
- Unity Editor: NO
- Blender: NO
- Mobile device: NO
- Firebase / Play Console: NO
- External API credentials: NO (until DW-PLANNER-AI needs a model API key)
