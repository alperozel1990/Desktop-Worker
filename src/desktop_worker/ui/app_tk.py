"""Tkinter control window (requirements Phase 7 UI).

A thin view over :class:`UiController`: task entry + Run, a live audit timeline,
a screenshot preview, Approve/Deny for pending approvals, and ESTOP / Pause /
Resume. The loop/broker run on a worker thread; the broker's approval callback
blocks on the controller's ApprovalQueue and is released by the Approve/Deny
buttons. All logic lives in the controller — this file only renders and forwards
clicks. ``tkinter`` is imported lazily so importing this module never needs a
display (the GUI is validated manually: MANUAL-UI-1).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

# run_task(task_text) -> None : drives one task (provided by the CLI wiring).
RunTask = Callable[[str], None]


def run_control_window(controller, *, run_task: Optional[RunTask] = None,
                       title: str = "Desktop-Worker — Control", poll_ms: int = 500) -> None:
    """Open the control window and block on the Tk main loop."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(title)
    root.geometry("900x600")

    # --- task entry + run -------------------------------------------
    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Task:").pack(side="left")
    task_var = tk.StringVar()
    entry = ttk.Entry(top, textvariable=task_var)
    entry.pack(side="left", fill="x", expand=True, padx=6)

    def on_run() -> None:
        text = task_var.get().strip()
        if not text:
            return
        controller.submit_task(text)
        if run_task is not None:
            threading.Thread(target=lambda: run_task(text), daemon=True).start()

    ttk.Button(top, text="Run", command=on_run).pack(side="left")

    # --- safety controls --------------------------------------------
    ctl = ttk.Frame(root, padding=(8, 0))
    ctl.pack(fill="x")
    ttk.Button(ctl, text="STOP", command=lambda: controller.estop("UI stop")).pack(side="left")
    ttk.Button(ctl, text="Pause", command=controller.pause).pack(side="left", padx=4)
    ttk.Button(ctl, text="Resume", command=controller.resume).pack(side="left")
    ttk.Button(ctl, text="Clear Stop", command=controller.clear_stop).pack(side="left", padx=4)
    status_var = tk.StringVar(value="ready")
    ttk.Label(ctl, textvariable=status_var).pack(side="right")

    # --- approval bar -----------------------------------------------
    appr = ttk.Frame(root, padding=(8, 4))
    appr.pack(fill="x")
    approval_var = tk.StringVar(value="No pending approval.")
    ttk.Label(appr, textvariable=approval_var, foreground="#a40").pack(side="left")
    approve_btn = ttk.Button(appr, text="Approve",
                             command=lambda: controller.resolve_approval(True))
    deny_btn = ttk.Button(appr, text="Deny",
                          command=lambda: controller.resolve_approval(False))
    approve_btn.pack(side="right")
    deny_btn.pack(side="right", padx=4)

    # --- timeline + screenshot --------------------------------------
    body = ttk.Frame(root, padding=8)
    body.pack(fill="both", expand=True)
    timeline = tk.Listbox(body)
    timeline.pack(side="left", fill="both", expand=True)
    shot_label = ttk.Label(body, text="(screenshot)", anchor="center")
    shot_label.pack(side="right", fill="both", expand=True, padx=(8, 0))
    shot_state: dict[str, object] = {"path": None, "image": None}

    def refresh() -> None:
        # timeline
        lines = controller.timeline_lines()
        if timeline.size() != len(lines):
            timeline.delete(0, tk.END)
            for ln in lines:
                timeline.insert(tk.END, ln)
            timeline.see(tk.END)
        # approval state
        pending = controller.pending_approval()
        if pending is not None:
            approval_var.set(f"APPROVAL NEEDED: {getattr(pending, 'summary', pending)}")
            approve_btn.state(["!disabled"])
            deny_btn.state(["!disabled"])
        else:
            approval_var.set("No pending approval.")
            approve_btn.state(["disabled"])
            deny_btn.state(["disabled"])
        # status
        if controller.is_stopped():
            status_var.set("STOPPED")
        elif controller.is_paused():
            status_var.set("PAUSED")
        else:
            status_var.set("running")
        # screenshot preview (best-effort; Tk 8.6 reads PNG natively)
        shots = controller.screenshots()
        if shots and shots[-1] != shot_state["path"]:
            try:
                img = tk.PhotoImage(file=shots[-1])
                shot_state["image"] = img  # keep a ref so it isn't GC'd
                shot_state["path"] = shots[-1]
                shot_label.configure(image=img, text="")
            except Exception:
                shot_label.configure(text=shots[-1])
        root.after(poll_ms, refresh)

    refresh()
    root.mainloop()
