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
