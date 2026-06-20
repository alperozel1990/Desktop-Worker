"""Real Windows desktop observation backend (requirements section 6).

Heavy dependencies (mss, pywin32) are imported lazily inside methods so that
importing this module never fails on a machine that lacks them; the factory in
``backends.get_desktop_backend`` catches construction errors and falls back to
the Null backend.

This is Phase-1 scope: single-monitor full-screen capture, cursor position,
active-window title/process/bounds, and a visible-window list. Multi-monitor and
per-window capture are later roadmap items.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from desktop_worker.schema.observations import ActiveWindow, Cursor, Screen


class WindowsDesktopBackend:
    """Windows implementation. Construct only on Windows with deps installed."""

    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsDesktopBackend requires Windows")
        # Probe imports eagerly so the factory can fall back if missing.
        import ctypes  # noqa: F401

        self._ctypes = ctypes

    # --- screen --------------------------------------------------------
    def screen(self) -> Screen:
        user32 = self._ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        return Screen(width=int(width), height=int(height), scaleFactor=1.0)

    # --- cursor --------------------------------------------------------
    def cursor(self) -> Cursor:
        class POINT(self._ctypes.Structure):
            _fields_ = [("x", self._ctypes.c_long), ("y", self._ctypes.c_long)]

        pt = POINT()
        self._ctypes.windll.user32.GetCursorPos(self._ctypes.byref(pt))
        return Cursor(x=int(pt.x), y=int(pt.y))

    # --- windows -------------------------------------------------------
    def active_window(self) -> Optional[ActiveWindow]:
        ctypes = self._ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        title = self._window_title(hwnd)
        process = self._window_process(hwnd)
        bounds = self._window_bounds(hwnd)
        return ActiveWindow(title=title, process=process, bounds=bounds)

    def visible_windows(self) -> tuple[str, ...]:
        ctypes = self._ctypes
        user32 = ctypes.windll.user32
        titles: list[str] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )

        def _cb(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                t = self._window_title(hwnd)
                if t:
                    titles.append(t)
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return tuple(titles)

    def capture_screenshot(self, dest: Path) -> Optional[str]:
        try:
            import mss  # type: ignore
            import mss.tools  # type: ignore
        except Exception:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor (single-monitor MVP)
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=str(dest))
        return str(dest)

    # --- helpers -------------------------------------------------------
    def _window_title(self, hwnd) -> str:
        ctypes = self._ctypes
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _window_process(self, hwnd) -> str:
        ctypes = self._ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(handle, None, buf, 260)
            return buf.value
        finally:
            kernel32.CloseHandle(handle)

    def _window_bounds(self, hwnd) -> tuple[int, int, int, int]:
        ctypes = self._ctypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
