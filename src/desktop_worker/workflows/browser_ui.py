"""Browser UI locator (Phase 5 helper).

Locates input fields and buttons inside the focused browser window via UI
Automation so the browser workflow can click them by (part of) their name/label
rather than guessing pixels. Windows only; ``uiautomation`` is imported lazily
and a Null locator is used otherwise (so the workflow stays headless-testable).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

# Common confirm/submit button labels (en + tr).
SUBMIT_NAMES = ("Submit", "Search", "Sign in", "Log in", "Send", "OK", "Continue",
                "Gönder", "Ara", "Giriş", "Oturum aç", "Tamam", "Devam")


@runtime_checkable
class BrowserUi(Protocol):
    """Locate browser input fields and buttons by name."""

    def edit_center(self, names: tuple[str, ...],
                    timeout: float = 2.0) -> Optional[tuple[int, int]]: ...
    def button_center(self, names: tuple[str, ...],
                      timeout: float = 2.0) -> Optional[tuple[int, int]]: ...


class NullBrowserUi:
    """No-op locator for tests/headless: finds nothing."""

    def edit_center(self, names, timeout: float = 2.0):
        return None

    def button_center(self, names, timeout: float = 2.0):
        return None


class WindowsBrowserUi:
    """Real locator via uiautomation. Construct only on Windows."""

    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsBrowserUi requires Windows")
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

    def edit_center(self, names, timeout: float = 2.0):
        for nm in names:
            it = self._auto.EditControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        return None

    def button_center(self, names, timeout: float = 2.0):
        for nm in names:
            it = self._auto.ButtonControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        # Hyperlinks often act as submit controls on the web.
        for nm in names:
            it = self._auto.HyperlinkControl(Name=nm)
            if it.Exists(timeout):
                c = self._center(it)
                if c:
                    return c
        return None


def get_browser_ui(prefer_real: bool = True) -> BrowserUi:
    """Return the best available browser UI locator, falling back to Null."""
    if prefer_real:
        try:
            return WindowsBrowserUi()
        except Exception:
            pass
    return NullBrowserUi()
