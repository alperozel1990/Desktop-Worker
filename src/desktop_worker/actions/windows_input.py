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
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}
# Letters A-Z (VK == ASCII uppercase) and digits 0-9 (VK == ASCII digit).
for _c in range(ord("A"), ord("Z") + 1):
    _VK[chr(_c)] = _c
for _d in range(ord("0"), ord("9") + 1):
    _VK[chr(_d)] = _d

# Default: paste text longer than this many chars via the clipboard instead of
# synthesizing each keystroke (faster + far more reliable for long strings).
DEFAULT_PASTE_THRESHOLD = 200


def resolve_vk(key: str) -> int | None:
    """Resolve a key name (case-insensitive) to its virtual-key code, or None."""
    return _VK.get((key or "").upper())


def plan_hotkey(keys: list[str]) -> list[tuple[int, str]]:
    """Plan a key-combination as an ordered (vk, "down"|"up") event list.

    Modifiers/keys are pressed in the given order and released in REVERSE order,
    so a combo like Ctrl+L holds Ctrl down across the L press (requirements §9).
    Raises KeyError if any key name is unknown — callers must not send a
    partially-resolved combo (which could leave a modifier stuck down).
    """
    vks: list[int] = []
    for k in keys:
        vk = resolve_vk(k)
        if vk is None:
            raise KeyError(f"unknown key in hotkey: {k!r}")
        vks.append(vk)
    plan: list[tuple[int, str]] = [(vk, "down") for vk in vks]
    plan += [(vk, "up") for vk in reversed(vks)]
    return plan


def should_paste(text: str, threshold: int = DEFAULT_PASTE_THRESHOLD) -> bool:
    """Whether long text should be entered via clipboard paste rather than typed."""
    return len(text) > threshold


class WindowsInputBackend:
    def __init__(self, *, inter_key_delay_s: float = 0.0,
                 paste_threshold: int = DEFAULT_PASTE_THRESHOLD) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsInputBackend requires Windows")
        import ctypes

        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32
        # Small delay between synthesized keystrokes improves reliability in apps
        # that drop input when it arrives too fast (requirements §9).
        self.inter_key_delay_s = inter_key_delay_s
        self.paste_threshold = paste_threshold
        self._build_sendinput(ctypes)

    def _build_sendinput(self, ctypes) -> None:
        """Set up SendInput structures for true Unicode typing.

        keybd_event's scan-code parameter is only a BYTE, so codepoints > 255
        (e.g. Turkish ş U+015F, ı U+0131) get truncated to garbage. SendInput's
        KEYBDINPUT.wScan is a 16-bit WORD, so the full BMP can be sent with
        KEYEVENTF_UNICODE. Codepoints above U+FFFF are sent as surrogate pairs.
        """
        from ctypes import wintypes

        ULONG_PTR = ctypes.wintypes.WPARAM if hasattr(ctypes.wintypes, "WPARAM") else ctypes.c_void_p

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ULONG_PTR)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class _INPUTunion(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

        self._KEYBDINPUT = KEYBDINPUT
        self._INPUT = INPUT
        self._INPUTunion = _INPUTunion

    def _send_unicode_units(self, units: list[int]) -> None:
        """Send a list of 16-bit code units as Unicode key down+up via SendInput."""
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        INPUT_KEYBOARD = 1
        events = []
        for u in units:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                ki = self._KEYBDINPUT(wVk=0, wScan=u, dwFlags=flags, time=0, dwExtraInfo=0)
                inp = self._INPUT(type=INPUT_KEYBOARD, u=self._INPUTunion(ki=ki))
                events.append(inp)
        n = len(events)
        arr = (self._INPUT * n)(*events)
        self.user32.SendInput(n, arr, self.ctypes.sizeof(self._INPUT))

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
        # Absolute synthetic moves so drag also works for drawing (see _abs_move).
        self._abs_move(x1, y1)
        time.sleep(0.03)
        self.mouse_down("left")
        time.sleep(0.03)
        steps = max(2, int(duration_ms / 12))
        for i in range(1, steps + 1):
            ix = int(x1 + (x2 - x1) * i / steps)
            iy = int(y1 + (y2 - y1) * i / steps)
            self._abs_move(ix, iy)
            time.sleep(duration_ms / 1000.0 / steps)
        time.sleep(0.03)
        self.mouse_up("left")

    def _abs_move(self, x: int, y: int) -> None:
        """Move via a synthetic ABSOLUTE mouse-move event.

        Drawing apps (Paint) track WM_MOUSEMOVE between button-down/up; SetCursorPos
        teleports the cursor without reliably generating those, so freehand strokes
        collapse to a dot. mouse_event(MOVE|ABSOLUTE) emits a real move the app draws.

        NOTE: ABSOLUTE is normalized over the PRIMARY monitor only; for a secondary
        monitor this would need MOUSEEVENTF_VIRTUALDESK + the virtual-screen metrics.
        """
        u = self.user32
        w = max(1, u.GetSystemMetrics(0) - 1)
        h = max(1, u.GetSystemMetrics(1) - 1)
        nx = int(x * 65535 / w)
        ny = int(y * 65535 / h)
        u.mouse_event(0x0001 | 0x8000, nx, ny, 0, 0)  # MOUSEEVENTF_MOVE|ABSOLUTE

    def stroke(self, points: list, duration_ms: int) -> None:
        """Press at the first point, drag smoothly through all points, release.

        Uses absolute synthetic moves (so Paint actually draws) and interpolates
        between consecutive points to produce continuous lines, not dots.
        """
        pts = [(int(p[0]), int(p[1])) for p in points]
        if not pts:
            return
        self._abs_move(*pts[0])
        time.sleep(0.03)
        self.mouse_down("left")
        time.sleep(0.03)
        seg_ms = max(1.0, duration_ms / max(1, len(pts) - 1))
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            steps = max(2, int(seg_ms / 8))
            for i in range(1, steps + 1):
                self._abs_move(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
                time.sleep(seg_ms / 1000.0 / steps)
        time.sleep(0.03)
        self.mouse_up("left")

    # --- keyboard ------------------------------------------------------
    def type_text(self, text: str) -> None:
        # For long text, paste via clipboard (Ctrl+V) — much faster and far more
        # reliable than synthesizing thousands of keystrokes (requirements §9).
        if should_paste(text, self.paste_threshold):
            self.clipboard_set(text)
            self.hotkey(["CTRL", "V"])
            return
        for ch in text:
            # KEYEVENTF_UNICODE lets us emit any character regardless of layout.
            self._unicode_key(ord(ch))
            if self.inter_key_delay_s:
                time.sleep(self.inter_key_delay_s)

    def _unicode_key(self, codepoint: int) -> None:
        # SendInput with 16-bit wScan handles the full BMP (incl. Turkish ş/ı);
        # astral codepoints (> U+FFFF) are sent as a UTF-16 surrogate pair.
        if codepoint > 0xFFFF:
            cp = codepoint - 0x10000
            hi = 0xD800 + (cp >> 10)
            lo = 0xDC00 + (cp & 0x3FF)
            self._send_unicode_units([hi, lo])
        else:
            self._send_unicode_units([codepoint])

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
        # plan_hotkey raises on an unknown key BEFORE any event is sent, so we
        # never leave a modifier stuck down from a partially-resolved combo.
        try:
            plan = plan_hotkey(keys)
        except KeyError:
            return
        KEYEVENTF_KEYUP = 0x0002
        for vk, action in plan:
            flags = KEYEVENTF_KEYUP if action == "up" else 0
            self.user32.keybd_event(vk, 0, flags, 0)

    # --- clipboard -----------------------------------------------------
    def _clipboard_prototypes(self):
        """Declare 64-bit-safe argtypes/restypes for the Win32 clipboard calls.

        Without this, ctypes defaults every HANDLE/pointer return to a 32-bit
        ``c_int`` and truncates real 64-bit handles, which raises
        ``OverflowError: int too long to convert`` (clipboard was fully broken on
        64-bit Python). Setting the prototypes is idempotent and scoped to these
        clipboard functions only.
        """
        ctypes = self.ctypes
        c_void_p, c_size_t = ctypes.c_void_p, ctypes.c_size_t
        c_uint, c_int = ctypes.c_uint, ctypes.c_int
        user32 = self.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [c_void_p]; user32.OpenClipboard.restype = c_int
        user32.SetClipboardData.argtypes = [c_uint, c_void_p]
        user32.SetClipboardData.restype = c_void_p
        user32.GetClipboardData.argtypes = [c_uint]; user32.GetClipboardData.restype = c_void_p
        kernel32.GlobalAlloc.argtypes = [c_uint, c_size_t]; kernel32.GlobalAlloc.restype = c_void_p
        kernel32.GlobalLock.argtypes = [c_void_p]; kernel32.GlobalLock.restype = c_void_p
        kernel32.GlobalUnlock.argtypes = [c_void_p]; kernel32.GlobalUnlock.restype = c_int
        kernel32.GlobalFree.argtypes = [c_void_p]; kernel32.GlobalFree.restype = c_void_p
        return kernel32

    def clipboard_set(self, text: str) -> None:
        ctypes = self.ctypes
        user32 = self.user32
        kernel32 = self._clipboard_prototypes()
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        if not user32.OpenClipboard(None):
            return
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                return
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                kernel32.GlobalFree(h)
                return
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h)
            # On success the system owns the memory; only free if it refused it.
            if not user32.SetClipboardData(CF_UNICODETEXT, h):
                kernel32.GlobalFree(h)
        finally:
            user32.CloseClipboard()

    def clipboard_get(self) -> str:
        ctypes = self.ctypes
        user32 = self.user32
        kernel32 = self._clipboard_prototypes()
        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(None):
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
