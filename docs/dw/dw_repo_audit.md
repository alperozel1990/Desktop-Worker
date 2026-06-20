# dw_repo_audit.md — Repository audit

## Repo structure (after bootstrap)
```
C:\Desktop-Worker
  docs\
    requirements.md            # SOURCE OF TRUTH (read-only)
    dw\                        # ease-me workspace (this folder)
  src\desktop_worker\
    __init__.py  __main__.py  app.py  config.py  util.py
    schema\      actions.py observations.py results.py
    safety\      emergency_stop.py policy.py
    audit\       log.py
    broker\      cli_broker.py risk.py
    observation\ backends.py windows_backend.py observer.py
    actions\     backends.py windows_input.py executor.py
    loop\        task_loop.py
  tests\         8 test modules (71 tests)
  pyproject.toml  README.md  CLAUDE.md  .gitignore
  artifacts\     (generated; git-ignored)
```

## Language / framework / build
- **Language:** Python (>=3.11; dev machine 3.14.0).
- **Build system:** setuptools via `pyproject.toml` (src layout).
- **Packaging:** editable install `pip install -e ".[dev]"`. Extras: `windows`
  (mss, pywin32, uiautomation), `ocr` (pytesseract, Pillow), `dev` (pytest).
- **Core runtime deps:** none. Real desktop control needs `[windows]`.

## Architecture summary (how the relevant subsystem works)
Layered per requirements §5. The **core is pure/testable**; side-effecting
desktop control is isolated in **Windows backends** selected by factories that
fall back to **Null backends**. `app.Session` wires everything; `loop.TaskLoop`
runs observe→plan→act→verify→log with a pluggable `Planner`.

## Extension points (where to safely add code)
- New action family → add a row to `schema/actions.ACTION_SPECS` + a branch in
  `actions/executor._dispatch`.
- New observation data → extend `schema/observations` + the `Observer`.
- Perception → new `perception/` package feeding `Observation.elements`.
- AI planner → implement the `loop.Planner` Protocol (`next_step`).
- New CLI risk rules → extend `broker/risk` pattern tables.

## Risk areas (fragile / complex)
- `broker/cli_broker.py` — `shell=True` execution; security-critical. Keep it the
  only shell path; everything gated by classify+approval+audit.
- `actions/windows_input.py` & `observation/windows_backend.py` — ctypes/Win32;
  Windows-only, hard to unit test (covered only via Null backends + manual runs).
- `broker/risk.py` — heuristic classifier; false-negatives are a safety concern.

## Do-not-break list
- Emergency stop must be checked before every action and loop step.
- Every action/command must produce an audit entry.
- Malformed actions must never execute (schema validation first).
- No CLI execution outside the broker.

## Do-not-touch list
- `docs/requirements.md` (read-only).
- `artifacts/` (generated output).
- `Protocol` signatures in `*/backends.py` unless a card explicitly allows it
  (Null backends and tests depend on them).

## Build / test commands discovered
- Install: `python -m pip install -e ".[dev]"`
- Test: `python -m pytest`  (71 tests, ~5s, no display)
- Run: `python -m desktop_worker {status|observe|demo|estop|clear-stop}`

## Manual editor / tooling requirements
- Real screenshots: `[windows]` extra (`mss`).
- OCR (Phase 4): Tesseract binary + `[ocr]` extra.
- Live input/UAC validation: a human on a Windows desktop session.

## Naming conventions / code style
- snake_case modules/functions; PascalCase dataclasses; action `type` strings use
  dotted lowerCamel (`mouse.doubleClick`) to match requirements JSON examples.
- `to_dict()` on schema/result objects for JSON/audit serialization.
- Lazy heavy imports inside Windows backends; factories swallow import errors and
  return Null backends.
- Line length 100 (ruff configured).
