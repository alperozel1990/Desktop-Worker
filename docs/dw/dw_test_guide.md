# Desktop-Worker — Test Guide (for the user)

This is a step-by-step guide to verifying everything built so far. You do **not**
need to know the code. Just open a terminal, copy-paste the commands, and compare
what you see to **"Expected."** If something differs, copy the output back to Claude.

> All commands run from the project folder. Open **PowerShell** and first run:
> ```powershell
> cd C:\Desktop-Worker
> ```

---

## 0. One-time setup (install)

```powershell
python -m pip install -e ".[dev]"
```
**Expected:** ends with `Successfully installed ...`. (You already have Python 3.14.)

For the desktop/perception tests below, also install the optional extras:
```powershell
python -m pip install -e ".[windows,ocr]"
```
**Expected:** installs `mss`, `pywin32`, `uiautomation`, `pytesseract`, `Pillow`.
(OCR also needs the Tesseract engine — see Test E.)

---

## A. Automated tests (no clicking, totally safe) — START HERE

```powershell
python -m pytest
```
**Expected:** the last line is **`109 passed`** (a few seconds). This proves all the
logic — action validation, safety/emergency-stop, audit log, CLI broker, elevation,
perception (OCR+UIA), the loop with retry/recovery, and input planning. ✅

---

## B. App sanity (safe, read-only)

```powershell
python -m desktop_worker status
```
**Expected:** prints version, your session/task, the artifacts path, `process admin:`
True/False, and `backends : {'desktop': 'WindowsDesktopBackend', 'input': 'WindowsInputBackend'}`.

```powershell
python -m desktop_worker observe --no-screenshot
```
**Expected:** a JSON block with your **real** screen size, current **cursor x/y**, and
the **active window** title/process. Move your mouse and run it again — x/y change. ✅

```powershell
python -m desktop_worker --null demo
```
**Expected:** a "Task Report" showing **5 steps, 5 ok, 0 failed, Completed: True**, and
paths to an audit log + report. This runs the full observe→act→verify→log loop safely
(no real mouse/keyboard). ✅

---

## C. Emergency stop (safety)

```powershell
python -m desktop_worker estop
python -m desktop_worker status
python -m desktop_worker clear-stop
```
**Expected:** after `estop`, status shows `estop file ... (present=True)`; after
`clear-stop` it's gone. This is the kill-switch any running task checks. ✅

---

## D. MANUAL-1 — Real mouse & keyboard (needs a visible app)

This actually moves the mouse / types, so watch the screen.

1. Open **Notepad** and click in it so it has focus.
2. Run (it types into whatever is focused — keep Notepad focused):
```powershell
python -c "from desktop_worker.actions.backends import get_input_backend as g; b=g(); b.type_text('hello from desktop-worker'); b.hotkey(['CTRL','A'])"
```
**Expected:** `hello from desktop-worker` appears in Notepad and then gets
**selected** (Ctrl+A). Try a long paste too:
```powershell
python -c "from desktop_worker.actions.backends import get_input_backend as g; b=g(); b.type_text('LONG '*100)"
```
**Expected:** a long line appears almost instantly (it pasted via clipboard, not
key-by-key). **Tell Claude:** did it type correctly? any dropped characters?

---

## E. MANUAL-5 — Real OCR (needs the Tesseract engine)

1. Install the engine:
```powershell
winget install UB-Mannheim.TesseractOCR
```
   (Then close & reopen PowerShell so it's on PATH.)
2. Capture your screen and OCR it:
```powershell
python -c "from desktop_worker.perception import get_ocr_backend; from desktop_worker.observation.backends import get_desktop_backend; from pathlib import Path; b=get_desktop_backend(); p=Path('artifacts/ocr_test.png'); b.capture_screenshot(p); els=get_ocr_backend().detect(p); print('backend:', type(get_ocr_backend()).__name__); print('found', len(els), 'text elements'); [print(repr(e.text), e.bounds, e.confidence) for e in els[:10]]"
```
**Expected:** `backend: TesseractOcrBackend`, then a count and several lines of text
that are actually on your screen, with positions + confidence. **Tell Claude** the
count and a few lines (or any error). If it says `NullOcrBackend`, Tesseract isn't
installed/on PATH yet.

---

## F. MANUAL-6 — Real UI Automation (needs `uiautomation`, installed in step 0)

1. Open a window (e.g. **Notepad** or **Chrome**) and keep it focused.
2. Run:
```powershell
python -c "from desktop_worker.perception import get_uia_backend; b=get_uia_backend(); els=b.detect(); print('backend:', type(b).__name__); print('found', len(els), 'controls'); [print(e.type, repr(e.text), e.bounds) for e in els[:15]]"
```
**Expected:** `backend: WindowsUiaBackend`, then a list of UI controls (buttons,
menus, edit fields…) with types and positions. **Tell Claude** the backend name +
count. If it's `WindowsUiaBackend` but found **0** controls, the live UIA API names
may need a tweak — paste any error and Claude will fix it.

---

## G. MANUAL-4 — Real elevated command (UAC prompt)

This proves the elevated CLI broker. Best from a **normal (non-admin)** PowerShell.

```powershell
python -c "from desktop_worker.app import Session; from desktop_worker.config import Config; from desktop_worker.safety.policy import PermissionPolicy, auto_approve; s=Session(Config(session_id='uac',task_id='t'), policy=PermissionPolicy(approval_callback=auto_approve)); r=s.broker.run('whoami /groups', r'C:\Desktop-Worker', elevated=True); print('elevated=', r.elevated, 'exit=', r.exitCode); print(r.stdoutTail[:300])"
```
**Expected:** a **UAC consent prompt** pops up. After you click **Yes**: `elevated= True`,
`exit= 0`, and some group output. If you click **No/Cancel**: it should fall back to
`elevated= False` and still run (not crash). **Tell Claude** the `elevated=`/`exit=`
line and whether the UAC prompt behaved as described.

---

## H. MANUAL-7 — Real AI planner (Claude drives the loop, no API key)

This uses your **existing `claude` login** (no API key, no extra billing setup) to
let Claude decide each step. It actually controls the desktop, so watch the screen.

1. Sanity-check your login (should already be fine):
```powershell
claude auth status
```
**Expected:** JSON with `"loggedIn": true`.

2. Run a short AI-driven task (auto-approves steps for this demo — keep Notepad
   focused if you want to see it type):
```powershell
python -c "from desktop_worker.app import Session; from desktop_worker.config import Config, Limits; from desktop_worker.safety.policy import PermissionPolicy, auto_approve; from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner; from desktop_worker.loop.task_loop import TaskLoop; s=Session(Config(session_id='ai',task_id='t'), policy=PermissionPolicy(approval_callback=auto_approve)); p=ClaudeCliPlanner(task='Type the word hello into the focused window then stop', broker=s.broker, cwd=r'C:\Desktop-Worker', audit=s.audit); loop=TaskLoop(task_id='t', planner=p, observer=s.observer, executor=s.executor, audit=s.audit, estop=s.estop, limits=Limits(max_actions_per_task=5)); print(loop.run().to_markdown())"
```
**Expected:** Claude plans a step (e.g. type "hello"), the loop executes it, verifies,
and prints a **Task Report**. Every planned step + every Claude call is in the audit
log under `artifacts/sessions/ai/t/`. **Panic button anytime:** open another terminal
and run `python -m desktop_worker estop`.
**Tell Claude:** the final report, and whether the steps made sense.

> ⚠️ This demo AUTO-APPROVES actions. For real/risky tasks you'd swap in a prompt so
> you confirm each risky step — that's a Phase 7 (UI) item.

---

## What to send back to Claude

For each manual test (D, E, F, G) just paste the printed result line(s) or any error.
That lets Claude mark validation **Level 4** (real-world verified) and fix anything
the live environment reveals. Tests A–C need nothing from you — if `109 passed`, the
core is green.

> Full per-test detail also lives in `dw_manual_steps.md`. Live dashboard:
> open `dw_tracker.html` in a browser.
