"""Emergency stop + pause mechanism (requirements sections 12, 16).

Two independent halt channels, checked before every action:

1. In-process flag — flipped by ``stop()`` (e.g. a UI button on the same
   process) for instant effect.
2. File sentinel — an external process (the status .bat, a separate UI, or the
   user) can create the estop file to halt a running session it does not share
   memory with.

This is deliberately simple and dependency-free so it can never be the thing
that fails when you most need it to work.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional


class EmergencyStopError(RuntimeError):
    """Raised when execution is halted by an emergency stop or pause."""


class EmergencyStop:
    def __init__(self, estop_file: Optional[Path] = None) -> None:
        self._stopped = threading.Event()
        self._paused = threading.Event()
        self._estop_file = Path(estop_file) if estop_file else None
        self._reason: str = ""

    # --- stop ----------------------------------------------------------
    def stop(self, reason: str = "user requested emergency stop") -> None:
        """Trigger an emergency stop (in-process + persistent file flag)."""
        self._reason = reason
        self._stopped.set()
        if self._estop_file is not None:
            try:
                self._estop_file.parent.mkdir(parents=True, exist_ok=True)
                self._estop_file.write_text(reason, encoding="utf-8")
            except OSError:
                # Never let artifact I/O prevent the stop from taking effect.
                pass

    def clear(self) -> None:
        """Reset stop/pause state and remove the sentinel file."""
        self._stopped.clear()
        self._paused.clear()
        self._reason = ""
        if self._estop_file is not None and self._estop_file.exists():
            try:
                self._estop_file.unlink()
            except OSError:
                pass

    def is_stopped(self) -> bool:
        if self._stopped.is_set():
            return True
        if self._estop_file is not None and self._estop_file.exists():
            self._stopped.set()  # latch so subsequent checks are cheap
            return True
        return False

    @property
    def reason(self) -> str:
        if self._reason:
            return self._reason
        if self._estop_file is not None and self._estop_file.exists():
            try:
                return self._estop_file.read_text(encoding="utf-8") or "estop file present"
            except OSError:
                return "estop file present"
        return ""

    # --- pause ---------------------------------------------------------
    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    # --- guard ---------------------------------------------------------
    def check(self) -> None:
        """Raise :class:`EmergencyStopError` if execution must not continue.

        Call this before every action. Pause blocks (no busy loop) until
        resumed or until a stop is triggered.
        """
        if self.is_stopped():
            raise EmergencyStopError(self.reason or "emergency stop active")
        # If paused, wait in small slices so a stop can still interrupt.
        while self._paused.is_set():
            if self.is_stopped():
                raise EmergencyStopError(self.reason or "emergency stop active")
            self._paused.wait(timeout=0.1)
