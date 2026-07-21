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

## Phase 4 — Perception Layer  ✅ complete (OCR + UIA + loop-wiring)
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
- [x] Identify visible text and common controls — OCR text + UIA controls done.
- [x] AI receives structured observation data + screenshot refs — elements now
  flow into the loop's audit records (DW-PERCEPTION-WIRE).
- [x] UIA preferred when available (DW-PERCEPTION-UIA; `merge_elements` UIA-first).
**Complexity:** High.

## §22 AI-CONTROL-READY — ✅ REALIZED (live AI agent: `do "<task>"`)
The AI now drives the loop end-to-end: observe → perceive → AI-decide → gated-act
→ verify → continue. Genuine dynamic control (DW-AGENT-DO), verified on the real
desktop, all safety below the planner. This was the product north star.

## Phase 5 — Browser & Desktop Workflows  ✅ complete (window/drag, file picker, download, Chrome form)
**Goal:** Real user workflows in Chrome and common Windows UI.
**Scope:** Chrome navigation, form fill, file upload via picker, downloads, file
picker handling, window switching, drag-and-drop.
**Dependencies:** Phases 2 + 4.
**Likely files touched:** new `workflows/` package.
**Manual steps required:** YES — live browser/app testing.
**Target validation level:** 4.
**Risks:** dialog/timing fragility.
**Done criteria:**
- [x] Complete a browser form workflow (DW-WF-BROWSER; live = MANUAL-WF-4).
- [x] Upload a file via native file picker (DW-WF-FILEPICKER; live = MANUAL-WF-2).
- [x] Download and locate a file (DW-WF-DOWNLOAD; live = MANUAL-WF-3).
- [x] Window switching + drag-and-drop (DW-WF-WINDOW; live = MANUAL-WF-1).
**Complexity:** High.

## Phase 6 — Multi-Agent Orchestration  ✅ complete (schema + roles + coordinator)
**Goal:** Formalize Strategist / Implementer / Codex Auditor / Northstar Auditor.
**Scope:** roadmap state file (this workspace already seeds it), task handoff
schema, implementer spawn protocol, auditor workflows + feedback integration.
**Dependencies:** Phases 1–3.
**Likely files touched:** new `orchestration/` package; reuse `docs/dw/` schema.
**Manual steps required:** NO.
**Target validation level:** 3.
**Risks:** scope creep; keep agents narrow.
**Done criteria:**
- [x] Strategist creates scoped tasks with acceptance criteria (DW-ORCH-SCHEMA/ROLES).
- [x] Implementers execute and return reports (Implementer + injectable execute_fn).
- [x] Auditors produce actionable findings; coordinator reflects accepted/blocked
  (DW-ORCH-COORD). Live full run = MANUAL-ORCH-1.
**Complexity:** Medium.

## Phase 7 — Production Hardening  ✅ complete (hardening + Tkinter control UI)
**Goal:** Reliable enough for extended real use.
**Scope:** permission profiles, session replay, recovery flows, artifact retention,
privacy controls, robust UI (task input, status, screenshot preview, timeline,
approve/deny, pause/estop, audit viewer, CLI viewer, settings), integration tests,
long-running supervision.
**Dependencies:** all prior.
**Manual steps required:** YES — UI/UX validation.
**Target validation level:** 4–6.
**Done criteria:**
- [x] Multi-step tasks run with clear supervision (Tkinter `ui`: live timeline +
  screenshot; loop on a worker thread). GUI interaction = MANUAL-UI-1.
- [x] Users can inspect/pause/approve/deny/stop (UiController + ApprovalQueue
  blocking handshake; STOP/Pause/Resume/Approve/Deny).
- [x] Logs + artifacts suffice to debug failures (audit timeline + session replay
  HTML + artifact retention via `clean-artifacts`).
- [x] Permission profiles + app allow/deny + artifact retention (DW-HARDEN).
**Complexity:** High.

## Phase 8 — External AI Interface (MCP server)  ✅ complete (live = MANUAL-MCP-1)
**Goal:** Make Desktop-Worker usable BY OTHER AI AGENTS. Today the only driver is
the *built-in* Claude CLI planner (`do`/`draw`); there is no programmatic entry
point, so an external agent (another Claude session, Cursor, Claude Desktop, a
custom agent) cannot use Desktop-Worker as its "hands". This phase exposes the
loop's capabilities over the **Model Context Protocol (MCP, stdio)** so any
MCP-capable agent becomes the planner.
**Scope:** A pure, dependency-free `AgentBridge` that maps MCP tool calls →
existing `executor.execute(parse_action(...))` / observer / perceiver / tools
registry / broker, returning JSON-serializable results. A thin `server.py`
(lazy-imported `mcp` SDK / FastMCP) registers the bridge methods as MCP tools and
serves over stdio. New CLI `mcp` command. The external AI can: `observe`,
`perceive` (UIA/OCR elements with ids+bounds), `screenshot`, mouse/keyboard/
clipboard primitives, `run_tool` (create_text_file/open_app/open_url/focus_window/
drag_drop/sketch), `run_cli` (broker-gated), and `status/estop/clear_stop`.
**Non-goals:** A network/SSE transport (stdio only for the MVP); bypassing any
safety gate; a new action family (the existing schema + `tool.run` suffice);
auto-approving high-risk actions (approval stays user-controlled via profiles).
**Dependencies:** all prior phases (reuses executor, perception, tools, broker, safety).
**Likely files touched:** new `mcp_server/` package; `__main__.py`; `pyproject.toml`.
**Manual steps required:** YES — connect a real external MCP client and drive a
complex task (MANUAL-MCP-1); prove reliability on the priority scenarios.
**Target validation level:** 3 now (unit + Null-backend); 4 once an external
client drives a live task.
**Risks:** MCP SDK API drift (mitigate: lazy import + bridge fully testable
without the SDK); approval model when headless (mitigate: profile-selectable,
deny-by-default above the threshold); element-id stability across observe/act.
**Done criteria:**
- [x] `AgentBridge` maps every capability through the existing executor/observer/
  perceiver/broker; malformed actions still rejected; estop+policy+audit below it.
- [x] Thin MCP server registers the tools (22) and serves stdio; SDK lazy-imported.
- [x] CLI `mcp` command starts the server; `--profile` selects the safety preset.
- [x] Null-backend unit tests for the bridge + a registration test without the SDK.
- [x] Real-FastMCP in-process e2e smoke (observe/click/list_tools work; malformed
  rejected; estop halts) — no SDK API drift. 373 tests.
- [ ] Live external-client validation queued as MANUAL-MCP-1 (priority scenarios:
  multi-step app, browser, file/system, draw, Unity Editor manual tasks).
**Complexity:** High.

## Phase 9 — 3D capabilities + input reliability (skill + playbooks)  ✅ complete (LIVE-validated)
**Goal:** Make the tool genuinely usable for real desktop work by other AI agents — close the
input-reliability gaps found in live use and add 3D-app perception/control — and ship a reusable,
self-improving usage layer (a user-scope skill + per-app playbooks) so any AI session benefits.
**Scope (all done + LIVE-validated on the real desktop):**
- **Input fixes:** clipboard set/get 64-bit handle bug (`OverflowError`) fixed; `press_key`/`hotkey`
  numpad+nav keys; `type_text` now reaches GHOST apps (Blender/games) via VkKeyScanW VK keystrokes
  (Unicode fallback for AltGr/off-layout). (DW-CLIP-FIX, DW-KEYS-NUMPAD, DW-INPUT-GHOST.)
- **3D tools:** `inspect_3d` (multi-view montage 3D perception; eased orbit that registers on GHOST;
  crop; identical-tile warning), `orbit` (eased middle-drag), `capture_burst` (timestamped
  snapshots-while-rotating; DXcam opt-in). Research-grounded (Agent3D-Zero/Think3D/Set-of-Mark; DXcam).
  (DW-3D-INSPECT Tier 3, DW-3D-CAPTURE Tier 2, Tier 1 = docs.)
- **Usage layer:** user-scope `desktop-worker` skill (thin SKILL.md + living REFERENCE.md) + per-app
  **playbooks** (INDEX + ltspice/blender/unity) with verify-before-save / generic-entry /
  read-before-write-after rules (deep-research-designed) so AI sessions self-improve from real runs.
**Validation:** Level 4 (live real desktop) — an external MCP agent built an LTSpice voltage divider
(sim verified 1.5V) and a low-poly Blender car; inspect_3d/capture_burst/type_text confirmed in Blender.
**Done criteria:** [x] input gaps closed + live-verified · [x] 3D perception + capture tools, live ·
[x] reusable skill + self-improving playbooks shipped. **Complexity:** High.

---

## Phase 10 — Measurement (eval harness)  ☐ todo — BLOCKS Phase 11
**Goal:** Be able to *prove* whether a change to the agent-facing surface helps or hurts.
Today there is no success-rate, step-count, or latency measurement anywhere in the repo —
so every Phase 11 claim would be unfalsifiable. Measurement comes first, by design.

**Research basis (deep research, 2026-07-21 — see `dw_web_research.md`):**
- Anthropic (Jan 2026): "20-50 simple tasks drawn from real failures is a great start...
  20-50 hand-reviewed examples you're confident in will outperform hundreds of synthetic
  examples you haven't verified."
- Statistical caveat (Miller 2024, arXiv 2411.00640): a 20-50 task suite has wide
  confidence intervals — run multiple trials per task and report variance, or changes
  below ~10-15pp are indistinguishable from noise.
- WindowsAgentArena-V2 found two hygiene defects in V1 to avoid: no VM state reset
  between tasks (mutations leak across episodes) and "infeasible hacking" (weaker models
  score spuriously on impossible tasks). Implement per-task reset from day one and score
  infeasible tasks on a separate axis.
- Deterministic verifiers align with human judgment far better than LLM-as-judge
  (94.1% vs 79.2% task-level in one 2026 study) — oracles, not critics.

**Scope — a three-tier harness (the tiering is a project decision, not a paper finding;
it exists because the user is quota-sensitive and Phase 11 is a tool-surface question):**
- **Tier A1 — harness unit tests.** Null backends, runs in CI on every change. Zero
  Claude quota. Validation level 3.
- **Tier A2 — live capability evals.** Deterministic scripted scenarios against real
  Win11 apps (Notepad, Paint, File Explorer, Settings, Calculator). Measures the *tool
  surface*, not the AI: does `perceive` contain the target element, is an element id
  stable across two calls, does `screenshot` return decodable bytes, does `act_many`
  reach the same end state as N separate acts. **Zero Claude quota**, real signal,
  validation level 4. This is the tier Phase 11 is graded against.
- **Tier B — live task evals.** Full `do "<task>"` runs scored by oracles. Costs Claude
  quota, so it is opt-in behind an explicit flag and run rarely with small N. The
  10-15pp noise caveat applies here, not to A2 (A2 is deterministic pass/fail).

**Metrics:** success rate (+ variance across trials), step count, wall-clock per step and
per task, model round-trip count, observation payload size. Step count and round-trips
matter because OSWorld-Human shows model calls are 87-97% of end-to-end latency and even
the best agents take 2.7-4.3x more steps than a human-optimal trajectory.

**Non-goals:** reproducing OSWorld/WindowsAgentArena; a VM/snapshot layer; scoring against
published SOTA numbers (they are stale and measured on different harnesses).
**Dependencies:** none — deliberately first.
**Likely files touched:** new `eval/` package; `__main__.py`; new tests.
**Manual steps required:** YES — Tier A2 and Tier B need a live Windows desktop session
(MANUAL-EVAL-1, MANUAL-EVAL-2).
**Target validation level:** 3 for the harness itself; 4 once A2 runs against real apps.
**Risks:** the suite bakes in today's assumptions and ossifies (mitigate: seed from real
audit-log failures, not imagination); A2 scenarios depend on app UI that Windows updates
may change (mitigate: oracles assert intent, and a broken scenario must fail loudly rather
than silently pass).
**Done criteria:**
- [ ] `eval/` package: task spec, deterministic oracles, runner with per-task reset,
      N-trial variance reporting, metrics collection.
- [ ] A seed suite of >=20 tasks, each traceable to a real observed failure or a Phase 11
      acceptance criterion.
- [ ] Tier A1 green in CI on Null backends; Tier B gated behind an explicit opt-in flag.
- [ ] `python -m desktop_worker eval` runs a suite and prints success rate + variance +
      step/latency/round-trip metrics; results persisted as JSON for before/after diffing.
- [ ] A recorded BASELINE run committed, so Phase 11 has something to be compared against.
**Complexity:** Medium-High.

## Phase 11 — Agent-facing surface gaps (audit-driven)  ☐ todo — graded by Phase 10
**Goal:** Close the concrete defects a code audit found in the MCP surface (2026-07-21).
These are the highest success-rate leverage available, and four of the five also cut step
count — the dominant latency term.

**Research basis:** model round-trips are 87-97% of end-to-end latency vs 1-3% for
screenshot+input (OSWorld-Human, MLSys 2026), so batching and fewer blind re-observations
beat any capture-rate work; hybrid UIA+SoM+OCR perception beats pixel-only or a11y-only
(WindowsAgentArena/Navi, OSCAR ICLR 2025); compressing a11y payloads cut tokens to 22%
while *adding* +5.1pp success (A11y-Compressor).

**Scope (cards DW-MCP-IMAGE, DW-ELEM-STABLE, DW-PERCEIVE-RANK, DW-ACT-BATCH,
DW-ACT-SETTLE — see backlog for each).**
**Non-goals:** a local GPU grounding model (see Excluded); DXcam capture-rate work;
new schema action families beyond what batching needs.
**Dependencies:** Phase 10 (each card must show a measured delta).
**Manual steps required:** YES — live re-validation per card via Tier A2.
**Target validation level:** 3 per card, 4 via the A2 suite.
**Done criteria:**
- [ ] Every card lands with a before/after Tier A2 measurement, not an assertion.
- [ ] No card regresses the existing 400-test suite or the safety invariants.
**Complexity:** Medium per card.

---

## Dependency graph
```
P1 ──> P2 ──> P5 ──> P7
  └──> P3 ──┐         ^
  └──> P4 ──┴> P5     │
P1..P3 ─────> P6 ─────┘
P8 ──> P9 ──> P10 ──> P11      (P10 measurement gates P11)
```

## Excluded / explicitly out of scope (for now)
| Item | Reason |
|---|---|
| Raw unrestricted shell | Forbidden by requirements §11. |
| Multi-monitor capture | Deferred; single-monitor MVP allowed (§6). |
| Cloud/remote control | Local Windows app only. |
| Non-Windows support | Out of scope; Null backends keep code importable elsewhere. |
| Training custom vision models | Use OCR/UIA + vision-capable model prompts instead. |
| **Local GPU grounding model** (UI-TARS / OmniParser / UGround class) | **Dropped on evidence (2026-07-21 deep research).** Eight verified-refuted claims all shared the premise that dedicated grounding models beat frontier VLMs; 2026 data contradicts it (Claude Opus 4.8 ~0.879 on ScreenSpot-Pro). The 2025-era 18.9%/19.5%/48.1% figures are stale — never build on them. Revisit ONLY if a Phase 10 A/B on our own apps (Blender/Unity/CAD) shows UIA+frontier-VLM losing; no source has measured that combination. |
| DXcam / capture-rate optimisation | Low ROI: screenshot+input is 1-3% of end-to-end latency vs 87-97% for model round-trips (OSWorld-Human, MLSys 2026). The pending `capture_burst fast:true` live test stays optional. |
| Unconditional crop-and-zoom grounding | Worth ~+7pp on ScreenSpot-Pro but costs 2-4x model calls per grounding action — directly opposed to the round-trip-reduction finding. If adopted, gate on low first-pass confidence or on UIA returning no candidate box. Deferred to Phase 13. |
