"""Workflow: create a text file on the desktop, type content, save it.

This is a *deterministic* desktop workflow (requirements Phase 5). Every input is
a validated structured action run through the executor (so each is audited and
gated by the emergency stop); on-screen targets are located via UI Automation.
The result is verified on disk, so the workflow never claims success unless the
file actually contains the requested content.

Visible sequence the user watches:
  show desktop -> right-click empty area -> New -> Text Document -> name it
  -> double-click to open -> type content -> Ctrl+S -> (verify on disk)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from desktop_worker.schema.actions import parse_action
from desktop_worker.workflows.desktop_ui import (
    NEW_MENU_NAMES,
    SHOW_MORE_NAMES,
    TEXT_DOCUMENT_NAMES,
)


@dataclass
class CreateDesktopFileResult:
    success: bool
    path: str
    content: str
    steps: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success, "path": self.path, "content": self.content,
            "steps": self.steps, "error": self.error,
        }

    def to_markdown(self) -> str:
        head = "OK" if self.success else "FAILED"
        lines = [f"# Create desktop file - {head}", "",
                 f"- Path: {self.path}", f"- Content: {self.content!r}"]
        if self.error:
            lines.append(f"- Error: {self.error}")
        lines += ["", "## Steps"]
        lines += [f"{i}. {s}" for i, s in enumerate(self.steps, 1)]
        return "\n".join(lines) + "\n"


def desktop_file_path(desktop_dir: str, filename: str) -> str:
    """Build the .txt path for a desktop file (adds .txt if missing)."""
    name = filename if filename.lower().endswith(".txt") else filename + ".txt"
    return str(Path(desktop_dir) / name)


def create_desktop_text_file(
    content: str,
    *,
    executor: Any,
    ui: Any,
    desktop_dir: str,
    screen_size: tuple[int, int],
    filename: str = "dw-demo",
    sleep: Callable[[float], None] = time.sleep,
    scale: float = 1.0,
) -> CreateDesktopFileResult:
    """Create ``<desktop>/<filename>.txt`` containing ``content``, visibly.

    Returns a result whose ``success`` is True only if the file on disk actually
    contains ``content`` (verified). Fails safe with a clear error at the first
    step that cannot complete.
    """
    path = desktop_file_path(desktop_dir, filename)
    steps: list[str] = []

    def fail(msg: str) -> CreateDesktopFileResult:
        steps.append(f"FAILED: {msg}")
        return CreateDesktopFileResult(False, path, content, steps, msg)

    def do(action_dict: dict, label: str) -> bool:
        res = executor.execute(parse_action(action_dict))
        ok = getattr(res, "success", False)
        steps.append(f"{'ok' if ok else 'FAIL'}: {label}")
        return ok

    def nap(seconds: float) -> None:
        sleep(seconds * scale)

    w, h = screen_size
    cx, cy = w // 2, h // 2

    # 1) reveal the desktop
    if ui.show_desktop():
        steps.append("ok: show desktop")
    else:
        steps.append("warn: show desktop not available")
    nap(1.2)

    # 2) right-click an empty desktop area
    if not do({"type": "mouse.rightClick", "x": cx, "y": cy}, "right-click desktop"):
        return fail("right-click failed")
    nap(0.9)

    # 3) New (open submenu). Fall back to "Show more options" (Win11 compact menu).
    new = ui.menu_item_center(NEW_MENU_NAMES)
    if new is None:
        more = ui.menu_item_center(SHOW_MORE_NAMES, timeout=1.0)
        if more is not None:
            do({"type": "mouse.click", "x": more[0], "y": more[1]}, "Show more options")
            nap(0.6)
            new = ui.menu_item_center(NEW_MENU_NAMES)
    if new is None:
        return fail("could not find 'New' in the context menu")
    if not do({"type": "mouse.click", "x": new[0], "y": new[1]}, "click New"):
        return fail("click New failed")
    nap(0.6)

    # 4) Text Document
    td = ui.menu_item_center(TEXT_DOCUMENT_NAMES)
    if td is None:
        return fail("could not find 'Text Document' submenu item")
    if not do({"type": "mouse.click", "x": td[0], "y": td[1]}, "click Text Document"):
        return fail("click Text Document failed")
    nap(1.3)

    # 5) name the new file (it appears in rename mode) and confirm
    do({"type": "keyboard.type", "text": filename}, f"type name {filename!r}")
    nap(0.4)
    do({"type": "keyboard.press", "key": "ENTER"}, "confirm name")
    nap(1.3)

    # 6) open it by double-clicking the desktop icon
    icon = ui.desktop_item_center((filename, filename + ".txt"))
    if icon is None:
        return fail("could not locate the new file icon on the desktop")
    if not do({"type": "mouse.doubleClick", "x": icon[0], "y": icon[1]}, "double-click file"):
        return fail("double-click failed")

    # 7) wait for the editor to be ready (title contains the filename)
    ready = False
    for _ in range(20):
        nap(0.5)
        if filename.lower() in ui.active_window_title().lower():
            ready = True
            break
    steps.append(f"{'ok' if ready else 'warn'}: editor ready ({ui.active_window_title()!r})")
    nap(0.8)

    # 8) type the content and save
    if not do({"type": "keyboard.type", "text": content}, "type content"):
        return fail("typing content failed")
    nap(0.6)
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "S"]}, "save (Ctrl+S)")
    nap(1.6)

    # 9) verify on disk (retry once if the content didn't land)
    if _verify(path, content):
        steps.append("ok: verified content on disk")
        return CreateDesktopFileResult(True, path, content, steps)

    steps.append("warn: content not verified, retrying type+save")
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "A"]}, "select all")
    nap(0.2)
    do({"type": "keyboard.type", "text": content}, "re-type content")
    nap(0.4)
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "S"]}, "save again")
    nap(1.6)
    if _verify(path, content):
        steps.append("ok: verified content on disk (after retry)")
        return CreateDesktopFileResult(True, path, content, steps)
    return fail(f"file did not contain expected content after save: {path}")


def _verify(path: str, content: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        return p.read_text(encoding="utf-8").strip() == content.strip()
    except OSError:
        return False
