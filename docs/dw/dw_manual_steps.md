# dw_manual_steps.md — Manual step queue

Actions Claude cannot fully perform/validate itself.

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
