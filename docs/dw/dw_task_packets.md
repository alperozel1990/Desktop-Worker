# dw_task_packets.md — Execution packets

> One packet per Execute-Card session. Append new packets; never overwrite old ones.

---

## TASK PACKET BOOTSTRAP-1 — 2026-06-20

**Goal:** Bootstrap the repo and implement the Phase 1 minimal working foundation
for Desktop-Worker, ready for continued autonomous implementation.
**Non-goals:** Perception (OCR/UIA), browser workflows, AI planner, full UI,
true per-command UAC elevation.
**Current state before:** Empty repo with only `docs/requirements.md`.
**Exact files inspected before coding:** `docs/requirements.md` (full),
ease-me `file_specs.md`, `elevated_launcher_template.bat`; environment probes
(`python`, `claude`, `git` versions; `claude --help` flags).
**Files allowed to edit:** entire new `src/`, `tests/`, repo root config, `docs/dw/`.
**Files forbidden to edit:** `docs/requirements.md`.
**Expected behavior after:** `pytest` green; CLI `status/observe/demo/estop` work;
real observation returns live desktop data; full ease-me workspace present.
**Data / network implications:** none (no network used; artifacts local & git-ignored).
**UI/UX implications:** CLI only (UI is Phase 7).
**Manual editor steps required:** MANUAL-1 (live input), MANUAL-2 (mss), MANUAL-3 (commit).
**Validation commands:** `python -m pip install -e ".[dev]"`; `python -m pytest`;
`python -m desktop_worker --null demo`; `python -m desktop_worker observe`.
**Manual validation scenario:** See MANUAL-1 (type into Notepad with real backend).
**Rollback plan:** This is the initial state; to discard, remove `src/`, `tests/`,
`docs/dw/`, root configs (repo had only `docs/requirements.md`).
**Diff budget:** N/A (greenfield bootstrap; user-authorized).
**Done criteria:**
- [x] 8 layers implemented with Null + Windows backends.
- [x] Safety, audit, estop, broker present from the start.
- [x] 71 tests pass; loop runs end-to-end.
- [x] ease-me workspace + launchers created.
**Stop conditions:** Stop and ask before implementing any further backlog card —
each needs its own packet + Pre-Implementation Gate.

---

## Packet: DW-WF-PICKER-OPENBTN — File-dialog confirm via ENTER (2026-06-25)
**Source card:** DW-WF-PICKER-OPENBTN (backlog). **Live finding:** MANUAL-WF-2.
**Pre-Implementation Gate:** PASS — scope tiny, files scoped, Null-testable, no safety
files touched, rollback trivial.
**Files allowed:** `src/desktop_worker/workflows/file_dialog.py`,
`tests/test_wf_file_dialog.py`.
**Files forbidden:** `schema/`, `actions/`, `safety/`, `broker/`, `audit/`, `__main__.py`.
**Plan:** `choose_file` confirms with a single `keyboard.press ENTER` after typing the
path into the focused File name field, instead of clicking a name-matched "Open"/"Save"
button. The Win11 dialog exposes ~5 controls named "Open" (split-button arrows), so a
name-based click landed wrong; ENTER activates the dialog default and is immune to that.
**Tests:** confirm-via-ENTER on open & save; ENTER even when a button center is offered
(immune to multi-Open); existing empty-path / no-field fail-safe unchanged.
**Rollback:** `git checkout -- src/desktop_worker/workflows/file_dialog.py`.
**Diff budget:** 1 production file + 1 test file.

---

## Packet: DW-WF-BROWSE-FOREGROUND — Foreground-gate before address-bar typing (2026-06-25)
**Source card:** DW-WF-BROWSE-FOREGROUND (backlog). **Live finding:** MANUAL-WF-4.
**Pre-Implementation Gate:** PASS — additive, injectable, default path unchanged,
no safety files, rollback trivial.
**Files allowed:** `src/desktop_worker/workflows/browser.py`, `__main__.py`
(`_cmd_browse` wiring only), `tests/test_wf_browser.py`.
**Files forbidden:** `schema/`, `actions/`, `safety/`, `broker/`, `audit/`, `browser_ui.py`.
**Plan:** Add `ensure_foreground(title_contains, *, active_window, switch=None, ...)` that
focuses a matching window (re-using `switch_window`) then polls `active_window()` until the
foreground window's title/process matches. `navigate(..., foreground=None)` and
`submit_form(..., foreground=None)` gain an injectable zero-arg gate: if provided and it
returns False, abort BEFORE any Ctrl+L/type/ENTER (never type into the wrong window).
`_cmd_browse` builds the gate from the real desktop backend's `active_window`. Default
`foreground=None` keeps existing behavior/tests.
**Tests:** ensure_foreground succeeds once active is chrome / times out otherwise;
navigate aborts (no input dispatched) when gate False; navigate proceeds when gate True;
existing no-gate navigate/submit tests unchanged.
**Rollback:** `git checkout -- src/desktop_worker/workflows/browser.py src/desktop_worker/__main__.py`.
**Diff budget:** 2 production files + 1 test file.

---

## Packet: DW-MCP-SERVER — Expose Desktop-Worker as an MCP server (2026-06-30)
**Source card:** DW-MCP-SERVER (backlog, Phase 8). **Driver:** user — "this tool must be
usable BY other AI agents" + chose MCP server + scenarios: multi-step app / browser /
file-system / draw / Unity Editor manual tasks.
**Pre-Implementation Gate:** PASS (see session report) — additive package, reuses the
existing executor/observer/perceiver/tools/broker choke points, no safety/schema/executor
edits, SDK lazy-imported so core stays dep-free, Null-backend testable, rollback trivial.
**Branch:** `dw/phase8-mcp`.
**Current state before:** All 7 phases done + merged to `main`; only driver is the
built-in Claude CLI planner (`do`/`draw`). No programmatic interface for external agents.
**Exact files inspected before coding:** `app.py` (Session wiring), `actions/executor.py`
(execute choke point + dispatch table), `tools/registry.py` + `tools/builtin.py`,
`schema/actions.py` (`parse_action`/ACTION_SPECS), `safety/profiles.py` (`build_policy`),
`perception/perceiver.py` (`perceive`), `__main__.py` (`_cmd_do` wiring), `pyproject.toml`,
`tests/test_tools.py` (style). Confirmed MCP SDK NOT installed (lazy import required).
**Files allowed:** new `src/desktop_worker/mcp_server/{__init__,bridge,server}.py`,
`src/desktop_worker/__main__.py`, `pyproject.toml`, new `tests/test_mcp_bridge.py`,
`tests/test_mcp_server_register.py`.
**Files forbidden:** `schema/`, `actions/executor.py`, `safety/`, `audit/`,
`broker/cli_broker.py`, `docs/requirements.md`, `artifacts/`.
**Plan:**
1. `bridge.py` — pure `AgentBridge(session, tools, perceiver)`: each capability builds a
   dict, calls `parse_action` then `session.executor.execute(...)` (or observer/perceiver/
   broker), returns a JSON-safe dict `{ok, error, detail/...}`. `perceive()` returns
   elements with per-observe integer ids + type + text + bounds + center so the external
   AI can target controls; `act(action_dict)` is the general escape hatch (any valid
   structured action). `run_tool`/`run_cli`/`list_tools`/`status`/`emergency_stop`/
   `clear_stop`. Factory `build_agent_bridge(real, profile, approver)` wires real backends +
   the same tool set as `_cmd_do` (CreateTextFile/OpenApp/OpenUrl/FocusWindow/DragDrop/Sketch).
2. `server.py` — lazy `from mcp.server.fastmcp import FastMCP` inside `serve()`. Pure
   `register(server, bridge)` decorates bridge methods as MCP tools (works with a fake
   server object → testable without the SDK). `serve(bridge, name)` runs stdio.
3. `__main__.py` — add `mcp` subcommand: `_cmd_mcp` builds the bridge via the factory and
   calls `serve`; `--profile` selects the safety preset (default standard); `--null` for a
   backend-free smoke. Helpful error if the SDK is missing (`pip install -e ".[mcp]"`).
4. `pyproject.toml` — add `[mcp]` extra: `mcp>=1.2`.
**Validation commands:** `python -m pytest`; `python -m desktop_worker mcp --help`;
`python -m desktop_worker --null mcp` (expects a clear "install mcp" message since the SDK
isn't installed) — proves wiring without the SDK.
**Manual validation:** MANUAL-MCP-1 — register the server in a real MCP client (Claude
Desktop/Code config) and drive a complex multi-step task end-to-end; prove the priority
scenarios incl. Unity Editor manual work.
**Rollback:** `git checkout -- src/desktop_worker/__main__.py pyproject.toml` and
`rm -r src/desktop_worker/mcp_server tests/test_mcp_*`.
**Diff budget:** 3 new production files + 1 changed (`__main__.py`) + pyproject; 2 test files.
**Done criteria:** see backlog card DW-MCP-SERVER.
**Stop conditions:** Stop before adding a network transport or any new schema action —
those are separate cards.
