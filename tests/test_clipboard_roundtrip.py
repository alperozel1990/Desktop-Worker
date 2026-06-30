"""Real-clipboard round-trip test for the 64-bit handle fix (DW-CLIP-FIX).

The Windows clipboard path was fully broken on 64-bit Python (`OverflowError: int
too long to convert`) because ctypes truncated the 64-bit GlobalAlloc/GlobalLock/
GetClipboardData handles to 32-bit. Skips on non-Windows and if the real backend
can't construct (headless CI), so it never blocks the core suite.
"""

import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="exercises the real Windows clipboard")
def test_clipboard_set_get_roundtrip():
    try:
        from desktop_worker.actions.windows_input import WindowsInputBackend
        ib = WindowsInputBackend()
    except Exception as exc:  # noqa: BLE001 — no real backend here → skip, don't fail
        pytest.skip(f"WindowsInputBackend unavailable: {exc}")

    for text in ["hello", "merhaba ş ı ğ", "line1\nline2\twith tab", "x" * 500]:
        ib.clipboard_set(text)
        assert ib.clipboard_get() == text
