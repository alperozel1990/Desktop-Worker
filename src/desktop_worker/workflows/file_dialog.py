"""Native file-picker (Open/Save dialog) handling workflow (requirements Phase 5).

When an app pops the standard Windows file dialog (e.g. for an upload or a
"Save as"), this workflow types a path into the "File name" field and clicks the
confirm button ("Open"/"Save"). Targets are located via UI Automation; every
input is a structured action through the audited, emergency-stop-gated executor.

The dialog is assumed already open (the caller/app triggers it); a file picker
has no generic on-disk post-condition, so success means the input sequence ran —
the app-specific result (file uploaded/saved) is the caller's to verify.

Locale-aware name candidates cover English + Turkish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from desktop_worker.schema.actions import parse_action

# "File name" edit + confirm button name candidates (en + tr).
FILE_NAME_NAMES = ("File name:", "File name", "Dosya adı:", "Dosya adı")
OPEN_BUTTON_NAMES = ("Open", "Aç", "&Open", "&Aç")
SAVE_BUTTON_NAMES = ("Save", "Kaydet", "&Save", "&Kaydet")


@runtime_checkable
class FileDialogUi(Protocol):
    """Locate the standard file-dialog controls."""

    def file_name_edit_center(self, names: tuple[str, ...] = FILE_NAME_NAMES,
                              timeout: float = 2.0) -> Optional[tuple[int, int]]: ...
    def button_center(self, names: tuple[str, ...],
                      timeout: float = 2.0) -> Optional[tuple[int, int]]: ...


class NullFileDialogUi:
    """No-op locator for tests/headless: finds nothing."""

    def file_name_edit_center(self, names=FILE_NAME_NAMES, timeout: float = 2.0):
        return None

    def button_center(self, names, timeout: float = 2.0):
        return None


class WindowsFileDialogUi:
    """Real locator via uiautomation. Construct only on Windows."""

    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsFileDialogUi requires Windows")
        import uiautomation  # noqa: F401  (probe so the factory can fall back)

        self._auto = uiautomation

    def _center(self, ctrl) -> Optional[tuple[int, int]]:
        try:
            r = ctrl.BoundingRectangle
            if r is None:
                return None
            return (r.left + r.right) // 2, (r.top + r.bottom) // 2
        except Exception:
            return None

    def file_name_edit_center(self, names=FILE_NAME_NAMES, timeout: float = 2.0):
        for nm in names:
            it = self._auto.EditControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        # Fall back to the first/only edit in the foreground dialog.
        try:
            it = self._auto.EditControl()
            if it.Exists(timeout):
                return self._center(it)
        except Exception:
            pass
        return None

    def button_center(self, names, timeout: float = 2.0):
        for nm in names:
            it = self._auto.ButtonControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        return None


def get_file_dialog_ui(prefer_real: bool = True) -> FileDialogUi:
    """Return the best available file-dialog locator, falling back to Null."""
    if prefer_real:
        try:
            return WindowsFileDialogUi()
        except Exception:
            pass
    return NullFileDialogUi()


@dataclass
class FileDialogResult:
    success: bool
    path: str
    confirm: str
    steps: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "path": self.path, "confirm": self.confirm,
                "steps": list(self.steps), "error": self.error}

    def to_markdown(self) -> str:
        head = f"{'OK' if self.success else 'FAILED'}: file dialog ({self.confirm})"
        body = "".join(f"\n  - {s}" for s in self.steps)
        tail = f"\n  error: {self.error}" if self.error else ""
        return f"{head} path={self.path!r}{body}{tail}"


def choose_file(path: str, *, executor, ui: FileDialogUi, confirm: str = "open",
                sleep=None) -> FileDialogResult:
    """Type ``path`` into the open file dialog and click Open/Save.

    ``confirm`` is "open" (file picker / upload) or "save" (save-as).
    """
    import time

    nap = sleep or time.sleep
    confirm = confirm.lower().strip()
    steps: list[str] = []

    def fail(msg: str) -> FileDialogResult:
        steps.append(f"FAIL: {msg}")
        return FileDialogResult(False, path, confirm, steps, error=msg)

    def do(action_dict: dict, label: str) -> bool:
        res = executor.execute(parse_action(action_dict))
        ok = getattr(res, "success", False)
        steps.append(f"{'ok' if ok else 'FAIL'}: {label}")
        return ok

    path = str(path or "").strip()
    if not path:
        return fail("empty path")

    edit = ui.file_name_edit_center()
    if edit is None:
        return fail("could not find the File name field (is a file dialog open?)")
    ex, ey = edit

    if not do({"type": "mouse.click", "x": ex, "y": ey}, "click File name field"):
        return fail("could not click the File name field")
    nap(0.1)
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "A"]}, "select existing text")
    if not do({"type": "keyboard.type", "text": path}, "type path"):
        return fail("could not type the path")
    nap(0.1)

    # Confirm with ENTER. The path now sits in the *focused* File name field, so
    # ENTER activates the dialog's default button (Open/Save). This is deliberately
    # immune to the Win11 file dialog exposing several controls all named "Open"
    # (the primary button plus split-button arrows next to the File-name / Files-of-
    # type / Encoding dropdowns): a name-based button click landed on the wrong one
    # and left the dialog open (live finding MANUAL-WF-2 → DW-WF-PICKER-OPENBTN).
    ok = do({"type": "keyboard.press", "key": "ENTER"}, f"confirm ({confirm}) with ENTER")

    if not ok:
        return fail("could not confirm the dialog")
    return FileDialogResult(True, path, confirm, steps)


def upload_file(path: str, *, executor, ui: FileDialogUi, sleep=None) -> FileDialogResult:
    """Choose ``path`` in an already-open upload (Open) file dialog."""
    return choose_file(path, executor=executor, ui=ui, confirm="open", sleep=sleep)
