"""Hermetic tests for desktop_worker.dpi_awareness (DW-DPI-aware).

Fully monkeypatched ctypes: no real Windows calls, no real display, and no
dependency on the host OS. Covers the fallback chain, the never-raises
guarantee, and the once-per-process caching that makes multiple backends
constructing in the same process agree on what was actually achieved.
"""

from __future__ import annotations

import types
from unittest.mock import Mock

import pytest

from desktop_worker import dpi_awareness


@pytest.fixture(autouse=True)
def _reset_cache():
    dpi_awareness.reset_for_tests()
    yield
    dpi_awareness.reset_for_tests()


def _fake_ctypes(*, user32, shcore=None, shcore_raises=False):
    """Build a stand-in for the `ctypes` module with a fake `windll`."""
    windll = types.SimpleNamespace()
    windll.user32 = user32
    if shcore_raises:
        class _MissingShcore:
            def __getattr__(self, _name):  # simulate shcore.dll absent (old Windows)
                raise OSError("shcore.dll not found")
        windll.shcore = _MissingShcore()
    else:
        windll.shcore = shcore if shcore is not None else Mock()
    return types.SimpleNamespace(c_void_p=lambda v: v, c_int=int, windll=windll)


def test_non_windows_never_touches_ctypes(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "linux")
    # A bare object has no `windll` (or anything else) — any access would raise,
    # proving the ctypes-touching branch was never reached.
    monkeypatch.setattr(dpi_awareness, "ctypes", object())

    assert dpi_awareness.set_process_dpi_awareness() == "not_windows"


def test_prefers_per_monitor_v2(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "win32")
    user32 = Mock()
    user32.SetProcessDpiAwarenessContext.return_value = 1
    shcore = Mock()
    monkeypatch.setattr(dpi_awareness, "ctypes", _fake_ctypes(user32=user32, shcore=shcore))

    result = dpi_awareness.set_process_dpi_awareness()

    assert result == "per_monitor_v2"
    user32.SetProcessDpiAwarenessContext.assert_called_once_with(-4)
    shcore.SetProcessDpiAwareness.assert_not_called()
    user32.SetProcessDPIAware.assert_not_called()


def test_falls_back_to_per_monitor_when_v2_context_api_missing(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "win32")
    # No SetProcessDpiAwarenessContext attribute at all -> simulates pre-1703 Windows.
    user32 = Mock(spec=["SetProcessDPIAware"])
    shcore = Mock()
    shcore.SetProcessDpiAwareness.return_value = 0  # S_OK
    monkeypatch.setattr(dpi_awareness, "ctypes", _fake_ctypes(user32=user32, shcore=shcore))

    result = dpi_awareness.set_process_dpi_awareness()

    assert result == "per_monitor"
    shcore.SetProcessDpiAwareness.assert_called_once_with(2)
    user32.SetProcessDPIAware.assert_not_called()


def test_falls_back_to_system_when_shcore_missing(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "win32")
    user32 = Mock(spec=["SetProcessDPIAware"])
    user32.SetProcessDPIAware.return_value = 1
    monkeypatch.setattr(
        dpi_awareness, "ctypes", _fake_ctypes(user32=user32, shcore_raises=True)
    )

    result = dpi_awareness.set_process_dpi_awareness()

    assert result == "system"
    user32.SetProcessDPIAware.assert_called_once()


def test_never_raises_when_nothing_is_available(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "win32")
    user32 = Mock(spec=[])  # no DPI API at all
    monkeypatch.setattr(
        dpi_awareness, "ctypes", _fake_ctypes(user32=user32, shcore_raises=True)
    )

    result = dpi_awareness.set_process_dpi_awareness()

    assert result == "unaware"


def test_result_is_cached_and_ctypes_is_not_touched_again(monkeypatch):
    monkeypatch.setattr(dpi_awareness.sys, "platform", "win32")
    user32 = Mock()
    user32.SetProcessDpiAwarenessContext.return_value = 1
    monkeypatch.setattr(dpi_awareness, "ctypes", _fake_ctypes(user32=user32))

    first = dpi_awareness.set_process_dpi_awareness()
    # Swap ctypes out for something that explodes on any attribute access — the
    # second call must be answered purely from the cache.
    monkeypatch.setattr(dpi_awareness, "ctypes", None)
    second = dpi_awareness.set_process_dpi_awareness()

    assert first == second == "per_monitor_v2"
    assert user32.SetProcessDpiAwarenessContext.call_count == 1
