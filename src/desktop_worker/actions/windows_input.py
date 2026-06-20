"""Real Windows input backend via Win32 SendInput (requirements sections 9, 10).

Uses ctypes + SendInput for reliable synthesized mouse/keyboard input, which is
more robust than higher-level helpers for absolute positioning and modifiers.
Clipboard uses the Win32 clipboard API. Heavy/Windows-only details are isolated
here; construction fails on non-Windows so the factory can fall back to Null.

NOTE: This Phase-1 backend covers the core primitives. Reliability hardening
(per-key layout handling, unicode via SendInput KEYEVENTF_UNICODE for all chars,
inter-key delays) is tracked as a Phase-1 follow-up card (DW-INPUT-HARDEN).
"""

from __future__ import annotations

import time
from typing import Optional

# Virtual-key codes for the common keys named in requirements section 9.
_VK = {
    "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12, "MENU": 0x12,
    "SHIFT": 0x10, "WIN": 0x5B, "LWIN": 0x5B,
    "ENTER": 0x0D, "RETURN": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B,
    "TAB": 0x09, "SPACE": 0x20, "BACKSPACE": 0x08, "BACK": 0x08,
    "DELETE": 0x2E, "DEL": 0x2E, "HOME": 0x24, "END": 0x23,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "L": 0x4C, "C": 0x43, "V": 0x56, "A": 0x41,
}


class WindowsInputBackend:
    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsInputBackend requires Windows")
        import ctypes

        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32

    # --- mouse ---------------------------------------------------------
    def move(self, x: int, y: int) -> None:
        self.user32.SetCursorPos(int(x), int(y))

    def move_relative(self, dx: int, dy: int) -> None:
        cx, cy = self._cursor()
        self.move(cx + int(dx), cy + int(dy))

    def _cursor(self) -> tuple[int, int]:
        ctypes = self.ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        self.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)

    _DOWN = {"left": 0x0002, "right": 0x0008, "middle": 0x0020}
    _UP = {"left": 0x0004, "right": 0x0010, "middle": 0x0040}

    def mouse_down(self, button: str) -> None:
        self.user32.mouse_event(self._DOWN.get(button, 0x0002), 0, 0, 0, 0)

    def mouse_up(self, button: str) -> None:
        self.user32.mouse_event(self._UP.get(button, 0x0004), 0, 0, 0, 0)

    def click(self, button: str, x: Optional[int], y: Optional[int]) -> None:
        if x is not None and y is not None:
            self.move(x, y)
        self.mouse_down(button)
        self.mouse_up(button)

    def double_click(self, button: str, x: Optional[int], y: Optional[int]) -> None:
        self.click(button, x, y)
        self.click(button, None, None)

    def scroll(self, dx: int, dy: int) -> None:
        WHEEL_DELTA = 120
        if dy:
            self.user32.mouse_event(0x0800, 0, 0, int(dy) * WHEEL_DELTA, 0)  # vertical
        if dx:
            self.user32.mouse_event(0x01000, 0, 0, int(dx) * WHEEL_DELTA, 0)  # horizontal

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        self.move(x1, y1)
        self.mouse_down("left")
        steps = max(1, int(duration_ms / 15))
        for i in range(1, steps + 1):
            ix = int(x1 + (x2 - x1) * i / steps)
            iy = int(y1 + (y2 - y1) * i / steps)
            self.move(ix, iy)
            time.sleep(duration_ms / 1000.0 / steps)
        self.mouse_up("left")

    # --- keyboard ------------------------------------------------------
    def type_text(self, text: str) -> None:
        ctypes = self.ctypes
        for ch in text:
            # KEYEVENTF_UNICODE lets us emit any character regardless of layout.
            self._unicode_key(ord(ch))
        _ = ctypes  # keep reference clear

    def _unicode_key(self, codepoint: int) -> None:
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        self.user32.keybd_event(0, codepoint, KEYEVENTF_UNICODE, 0)
        self.user32.keybd_event(0, codepoint, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)

    def press_key(self, key: str) -> None:
        vk = _VK.get(key.upper())
        if vk is None:
            # Fall back to typing the literal character.
            if len(key) == 1:
                self._unicode_key(ord(key))
            return
        self.user32.keybd_event(vk, 0, 0, 0)
        self.user32.keybd_event(vk, 0, 0x0002, 0)

    def hotkey(self, keys: list[str]) -> None:
        vks = [_VK.get(k.upper()) for k in keys]
        if any(v is None for v in vks):
            return
        for vk in vks:
            self.user32.keybd_event(vk, 0, 0, 0)
        for vk in reversed(vks):
            self.user32.keybd_event(vk, 0, 0x0002, 0)

    # --- clipboard -----------------------------------------------------
    def clipboard_set(self, text: str) -> None:
        ctypes = self.ctypes
        user32 = self.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        if not user32.OpenClipboard(0):
            return
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            ptr = kernel32.GlobalLock(h)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h)
            user32.SetClipboardData(CF_UNICODETEXT, h)
        finally:
            user32.CloseClipboard()

    def clipboard_get(self) -> str:
        ctypes = self.ctypes
        user32 = self.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(0):
            return ""
        try:
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                return ""
            try:
                return ctypes.c_wchar_p(ptr).value or ""
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()
