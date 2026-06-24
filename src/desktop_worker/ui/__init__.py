"""Desktop-Worker control UI (requirements Phase 7).

A thin Tkinter window (``app_tk.py``) over a pure, dependency-free controller
(``controller.py``). All logic — building the audit timeline, listing artifacts,
emergency stop / pause, and the blocking approval handshake — lives in the
controller so it is fully unit-testable without a display; the Tk layer only
renders and forwards button clicks.
"""

from desktop_worker.ui.controller import ApprovalQueue, UiController, summarize_event

__all__ = ["UiController", "ApprovalQueue", "summarize_event"]
