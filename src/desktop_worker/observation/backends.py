"""Desktop observation backends behind a Protocol (requirements section 6).

The Observer depends only on the :class:`DesktopBackend` interface. A real
Windows backend (lazy heavy imports) provides screenshots, cursor position and
window info; the :class:`NullDesktopBackend` returns deterministic fake data so
the whole observe-plan-act-verify loop and its tests run with no display and no
third-party libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from desktop_worker.schema.observations import ActiveWindow, Cursor, Screen


@runtime_checkable
class DesktopBackend(Protocol):
    """Capabilities required to observe the desktop."""

    def screen(self) -> Screen: ...
    def cursor(self) -> Cursor: ...
    def active_window(self) -> Optional[ActiveWindow]: ...
    def visible_windows(self) -> tuple[str, ...]: ...
    def capture_screenshot(self, dest: Path) -> Optional[str]:
        """Save a screenshot to ``dest`` and return the path, or None."""
        ...


class NullDesktopBackend:
    """Deterministic, dependency-free backend for tests and dry runs."""

    def __init__(
        self,
        *,
        width: int = 1920,
        height: int = 1080,
        cursor: tuple[int, int] = (0, 0),
        active_title: str = "NullDesktop",
        active_process: str = "null.exe",
    ) -> None:
        self._screen = Screen(width=width, height=height, scaleFactor=1.0)
        self._cursor = Cursor(*cursor)
        self._active = ActiveWindow(
            title=active_title, process=active_process,
            bounds=(0, 0, width, height),
        )

    def screen(self) -> Screen:
        return self._screen

    def cursor(self) -> Cursor:
        return self._cursor

    def active_window(self) -> Optional[ActiveWindow]:
        return self._active

    def visible_windows(self) -> tuple[str, ...]:
        return (self._active.title,)

    def capture_screenshot(self, dest: Path) -> Optional[str]:
        # No display in the Null backend: write a tiny placeholder so the
        # artifact reference is real and the audit chain stays intact.
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.with_suffix(".txt").write_text(
            "null-backend placeholder screenshot", encoding="utf-8"
        )
        return str(dest.with_suffix(".txt"))


def get_desktop_backend(prefer_real: bool = True) -> DesktopBackend:
    """Return the best available desktop backend.

    Falls back to :class:`NullDesktopBackend` when the real Windows backend or
    its dependencies are unavailable, so callers always get a usable object.
    """
    if prefer_real:
        try:
            from desktop_worker.observation.windows_backend import WindowsDesktopBackend

            return WindowsDesktopBackend()
        except Exception:
            # Missing deps (mss/pywin32) or non-Windows host: degrade safely.
            pass
    return NullDesktopBackend()
