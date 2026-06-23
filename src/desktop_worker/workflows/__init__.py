"""Desktop & browser workflows (requirements Phase 5).

High-level, reliable, *visible* desktop tasks composed from structured actions
(executed through the audited, emergency-stop-gated executor) plus UI Automation
to locate on-screen targets. The first workflow creates a text file on the
desktop, opens it, types content, and saves it.
"""

from desktop_worker.workflows.desktop_file import (
    CreateDesktopFileResult,
    create_desktop_text_file,
)
from desktop_worker.workflows.window import WindowResult, drag_drop, switch_window

__all__ = ["create_desktop_text_file", "CreateDesktopFileResult",
           "switch_window", "drag_drop", "WindowResult"]
