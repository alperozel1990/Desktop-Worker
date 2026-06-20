"""Input backends behind a Protocol (requirements sections 9, 10).

The executor depends only on :class:`InputBackend`. The Null backend records
every call so tests can assert the executor translated structured actions into
the right primitive calls — without moving a real mouse. The Windows backend
performs real input via the Win32 SendInput API.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class InputBackend(Protocol):
    """Low-level mouse / keyboard / clipboard primitives."""

    # mouse
    def move(self, x: int, y: int) -> None: ...
    def move_relative(self, dx: int, dy: int) -> None: ...
    def mouse_down(self, button: str) -> None: ...
    def mouse_up(self, button: str) -> None: ...
    def click(self, button: str, x: Optional[int], y: Optional[int]) -> None: ...
    def double_click(self, button: str, x: Optional[int], y: Optional[int]) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None: ...
    # keyboard
    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str) -> None: ...
    def hotkey(self, keys: list[str]) -> None: ...
    # clipboard
    def clipboard_set(self, text: str) -> None: ...
    def clipboard_get(self) -> str: ...


class NullInputBackend:
    """Records calls instead of performing them. For tests and dry runs."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._clipboard = ""

    def _rec(self, name: str, *args) -> None:
        self.calls.append((name, *args))

    def move(self, x, y): self._rec("move", x, y)
    def move_relative(self, dx, dy): self._rec("move_relative", dx, dy)
    def mouse_down(self, button): self._rec("mouse_down", button)
    def mouse_up(self, button): self._rec("mouse_up", button)
    def click(self, button, x, y): self._rec("click", button, x, y)
    def double_click(self, button, x, y): self._rec("double_click", button, x, y)
    def scroll(self, dx, dy): self._rec("scroll", dx, dy)
    def drag(self, x1, y1, x2, y2, duration_ms): self._rec("drag", x1, y1, x2, y2, duration_ms)
    def type_text(self, text): self._rec("type_text", text)
    def press_key(self, key): self._rec("press_key", key)
    def hotkey(self, keys): self._rec("hotkey", tuple(keys))

    def clipboard_set(self, text):
        self._clipboard = text
        self._rec("clipboard_set", text)

    def clipboard_get(self) -> str:
        self._rec("clipboard_get")
        return self._clipboard


def get_input_backend(prefer_real: bool = True) -> InputBackend:
    """Return the best available input backend, falling back to Null."""
    if prefer_real:
        try:
            from desktop_worker.actions.windows_input import WindowsInputBackend

            return WindowsInputBackend()
        except Exception:
            pass
    return NullInputBackend()
