# dw_project_profile.md — Reusable repo profile

> Created once; referenced by future ease-me tasks in this repo.

## Project
- **Type:** Windows desktop automation app / AI agent runtime.
- **Language:** Python (>=3.11; dev 3.14.0).
- **Framework/engine:** none (stdlib + ctypes core); optional mss / pywin32 /
  uiautomation / pytesseract for real desktop/perception.
- **Layout:** src layout, package `desktop_worker` under `src/`.

## Commands
- **Install:** `python -m pip install -e ".[dev]"` (add `[windows]`/`[ocr]` as needed)
- **Test:** `python -m pytest`
- **Run:** `python -m desktop_worker {status|observe|demo|estop|clear-stop}`
- **Lint (optional):** `ruff check src tests`

## Important folders
- `src/desktop_worker/` — application code (8 layers; see repo audit).
- `tests/` — pytest suite, all on Null backends (no display).
- `docs/` — `requirements.md` (source of truth) + `dw/` (ease-me workspace).
- `artifacts/` — generated screenshots/observations/cli/audit/reports (git-ignored).

## Forbidden folders / files
- `docs/requirements.md` (read-only source of truth).
- `artifacts/` (generated).
- `*/backends.py` Protocol signatures (stable contract for Null backends/tests).

## Architecture principles (invariants)
- Core is dependency-free and unit-testable; side effects live in Windows backends
  behind Protocols with Null fallbacks.
- The loop (observe-plan-act-verify-log) is the product; nothing bypasses it.
- All CLI through the broker; no raw shell. Everything audited. Estop honored.
- Structured actions/observations validated before use; deny-by-default for risk.

## Coding style
- snake_case / PascalCase; dotted action type strings matching requirements JSON.
- `to_dict()` serialization; lazy Windows imports; line length 100.

## Manual tools required
- Real screenshots: `mss`. OCR: Tesseract. Live input/UAC: human Windows session.

## Known pitfalls
- ctypes/Win32 backends are Windows-only and only logic-tested via Null backends.
- `shell=True` in the broker is security-sensitive — keep it gated and singular.
- Risk classifier is heuristic; prefer escalating to higher risk when unsure.
- Console (cp1252) mangles non-ASCII when printing; files are UTF-8 — keep CLI
  output ASCII-friendly.

## User preferences for this repo
- Requirements doc is source of truth; stay aligned to AI-control-ready north star.
- Small, testable, structured; UI Automation preferred over image-only.
- **Git workflow is active.** Remote: `origin` → github.com/alperozel1990/Desktop-Worker.
  User wants to use git on this project; committing and pushing are allowed.
  Keep commits scoped per card; end commit messages with the Co-Authored-By line.
