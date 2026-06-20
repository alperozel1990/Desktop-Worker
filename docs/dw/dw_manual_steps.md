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

## MANUAL-3 — (Optional) Make the initial git commit
**Status:** [ ] Waiting
**Blocking:** NO
**Tool:** Terminal
**Added by:** BOOTSTRAP-1
**Instructions:**
1. Review staged files: `git status`
2. If satisfied: `git commit -m "Bootstrap Desktop-Worker Phase 1 foundation"`
**What Claude needs back:** Nothing — or tell Claude to commit and it will (commit
requires your explicit go-ahead per project policy).
