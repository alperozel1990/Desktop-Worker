"""Process-wide Windows DPI awareness, decided once at startup (DW-DPI-aware).

Whether Win32 coordinates a process reads/writes are physical or DPI-virtualized
is decided the first time *something* in the process opts it into DPI awareness
— and that decision sticks for the process's lifetime. Two independent things in
this codebase used to make that decision lazily, as a side effect of unrelated
work:

  * ``WindowsDesktopBackend.screen()`` called the legacy ``SetProcessDPIAware()``
    (system-DPI-aware, not per-monitor) only when ``observe``/``screenshot`` had
    already run at least once.
  * the third-party ``mss`` screenshot library sets ``SetProcessDpiAwareness``
    (PROCESS_PER_MONITOR_DPI_AWARE) itself, as a side effect of constructing
    ``mss.mss()`` (see ``mss/windows/gdi.py: _set_dpi_awareness``), the first
    time anything grabs a screenshot.

Whichever of those ran first "won" the process's awareness level. An MCP server
spawn that calls ``mouse.move`` before any screenshot/observe call never
triggered either path, so the process stayed fully DPI-unaware: Windows then
DPI-virtualizes every coordinate the process sends through ``SetCursorPos``/
``SendInput`` by the display scale factor (measured: requesting (959, 570) at
125% scaling landed the physical cursor at (1199, 713) = exactly 1.25x). Spawns
that happened to call ``screenshot``/``perceive`` first landed correctly, purely
by accident of call order.

The fix: decide it exactly once, deterministically, before any backend touches
a screen or input API — not as an incidental side effect of whichever backend
constructs or gets called first.
"""

from __future__ import annotations

import sys

import ctypes

#: Cached result of the first call. The OS decision is per-process and (mostly)
#: cannot be changed once made, so re-deciding per call site would either be a
#: no-op or, worse, make later callers observe a spurious "unaware" when an
#: earlier call already won a stronger level — caching keeps every caller in
#: the process honest about what was actually achieved.
_ACHIEVED: str | None = None


def set_process_dpi_awareness() -> str:
    """Set this process's DPI awareness once, before any input/screen API is used.

    Tries the most capable level first, falling back for older Windows:

      1. ``SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`` — Windows 10
         1703+, the modern per-monitor-v2 level.
      2. ``SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)`` — Windows
         8.1+.
      3. ``SetProcessDPIAware()`` — Vista+, system-DPI-aware (coarser, but still
         means coordinates are not silently virtualized).

    Never raises: on non-Windows, or a Windows old enough that none of the
    above exist, the process just keeps whatever awareness the OS defaults to,
    and that fail-safe outcome is reported honestly via the return value
    instead of crashing server startup over a cosmetic capability.

    Idempotent — the first call decides it for the process; later calls return
    the cached result without touching ctypes again.
    """
    global _ACHIEVED
    if _ACHIEVED is not None:
        return _ACHIEVED

    if not sys.platform.startswith("win"):
        _ACHIEVED = "not_windows"
        return _ACHIEVED

    # 1) PER_MONITOR_AWARE_V2 (Windows 10 1703+).
    try:
        user32 = ctypes.windll.user32
        set_ctx = user32.SetProcessDpiAwarenessContext
        set_ctx.argtypes = [ctypes.c_void_p]
        set_ctx.restype = ctypes.c_int
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        if set_ctx(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            _ACHIEVED = "per_monitor_v2"
            return _ACHIEVED
    except Exception:
        pass

    # 2) PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+).
    try:
        shcore = ctypes.windll.shcore
        PROCESS_PER_MONITOR_DPI_AWARE = 2
        if shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0:  # S_OK
            _ACHIEVED = "per_monitor"
            return _ACHIEVED
    except Exception:
        pass

    # 3) SetProcessDPIAware (Vista+) — coarser, but still not virtualized.
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            _ACHIEVED = "system"
            return _ACHIEVED
    except Exception:
        pass

    _ACHIEVED = "unaware"
    return _ACHIEVED


def reset_for_tests() -> None:
    """Test-only: clear the cached result so a test can exercise a fresh call.

    Production code never needs this — the whole point of the cache is that a
    real process decides awareness exactly once.
    """
    global _ACHIEVED
    _ACHIEVED = None
