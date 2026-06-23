"""Download wait + locate workflow (requirements Phase 5).

Pure, dependency-free helpers to detect when a browser download has completed
and return the resulting file path. The filesystem and clock are injected, so the
whole module is unit-testable without a real desktop or real downloads.

Strategy: snapshot the download directory *before* triggering the download, then
poll for a new file whose name is not a partial-download marker
(``.crdownload`` / ``.part`` / ``.tmp`` / trailing ``~``). When such a file
appears, it is the completed download.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable, Optional

# Partial-download suffixes used by Chrome/Edge/Firefox and common tools.
_PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".tmp", ".download")


def is_partial(name: str) -> bool:
    """True if ``name`` looks like an in-progress (incomplete) download."""
    low = name.lower()
    return low.endswith(_PARTIAL_SUFFIXES) or low.endswith("~")


def find_new_files(before: Iterable[str], directory: str,
                   listdir: Callable[[str], list[str]] = os.listdir) -> list[str]:
    """Return completed (non-partial) file names in ``directory`` not in ``before``."""
    before_set = set(before)
    try:
        current = listdir(directory)
    except OSError:
        return []
    new = [n for n in current if n not in before_set and not is_partial(n)]
    return sorted(new)


def snapshot(directory: str,
             listdir: Callable[[str], list[str]] = os.listdir) -> set[str]:
    """Snapshot the current file names in ``directory`` (for a `before` set)."""
    try:
        return set(listdir(directory))
    except OSError:
        return set()


def wait_for_download(directory: str, *, before: Optional[Iterable[str]] = None,
                      timeout_s: float = 60.0, poll_s: float = 0.5,
                      now: Callable[[], float] = time.monotonic,
                      sleep: Callable[[float], None] = time.sleep,
                      listdir: Callable[[str], list[str]] = os.listdir) -> Optional[str]:
    """Poll ``directory`` until a new completed download appears; return its path.

    Returns the absolute path of the first new non-partial file, or ``None`` on
    timeout. ``before`` defaults to a fresh snapshot taken now (so call this
    *before* triggering the download for reliable detection, passing the
    pre-download snapshot).
    """
    before_set = set(before) if before is not None else snapshot(directory, listdir)
    start = now()
    while True:
        new = find_new_files(before_set, directory, listdir)
        if new:
            return os.path.join(directory, new[0])
        if now() - start >= timeout_s:
            return None
        sleep(poll_s)


def get_downloads_dir() -> str:
    """Resolve the user's Downloads folder (handles redirection); fall back to ~/Downloads."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        try:
            # The Downloads known folder GUID.
            val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            return os.path.expandvars(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Downloads")
