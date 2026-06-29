# dw_manual_steps.md — Manual step queue

Actions Claude cannot fully perform/validate itself.

---

## MANUAL-MCP-1 — ⭐⭐⭐ Drive Desktop-Worker from an external AI agent over MCP  ☐
**Status:** [ ] Waiting · **Blocking:** NO · **Added by:** DW-MCP-SERVER (Phase 8)
**Why this is the headline test:** it proves the new north-star — *another AI agent
can use this tool*. Claude validated the server in-process (real FastMCP: 22 tools, a
full call → executor → result path, malformed rejected, estop halts). What only YOU can
do is connect a real external MCP **client** and watch it drive the real desktop.
**One-time setup:**
1. Install the SDK: `python -m pip install -e ".[mcp]"` (adds `mcp`).
2. Register the server in an MCP client. For **Claude Desktop** (or Claude Code's MCP
   config), add a server entry like:
   ```json
   {
     "mcpServers": {
       "desktop-worker": {
         "command": "python",
         "args": ["-m", "desktop_worker", "mcp"]
       }
     }
   }
   ```
   (Add `"--profile","strict"` to the args to be prompted/denied more; note: over
   stdio there is no console to approve HIGH-risk, so `standard` auto-runs low/medium
   and denies high. Emergency stop any time: `python -m desktop_worker estop`.)
**What to try (the priority scenarios you chose):** ask the external agent to —
- open Notepad, type text, save (multi-step app work);
- open Chrome and navigate / fill a form (browser);
- create/rename a file, run a short `run_cli` command (file/system);
- `run_tool sketch` to draw a figure in Paint (draw);
- in the **Unity Editor**, perform a manual GUI task (e.g. select a GameObject, click a
  menu, set a field) by `perceive` → click `center` → `type_text` — desktop-level control,
  complementary to the Unity MCP.
**What Claude needs back:** which scenarios worked vs. failed, and for failures what
`perceive` returned (UIA element coverage) — so we can tune perception/reliability
(this is exactly where the "another AI couldn't do it" gap gets closed for real).

## MANUAL-11 — ⭐⭐⭐ Watch the AI draw with best-of-N + judge (`draw` command)
**Status:** [ ] Waiting  (Claude live-validated the DETERMINISTIC half: clean canvas
+ SVG cat in real Paint — `artifacts/cat_attempts/cat_v2_clean_best.png`, no red; and
verified the Claude integration. The AI best-of-N half uses your subscription, so it's
yours to watch.)
**Blocking:** NO
**Tool:** PowerShell + your `claude` login + desktop + MS Paint
**Added by:** DW-AGENT-DRAW
**Instructions:**
1. `cd C:\Desktop-Worker` ; (first time) `python -m pip install -e ".[windows]"`
2. `python -m desktop_worker draw "a cat"`
   (try also: `draw "a house"`, `draw "a smiling sun"`, or `--candidates 4`)
3. Watch the console: the AI proposes several SVG drawings → they're rendered offline
   → an AI judge picks the best → ONLY the winner is drawn on a freshly CLEANED canvas
   (Pencil + black; no raw scribbles possible) → one verify/correct pass. ~3-4 Claude
   calls total. Stop anytime: `python -m desktop_worker estop` (another window).
**What Claude needs back:** Did a clean, recognizable figure appear (no red mess)?
Paste the `[draw]` console lines if anything looked off (which candidate it chose,
canvasSource uia/client). The candidate previews + montage are saved under
`artifacts/sessions/ai-draw/task/draw/`.

---

## MANUAL-10 — ⭐⭐ Watch the AI draw a cat with the `sketch` pipeline (v1)
**Status:** [~] Partially validated by Claude — the FULL drawing pipeline (real mouse
+ real UIA canvas detection + render) was run live in real Win11 Paint and produced a
clean, recognizable cat: `artifacts/cat_attempts/cat_live_best.png`. What remains for
YOU is to watch the *AI-driven* version end-to-end (the `do` command, which also calls
Claude to plan the program — uses a little quota).
**Blocking:** NO
**Tool:** PowerShell + your `claude` login (no API key) + your desktop + MS Paint
**Added by:** DW-AGENT-SKETCH
**Instructions:**
1. `cd C:\Desktop-Worker` ; (first time) `python -m pip install -e ".[windows]"`
   (the `[windows]` extra brings `uiautomation` for canvas detection + `mss`/`Pillow`
   for the cropped vision look).
2. `python -m desktop_worker do "open Paint and draw a cat" --vision`
3. Watch: the AI opens Paint, then makes ONE `sketch` tool call with the whole cat as
   primitives on a 0..100 grid; the app finds Paint's real canvas and draws smooth
   circles/curves (no ribbon overdraw, no diagonal slash). Then it takes ONE cropped
   look and may issue ONE correction `sketch`. Stop anytime: `python -m desktop_worker
   estop` (another window).
**What Claude needs back:** Did a recognizable cat land INSIDE the canvas? If the
figure was offset/clipped, tell me the Paint version (Win11 Store Paint vs classic
mspaint) and paste the printed `[AI]` steps — the `canvasSource` in the audit
(`uia` vs `client`) tells me whether canvas detection used UI Automation or the
geometric fallback, so I can tune the insets.

---

## MANUAL-9 — ⭐⭐ Run the GENUINE live-AI demo (the real AI control)
**Status:** [x] DONE — validated live 2026-06-25 with the user observing. `do "Open
Notepad using the Run dialog, then type merhaba"` ran 6/6 steps; the AI adapted to
leftover `calc` text (clicked field → Ctrl+A → typed notepad), launched Notepad,
typed merhaba, self-verified via UIA.
**Blocking:** NO
**Tool:** PowerShell + your `claude` login (no API key) + your desktop
**Added by:** DW-AGENT-DO
**Instructions:**
1. `cd C:\Desktop-Worker` ; (first time) `python -m pip install -e ".[windows]"`
2. `python -m desktop_worker do "Open Notepad using the Run dialog, then type merhaba"`
3. Watch the AI print its reasoning + chosen action each step and drive the desktop
   until done. Try your own: `do "open Calculator and compute 12 times 9"`.
   Stop anytime: `python -m desktop_worker estop` (another window).
**What Claude needs back:** did it complete? If it stalled/misclicked, paste the
printed [AI] steps so I can tune it. Honest limit: best on normal Win apps; some
Electron/Chromium apps hide their UI from accessibility.

---

## MANUAL-8 — ⭐ Run the create-file demo and watch (deterministic, scripted)
**Status:** [x] DONE — validated live 2026-06-25 with the user observing. 11/11 steps;
`dw-demo.txt` created on the desktop with "başlıyoruz" (Turkish chars intact).
**Blocking:** NO
**Tool:** PowerShell + your desktop
**Added by:** DW-WORKFLOW-CREATEFILE
**Instructions:**
1. `cd C:\Desktop-Worker`
2. (first time) `python -m pip install -e ".[windows]"`
3. `python -m desktop_worker create-file` — watch the mouse right-click the
   desktop, create New → Text Document, name it, open it, type "başlıyoruz", save.
4. Confirm `dw-demo.txt` is on your desktop containing "başlıyoruz". Stop anytime
   with `python -m desktop_worker estop` (in another window).
**What Claude needs back:** "worked" or the printed report if a step FAILED.
Full how-to: `dw_test_guide.md`.

---

## MANUAL-1 — Validate real mouse/keyboard/drag on a live desktop
**Status:** [x] DONE — real mouse/keyboard motion confirmed live 2026-06-25 via the
create-file + `do` runs (Notepad opened + typed; desktop right-click menu driven).
**Blocking:** NO (logic is unit-tested via Null backends; this confirms Level 4)
**Tool:** Windows desktop session
**Added by:** BOOTSTRAP-1
**Instructions:**
1. Open Notepad and focus it.
2. From `C:\Desktop-Worker`, run a short script/REPL using the real backend:
   `python -c "from desktop_worker.actions.backends import get_input_backend as g; b=g(); b.type_text('hello'); b.hotkey(['CTRL','A'])"`
3. Confirm "hello" was typed and selected. Try a drag on a window title bar.
**What Claude needs back:** Confirmation it worked (or a description of any
misbehavior — dropped keys, wrong position) so DW-INPUT-HARDEN can target it.

---

## MANUAL-2 — Install the [windows] extra for real screenshots
**Status:** [x] DONE — `observe` wrote a real 1920×1200 PNG live 2026-06-25
(`manual-0001.png`); real active-window detection confirmed.
**Blocking:** NO (placeholder screenshots keep the loop working)
**Tool:** Terminal
**Added by:** BOOTSTRAP-1
**Instructions:**
1. `python -m pip install -e ".[windows]"`
2. `python -m desktop_worker observe`  (should now write a real PNG screenshot).
**What Claude needs back:** Confirm a real `.png` appears under
`artifacts/.../screenshots/` (or paste any error).

---

## MANUAL-7 — Drive a real task with the Claude CLI planner (DW-PLANNER-AI)
**Status:** [ ] Waiting  (the planner→broker→claude path is already verified for a
single step; this is the full multi-step loop on your real desktop)
**Blocking:** NO
**Tool:** Terminal + the logged-in `claude` CLI (already set up) + a visible app
**Added by:** DW-PLANNER-AI
**Instructions:**
1. (Optional but recommended for a first run) keep an app like Notepad focused.
2. Run a short AI-driven loop (it will ask Claude for each step and execute it):
   ```
   python -c "from desktop_worker.app import Session; from desktop_worker.config import Config; from desktop_worker.safety.policy import PermissionPolicy, auto_approve; from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner; from desktop_worker.loop.task_loop import TaskLoop; from desktop_worker.config import Limits; s=Session(Config(session_id='ai',task_id='t'), policy=PermissionPolicy(approval_callback=auto_approve)); p=ClaudeCliPlanner(task='Type the word hello into the focused window then stop', broker=s.broker, cwd=r'C:\Desktop-Worker', audit=s.audit); loop=TaskLoop(task_id='t', planner=p, observer=s.observer, executor=s.executor, audit=s.audit, estop=s.estop, limits=Limits(max_actions_per_task=5)); r=loop.run(); print(r.to_markdown())"
   ```
   NOTE: this AUTO-APPROVES actions for the demo. For real use, swap `auto_approve`
   for a real prompt so you confirm risky steps.
3. Watch: Claude plans each step (e.g. type "hello"), the loop executes + verifies,
   and prints a final report. The audit log under `artifacts/sessions/ai/t/` records
   every planned step + every `claude` call (via the broker).
**What Claude needs back:** The final report + whether the actions made sense, or
any error. Press the emergency stop any time: `python -m desktop_worker estop`.

---

## MANUAL-6 — Install uiautomation + validate real UIA enumeration (DW-PERCEPTION-UIA)
**Status:** [x] DONE — `WindowsUiaBackend` enumerated 13 real controls live 2026-06-25
(buttons / scrollbar / text area) with bounds + `source=uia`.
**Blocking:** NO (mapping + merge logic unit-tested; without the lib it degrades to
zero UIA elements and OCR still works)
**Tool:** Terminal + a real foreground window (e.g. Notepad, Chrome)
**Added by:** DW-PERCEPTION-UIA
**Instructions:**
1. `python -m pip install -e ".[windows]"` (includes `uiautomation`).
2. Open a window (e.g. Notepad), keep it focused, then run:
   ```
   python -c "from desktop_worker.perception import get_uia_backend; b=get_uia_backend(); els=b.detect(); print(type(b).__name__, 'elements:', len(els)); [print(e.type, e.text, e.bounds) for e in els[:15]]"
   ```
3. Confirm the backend is `WindowsUiaBackend`, that controls are enumerated with
   sensible types (button/input/menu…) and bounds. NOTE for Claude: if this returns
   0 with the lib installed, the live `uiautomation` API names may need adjusting
   (Codex flagged `GetForegroundWindow`+`ControlFromHandle`/`WalkControl` as the
   verify points) — report the exact error so DW can fix the real path.
**What Claude needs back:** Backend name + element count + a few sample lines, or any error.

---

## MANUAL-5 — Install Tesseract + validate real OCR (DW-PERCEPTION-OCR)
**Status:** [ ] Waiting
**Blocking:** NO (OCR parsing logic is unit-tested; without Tesseract the system
degrades to zero elements and keeps running)
**Tool:** Terminal + the Tesseract OCR engine
**Added by:** DW-PERCEPTION-OCR
**Instructions:**
1. Install the Tesseract engine (e.g. `winget install UB-Mannheim.TesseractOCR`)
   and the Python extra: `python -m pip install -e ".[ocr,windows]"`.
2. Take a real screenshot then run OCR over it, e.g.:
   ```
   python -c "from desktop_worker.perception import get_ocr_backend; from desktop_worker.observation.backends import get_desktop_backend; from pathlib import Path; b=get_desktop_backend(); p=Path('artifacts/ocr_test.png'); b.capture_screenshot(p); els=get_ocr_backend().detect(p); print('elements:',len(els)); [print(e.text, e.bounds, e.confidence) for e in els[:10]]"
   ```
3. Confirm `get_ocr_backend()` is now the Tesseract backend and that some visible
   on-screen text is detected with plausible bounds + confidence.
**What Claude needs back:** The element count + a few sample lines (or any error).

---

## MANUAL-4 — Validate real UAC elevation (DW-CLI-ELEVATE)
**Status:** [ ] Waiting
**Blocking:** NO (broker logic is fully unit-tested via an injected fake elevator;
this validates the real ShellExecuteEx "runas" path which cannot run in CI)
**Tool:** A genuine **non-admin** PowerShell/cmd (so UAC actually prompts)
**Added by:** DW-CLI-ELEVATE
**Instructions:**
1. From `C:\Desktop-Worker` in a NON-admin shell, run a quick Python snippet that
   drives the broker with a low-risk elevated command, e.g.:
   ```
   python -c "from desktop_worker.app import Session; from desktop_worker.config import Config; from desktop_worker.safety.policy import PermissionPolicy, auto_approve; s=Session(Config(session_id='uac',task_id='t'), policy=PermissionPolicy(approval_callback=auto_approve)); r=s.broker.run('whoami /groups', r'C:\\Desktop-Worker', elevated=True); print('elevated=',r.elevated,'exit=',r.exitCode); print(r.stdoutTail[:400])"
   ```
2. Confirm: (a) a UAC consent prompt appears; (b) after consenting, `elevated=True`
   and the output is captured; (c) if you CANCEL the UAC prompt, it falls back to a
   non-elevated run with `elevated=False` and a "elevation failed" note (not dropped);
   (d) no leftover `dw_elev_*`/`dw_exit_*` files remain in `artifacts/.../cli/`.
**What Claude needs back:** The printed `elevated=`/`exit=` line and whether the UAC
prompt behaved as described (or any error / leftover files).

---

## MANUAL-3 — Make the initial git commit  ✅ DONE
**Status:** [x] Done
**Blocking:** NO
**Tool:** Terminal
**Added by:** BOOTSTRAP-1
**Resolution:** User created GitHub repo and authorized push. Committed `023b107`
and pushed to `origin/main` (https://github.com/alperozel1990/Desktop-Worker.git).
Commit + push are now allowed for this project going forward.

---

## MANUAL-WF-1 — Window switch + drag-and-drop (live)  ☑ (switch part)
**Status:** [x] switch-window DONE live 2026-06-25 — `switch-window "merhaba"` focused
the Notepad (verified active window changed terminal→Notepad). Drag-drop part not yet
exercised live. · **Blocking:** NO · **Added by:** DW-WF-WINDOW
**Tool:** Real Windows desktop with a couple of windows open.
**Instructions:**
1. Open Notepad (or any window). Run `python -m desktop_worker switch-window "Notepad"`.
   Confirm Notepad comes to the front (audited; check `artifacts/.../switch-window/audit.jsonl`).
2. For drag-drop, the `drag_drop` workflow/`DragDropTool` move the mouse; try via a
   short script or the `do`/`ui` agent dragging a desktop icon. Confirm a real drag.
**What Claude needs back:** Whether the window focused + whether a drag actually moved an item.

## MANUAL-WF-2 — Native file picker upload (live)  ☑
**Status:** [x] DONE live 2026-06-25. Initial run exposed a bug (5 "Open" controls →
wrong click); fixed in **DW-WF-PICKER-OPENBTN** (confirm via ENTER). Re-run: `pick-file`
typed the path and self-confirmed with ENTER → `dw-demo.txt` opened, no manual ENTER.
· **Blocking:** NO · **Added by:** DW-WF-FILEPICKER
**Tool:** Any app that opens the standard Open dialog (e.g. a browser upload).
**Instructions:** With an Open dialog visible, run
`python -m desktop_worker pick-file "C:\full\path\to\file.txt"`. Confirm the path is
typed into the File name field and Open is clicked.
**What Claude needs back:** Whether the file was selected / dialog confirmed.

## MANUAL-WF-3 — Download wait + locate (live)  ☑
**Status:** [x] DONE live 2026-06-25 — `wait-download` caught a real Chrome download
(`WhatsApp Image ....jpeg`) in ~/Downloads, ignored `.crdownload` partials, printed the
completed path. (First 90s run timed out cleanly with no download — graceful.) · **Blocking:** NO · **Added by:** DW-WF-DOWNLOAD
**Instructions:** Run `python -m desktop_worker wait-download --timeout 60`, then start
a download in Chrome. Confirm the command prints the completed file's path once the
`.crdownload` finishes.
**What Claude needs back:** The printed path / whether partials were correctly ignored.

## MANUAL-WF-4 — Chrome navigate + form fill (live)  ☑ (navigate)
**Status:** [x] navigate DONE live 2026-06-25. Initial run exposed a focus-race bug
(typed before Chrome was foreground → tab stayed "New Tab"); fixed in
**DW-WF-BROWSE-FOREGROUND**. Re-run: `browse "https://www.google.com"` → active window
became "Google - Google Chrome". Form fill/submit (`--fill`/`--submit`) still untested
live (page-specific UIA names). · **Blocking:** NO · **Added by:** DW-WF-BROWSER
**Instructions:** Run e.g.
`python -m desktop_worker browse "https://www.google.com" --fill "Search=desktop worker" --submit "Google Search"`
(label names depend on the page's accessibility names). Confirm Chrome opens, navigates,
the field fills, and it submits.
**What Claude needs back:** Whether navigation + fill + submit worked (and which UIA
names matched), so we can tune the name candidates.

## MANUAL-ORCH-1 — Full multi-agent orchestration (live)  ☐
**Status:** [ ] To do · **Blocking:** NO · **Added by:** DW-ORCH-COORD
**Instructions:** Plan-only first: `python -m desktop_worker orchestrate "tidy my desktop"`
(real Claude decomposes + auditors review; no side effects). Then, only if comfortable,
`... orchestrate "..." --execute` to let the Implementer drive the desktop per task.
**What Claude needs back:** The printed plan/outcomes table + whether verdicts looked sane.

## MANUAL-UI-1 — Tkinter control window (live)  ☐
**Status:** [ ] To do · **Blocking:** NO · **Added by:** DW-UI-TK
**Instructions:** Run `python -m desktop_worker ui`. The window shows a task box +
Run, a live audit timeline, the latest screenshot, Approve/Deny, and STOP/Pause/Resume.
Type a task (e.g. "open notepad and type hi"), click Run, watch the timeline; trigger a
high-risk action to see the Approve/Deny prompt block the loop until you click; test STOP.
**What Claude needs back:** Whether the window renders, the timeline updates live, the
screenshot shows, approve/deny gates the loop, and STOP halts it.
