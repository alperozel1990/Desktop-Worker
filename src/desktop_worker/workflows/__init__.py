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
from desktop_worker.workflows.file_dialog import (
    FileDialogResult,
    choose_file,
    upload_file,
)
from desktop_worker.workflows.browser import (
    BrowserResult,
    click_control,
    fill_field,
    navigate,
    open_chrome,
    submit_form,
)
from desktop_worker.workflows.downloads import (
    get_downloads_dir,
    is_partial,
    wait_for_download,
)
from desktop_worker.workflows.window import WindowResult, drag_drop, switch_window

__all__ = ["create_desktop_text_file", "CreateDesktopFileResult",
           "switch_window", "drag_drop", "WindowResult",
           "choose_file", "upload_file", "FileDialogResult",
           "wait_for_download", "is_partial", "get_downloads_dir",
           "open_chrome", "navigate", "fill_field", "click_control",
           "submit_form", "BrowserResult"]
