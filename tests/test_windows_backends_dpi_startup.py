"""Hermetic ordering tests: DPI awareness is decided at backend construction,
strictly before any screen/input Win32 API call (DW-DPI-aware).

`ctypes.windll` is monkeypatched on the real `ctypes` module so these run
without a display and without depending on the host actually being Windows;
`sys.platform` is forced to "win32" so the backends' own guard clause passes.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

from desktop_worker import dpi_awareness


@pytest.fixture(autouse=True)
def _reset_cache():
    dpi_awareness.reset_for_tests()
    yield
    dpi_awareness.reset_for_tests()


@pytest.fixture
def win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")


def test_desktop_backend_decides_dpi_awareness_before_screen_touches_win32(monkeypatch, win32):
    import ctypes

    order: list[str] = []
    monkeypatch.setattr(
        dpi_awareness, "set_process_dpi_awareness",
        lambda: (order.append("dpi_awareness"), "per_monitor_v2")[1],
    )

    user32 = Mock()
    user32.GetSystemMetrics.side_effect = lambda i: (order.append("GetSystemMetrics"), 1920)[1]
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)

    from desktop_worker.observation.windows_backend import WindowsDesktopBackend

    backend = WindowsDesktopBackend()
    # DPI awareness must already be decided by the time __init__ returns.
    assert order == ["dpi_awareness"]
    assert backend.dpi_awareness == "per_monitor_v2"

    backend.screen()
    # screen() must not re-decide it — construction owns that, once.
    assert order == ["dpi_awareness", "GetSystemMetrics", "GetSystemMetrics"]


def test_input_backend_decides_dpi_awareness_before_move_calls_setcursorpos(monkeypatch, win32):
    import ctypes

    order: list[str] = []
    monkeypatch.setattr(
        dpi_awareness, "set_process_dpi_awareness",
        lambda: (order.append("dpi_awareness"), "per_monitor_v2")[1],
    )

    user32 = Mock()
    user32.SetCursorPos.side_effect = lambda x, y: order.append("SetCursorPos")
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)

    from desktop_worker.actions.windows_input import WindowsInputBackend

    backend = WindowsInputBackend()
    assert order == ["dpi_awareness"]
    assert backend.dpi_awareness == "per_monitor_v2"

    backend.move(959, 570)
    assert order == ["dpi_awareness", "SetCursorPos"]


def test_both_backends_in_one_process_agree_on_the_cached_result(monkeypatch, win32):
    """Reproduces the original bug's precondition: whichever backend constructs
    first must not leave the other with a different, order-dependent answer."""
    import ctypes

    user32 = Mock()
    user32.SetProcessDpiAwarenessContext.return_value = 1
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)

    from desktop_worker.actions.windows_input import WindowsInputBackend
    from desktop_worker.observation.windows_backend import WindowsDesktopBackend

    input_backend = WindowsInputBackend()
    desktop_backend = WindowsDesktopBackend()

    assert input_backend.dpi_awareness == desktop_backend.dpi_awareness == "per_monitor_v2"
    # Only decided once for the whole process, regardless of construction order.
    assert user32.SetProcessDpiAwarenessContext.call_count == 1
