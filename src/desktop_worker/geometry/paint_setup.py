"""Canvas hygiene: guarantee a clean, ready-to-draw Paint before any ink.

This is the fix for the "red scribbles" failure: without it, the AI could draw
over stale content, on the wrong tool (Select), or in the wrong colour. Before
drawing we deterministically: focus + maximize Paint, clear the canvas
(Ctrl+A / Delete / Escape), select a drawing tool (Pencil/Brush), and pick a
known colour (Black). One primitive == one stroke + a clean canvas == no chaos.

The OS/UIA work lives behind a small ``PaintUi`` protocol (Null + Windows
implementations, ``uiautomation``/ctypes imported lazily). The orchestration
(``prepare_paint``) routes all clicks/keys through the injected input backend, so
it is fully unit-testable with the Null backend + a fake PaintUi.
"""

from __future__ import annotations

from typing import Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class PaintUi(Protocol):
    def focus(self) -> bool: ...
    def tool_center(self, name: str) -> Optional[Tuple[int, int]]: ...
    def color_center(self, name: str) -> Optional[Tuple[int, int]]: ...


class NullPaintUi:
    """No-op UI (tests / non-Windows). Records nothing, finds nothing."""

    def focus(self) -> bool:
        return False

    def tool_center(self, name: str) -> Optional[Tuple[int, int]]:
        return None

    def color_center(self, name: str) -> Optional[Tuple[int, int]]:
        return None


def prepare_paint(input_backend, paint_ui: PaintUi, *, clear: bool = True,
                  tool: str = "Pencil", color: Optional[str] = "Black") -> dict:
    """Make Paint ready to draw cleanly. Returns what actually happened.

    All keystrokes/clicks go through ``input_backend`` (audited/estop-gated when it
    is the real one). Each step is best-effort and reported in the result so the
    caller/AI knows the canvas state.
    """
    focused = paint_ui.focus()

    cleared = False
    if clear:
        input_backend.hotkey(["CTRL", "A"])
        input_backend.press_key("DELETE")
        input_backend.press_key("ESCAPE")
        cleared = True

    # Ctrl+A leaves the SELECT tool active — pick a drawing tool or strokes become
    # selections, not ink. (This is the bug observed live.)
    tool_ok = False
    if tool:
        xy = paint_ui.tool_center(tool)
        if xy is not None:
            input_backend.click("left", xy[0], xy[1])
            tool_ok = True

    color_ok = False
    if color:
        xy = paint_ui.color_center(color)
        if xy is not None:
            input_backend.click("left", xy[0], xy[1])
            color_ok = True

    return {"focused": focused, "cleared": cleared,
            "tool": tool if tool_ok else None, "color": color if color_ok else None}


# --- Windows implementation (lazy ctypes + uiautomation) -----------------

class WindowsPaintUi:
    """Real Paint UI control via Win32 + UI Automation. Construct only on Windows."""

    def __init__(self, title_contains: str = "Paint") -> None:
        import ctypes  # noqa: F401  (probe so the factory can fall back)

        self._ctypes = ctypes
        self._title = title_contains

    def _hwnd(self):
        ctypes = self._ctypes
        u = ctypes.windll.user32
        found = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _l):
            if u.IsWindowVisible(h):
                n = u.GetWindowTextLengthW(h)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(h, b, n + 1)
                    if self._title.lower() in b.value.lower():
                        found.append(h)
            return True

        u.EnumWindows(EnumProc(cb), 0)
        return found[0] if found else None

    def focus(self) -> bool:
        h = self._hwnd()
        if not h:
            return False
        u = self._ctypes.windll.user32
        try:
            u.ShowWindow(h, 3)             # SW_MAXIMIZE
            u.SetForegroundWindow(h)
            return True
        except Exception:
            return False

    def _find_center(self, name: str, types: tuple) -> Optional[Tuple[int, int]]:
        try:
            import uiautomation as auto
        except Exception:
            return None
        h = self._hwnd()
        if not h:
            return None
        try:
            root = auto.ControlFromHandle(h)
            for c, _ in auto.WalkControl(root, includeTop=True, maxDepth=16):
                try:
                    if (c.Name or "") == name and any(t in (c.ControlTypeName or "")
                                                      for t in types):
                        r = c.BoundingRectangle
                        if r.width() > 0 and r.height() > 0:
                            return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def tool_center(self, name: str) -> Optional[Tuple[int, int]]:
        return self._find_center(name, ("Button", "RadioButton"))

    def color_center(self, name: str) -> Optional[Tuple[int, int]]:
        return self._find_center(name, ("Button", "RadioButton", "ListItem"))


def get_paint_ui(prefer_real: bool = True) -> PaintUi:
    """Return the best available Paint UI controller, falling back to Null."""
    if prefer_real:
        try:
            return WindowsPaintUi()
        except Exception:
            pass
    return NullPaintUi()
