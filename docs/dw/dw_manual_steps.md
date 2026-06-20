# dw_manual_steps.md — Manual step queue

Actions Claude cannot fully perform/validate itself.

---

## MANUAL-9 — ⭐⭐ Run the GENUINE live-AI demo (the real AI control)
**Status:** [ ] Waiting  (Claude verified end-to-end: the AI opened Notepad via the
Run dialog and typed text, deciding each step itself)
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
**Status:** [ ] Waiting  (Claude already verified it end-to-end on disk; this is
your watch-it-happen run)
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
**Status:** [ ] Waiting
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
**Status:** [ ] Waiting
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
**Status:** [ ] Waiting
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
