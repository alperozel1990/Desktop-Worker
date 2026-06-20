# dw_roadmap.md — Desktop-Worker roadmap

- **Project goal:** AI-control-ready Windows desktop automation (observe-plan-act-verify-log).
- **Task prefix:** `dw`
- **Date:** 2026-06-20
- **Branch:** `master`
- **Source of truth:** `docs/requirements.md` (§19 roadmap mirrored here with repo reality).

This roadmap tracks the requirements' 7 phases against the current codebase.
Phases 1–3 have a working foundation; the cards in `dw_backlog.md` close the
remaining gaps and carry the project forward.

---

## Phase 1 — Local Control Foundation  ✅ implemented + tested
**Goal:** Prove Desktop-Worker can observe and control the local desktop.
**Scope:** screenshot capture, cursor read, mouse move/click/double/right,
keyboard type/hotkeys, clipboard set/get, active-window detection, action schema,
audit log, emergency stop.
**Non-goals:** OCR, UIA, browser flows, multi-agent.
**Dependencies:** none.
**Likely files touched:** `schema/`, `observation/`, `actions/`, `audit/`, `safety/`.
**Manual steps required:** YES — live-desktop input validation (MANUAL-1); real
screenshots need `[windows]` extra (MANUAL-2).
**Target validation level:** 3 (unit + local runtime); 4 once MANUAL-1 done.
**Risks:** input reliability across layouts; screenshot dep availability.
**Done criteria:**
- [x] Take a screenshot and save as an artifact (placeholder without `mss`).
- [x] Move mouse, click, type, hotkey (via executor + backend).
- [x] Every action written to the audit log.
- [x] User can stop execution immediately (estop, file + in-process).
**Complexity:** Medium.

## Phase 2 — Structured Action Loop  ✅ complete (loop + recovery)
**Goal:** Establish the observe-plan-act-verify loop.
**Scope:** structured observation object, structured executor, before/after
observation capture, verification interface, retry limits, final report.
**Non-goals:** AI planner, rich verification (needs perception).
**Dependencies:** Phase 1.
**Likely files touched:** `loop/`, `schema/results.py`.
**Manual steps required:** NO.
**Target validation level:** 3.
**Risks:** verification depth limited until Perception (Phase 4).
**Done criteria:**
- [x] A simple task runs as a sequence of structured actions (demo + tests).
- [x] Each action has a result record.
- [x] Failed verification causes retry/re-plan/safe stop (DW-LOOP-RECOVERY done):
  bounded retries with re-observe, optional planner re-plan, time/action limits.
**Complexity:** Medium.

## Phase 3 — Elevated CLI Broker  ✅ complete (real per-command UAC elevation)
**Goal:** Safe elevated command execution.
**Scope:** broker with preview, cwd handling, stdout/stderr/exit capture,
timeouts, risk classifier, approval gates, audit, session allow rules.
**Non-goals:** sandboxing the shell itself.
**Dependencies:** Phase 1 (audit, policy).
**Likely files touched:** `broker/`.
**Manual steps required:** YES for true UAC test (MANUAL-1 family / DW-CLI-ELEVATE).
**Target validation level:** 3 now; 4 after DW-CLI-ELEVATE manual UAC test.
**Risks:** per-command elevation + output capture is non-trivial.
**Done criteria:**
- [x] CLI runs only through the broker (no other shell path in repo).
- [x] CLI results fully captured (stdout/stderr/exit/timeout artifacts).
- [x] High-risk commands require approval (deny-by-default).
- [x] Elevated execution logged — true per-command UAC re-elevation with captured
  output (DW-CLI-ELEVATE done); `elevated` flag never overstates privilege.
  Real UAC prompt validated by user → MANUAL-4.
**Complexity:** High.

## Phase 4 — Perception Layer  ☐ not started
**Goal:** Help the AI understand the screen beyond raw pixels.
**Scope:** OCR, **Windows UI Automation** (preferred), element detection with
bounds + confidence + source attribution (uia/ocr/vision/heuristic).
**Non-goals:** full computer-vision model training.
**Dependencies:** Phase 1 observation.
**Likely files touched:** new `perception/` package, `schema/` (elements).
**Manual steps required:** YES — Tesseract install; live UIA testing.
**Target validation level:** 3–4.
**Risks:** OCR accuracy; UIA coverage varies by app.
**Done criteria:**
- [ ] Identify visible text and common controls.
- [ ] AI receives structured observation data + screenshot refs.
- [ ] UIA preferred when available.
**Complexity:** High.

## Phase 5 — Browser & Desktop Workflows  ☐ not started
**Goal:** Real user workflows in Chrome and common Windows UI.
**Scope:** Chrome navigation, form fill, file upload via picker, downloads, file
picker handling, window switching, drag-and-drop.
**Dependencies:** Phases 2 + 4.
**Likely files touched:** new `workflows/` package.
**Manual steps required:** YES — live browser/app testing.
**Target validation level:** 4.
**Risks:** dialog/timing fragility.
**Done criteria:**
- [ ] Complete a browser form workflow.
- [ ] Upload a file via native file picker.
- [ ] Download and locate a file.
**Complexity:** High.

## Phase 6 — Multi-Agent Orchestration  ☐ not started
**Goal:** Formalize Strategist / Implementer / Codex Auditor / Northstar Auditor.
**Scope:** roadmap state file (this workspace already seeds it), task handoff
schema, implementer spawn protocol, auditor workflows + feedback integration.
**Dependencies:** Phases 1–3.
**Likely files touched:** new `orchestration/` package; reuse `docs/dw/` schema.
**Manual steps required:** NO.
**Target validation level:** 3.
**Risks:** scope creep; keep agents narrow.
**Done criteria:**
- [ ] Strategist creates scoped tasks with acceptance criteria.
- [ ] Implementers execute and return reports.
- [ ] Auditors produce actionable findings; roadmap reflects completed/blocked.
**Complexity:** Medium.

## Phase 7 — Production Hardening  ☐ not started
**Goal:** Reliable enough for extended real use.
**Scope:** permission profiles, session replay, recovery flows, artifact retention,
privacy controls, robust UI (task input, status, screenshot preview, timeline,
approve/deny, pause/estop, audit viewer, CLI viewer, settings), integration tests,
long-running supervision.
**Dependencies:** all prior.
**Manual steps required:** YES — UI/UX validation.
**Target validation level:** 4–6.
**Done criteria:**
- [ ] Multi-step tasks run with clear supervision.
- [ ] Users can inspect/pause/approve/deny/stop.
- [ ] Logs + artifacts suffice to debug failures.
**Complexity:** High.

---

## Dependency graph
```
P1 ──> P2 ──> P5 ──> P7
  └──> P3 ──┐         ^
  └──> P4 ──┴> P5     │
P1..P3 ─────> P6 ─────┘
```

## Excluded / explicitly out of scope (for now)
| Item | Reason |
|---|---|
| Raw unrestricted shell | Forbidden by requirements §11. |
| Multi-monitor capture | Deferred; single-monitor MVP allowed (§6). |
| Cloud/remote control | Local Windows app only. |
| Non-Windows support | Out of scope; Null backends keep code importable elsewhere. |
| Training custom vision models | Use OCR/UIA + vision-capable model prompts instead. |
