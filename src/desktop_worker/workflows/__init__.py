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

__all__ = ["create_desktop_text_file", "CreateDesktopFileResult"]
