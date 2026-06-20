"""Windows desktop UI locator (Phase 5 helper).

Locates on-screen targets (right-click menu items, desktop icons) via Windows UI
Automation so the workflow can click them reliably regardless of their exact
pixel position, and provides a reliable "show the desktop" primitive. Windows
only; ``uiautomation`` is imported lazily and a Null locator is used otherwise.

Locale-aware name candidates cover English + Turkish (the two locales this repo
targets); add more as needed.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

# Context-menu item name candidates (en + tr).
NEW_MENU_NAMES = ("New", "Yeni")
TEXT_DOCUMENT_NAMES = ("Text Document", "Metin Belgesi", "Text Belgesi")
SHOW_MORE_NAMES = ("Show more options", "Daha fazla seçenek göster")


@runtime_checkable
class DesktopUi(Protocol):
    """Locate desktop targets and reveal the desktop."""

    def show_desktop(self) -> bool: ...
    def menu_item_center(self, names: tuple[str, ...], timeout: float = 2.0) -> Optional[tuple[int, int]]: ...
    def desktop_item_center(self, names: tuple[str, ...], timeout: float = 2.0) -> Optional[tuple[int, int]]: ...
    def active_window_title(self) -> str: ...


class NullDesktopUi:
    """No-op locator for tests/headless: finds nothing, can't show desktop."""

    def show_desktop(self) -> bool:
        return False

    def menu_item_center(self, names, timeout: float = 2.0):
        return None

    def desktop_item_center(self, names, timeout: float = 2.0):
        return None

    def active_window_title(self) -> str:
        return ""


class WindowsDesktopUi:
    """Real locator via uiautomation + Win32. Construct only on Windows."""

    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsDesktopUi requires Windows")
        import ctypes  # noqa: F401
        import uiautomation  # noqa: F401  (probe so the factory can fall back)

        self._ctypes = ctypes
        self._auto = uiautomation

    def show_desktop(self) -> bool:
        # Shell.MinimizeAll is the most reliable "show desktop"; fall back to Win+D.
        try:
            import win32com.client

            win32com.client.Dispatch("Shell.Application").MinimizeAll()
            return True
        except Exception:
            try:
                u = self._ctypes.windll.user32
                for vk, up in ((0x5B, 0), (0x44, 0), (0x44, 2), (0x5B, 2)):  # Win+D
                    u.keybd_event(vk, 0, up, 0)
                return True
            except Exception:
                return False

    def _center(self, ctrl) -> Optional[tuple[int, int]]:
        try:
            r = ctrl.BoundingRectangle
            if r is None:
                return None
            return (r.left + r.right) // 2, (r.top + r.bottom) // 2
        except Exception:
            return None

    def menu_item_center(self, names, timeout: float = 2.0):
        for nm in names:
            it = self._auto.MenuItemControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        return None

    def desktop_item_center(self, names, timeout: float = 2.0):
        for nm in names:
            it = self._auto.ListItemControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        return None

    def active_window_title(self) -> str:
        ctypes = self._ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1)
        return b.value or ""


def get_desktop_dir() -> str:
    """Resolve the real Desktop folder (handles OneDrive redirection).

    Reads the user's Shell Folders registry value so OneDrive-redirected
    desktops resolve correctly; falls back to ~/Desktop.
    """
    import os

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        try:
            val, _ = winreg.QueryValueEx(key, "Desktop")
            return os.path.expandvars(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def get_desktop_ui(prefer_real: bool = True) -> DesktopUi:
    """Return the best available desktop UI locator, falling back to Null."""
    if prefer_real:
        try:
            return WindowsDesktopUi()
        except Exception:
            pass
    return NullDesktopUi()
