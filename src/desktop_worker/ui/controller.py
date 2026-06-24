"""Pure UI controller for the Phase 7 control window (no Tkinter import here).

Responsibilities:

* build the audit *timeline* from the JSONL log (reuses ``AuditLog.read_all``);
* list screenshot / report artifacts for preview;
* expose the safety controls (estop / clear / pause / resume) by delegating to
  the shared :class:`EmergencyStop`;
* hold a submitted task for the UI's worker thread to pick up;
* provide a thread-safe, *blocking* approval handshake: the broker's synchronous
  approval callback (running on the worker thread) calls
  :meth:`UiController.approve`, which blocks until the UI thread calls
  :meth:`resolve_approval`. A timeout (or no decision) denies — fail safe.

Everything here is deterministic and unit-testable without a display.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from desktop_worker.audit.log import AuditLog


def summarize_event(record: dict[str, Any]) -> str:
    """One-line human summary of an audit record for the timeline."""
    ts = str(record.get("timestamp", ""))[11:19]  # HH:MM:SS
    event = record.get("event", "?")
    agent = record.get("agent", "")
    bits = [f"{ts} {event}"]
    if agent and agent != "system":
        bits.append(f"[{agent}]")
    action = record.get("action")
    if isinstance(action, dict) and action.get("type"):
        bits.append(str(action["type"]))
    cli = record.get("cli")
    if isinstance(cli, dict) and cli.get("command"):
        bits.append(str(cli["command"])[:60])
    for key in ("reason", "summary", "outcome", "verdict", "error"):
        if record.get(key):
            bits.append(f"{key}={record[key]}")
            break
    return " ".join(bits)


class ApprovalQueue:
    """Single-slot, thread-safe, blocking approval handshake.

    The worker thread calls :meth:`request` (blocks); the UI thread observes
    :meth:`pending` and answers with :meth:`resolve`. Deny-by-default: a timeout
    or an unanswered request returns ``False``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._request: Optional[Any] = None
        self._pending = False
        self._decision = False

    def request(self, req: Any, timeout: Optional[float] = None) -> bool:
        with self._lock:
            self._request = req
            self._pending = True
            self._decision = False
            self._event.clear()
        got = self._event.wait(timeout)
        with self._lock:
            self._pending = False
            self._request = None
            return self._decision if got else False

    def pending(self) -> Optional[Any]:
        with self._lock:
            return self._request if self._pending else None

    def resolve(self, approved: bool) -> None:
        with self._lock:
            self._decision = bool(approved)
            self._event.set()


class UiController:
    def __init__(self, cfg: Any, estop: Any, *, max_timeline: int = 300) -> None:
        self._cfg = cfg
        self._estop = estop
        self._max_timeline = max_timeline
        self._approvals = ApprovalQueue()
        self._task_lock = threading.Lock()
        self._pending_task: Optional[str] = None

    # --- timeline / artifacts ---------------------------------------
    def timeline(self) -> list[dict[str, Any]]:
        """Most recent audit records (oldest-first), capped at max_timeline."""
        records = AuditLog(self._cfg.audit_file).read_all()
        return records[-self._max_timeline:]

    def timeline_lines(self) -> list[str]:
        return [summarize_event(r) for r in self.timeline()]

    def screenshots(self) -> list[str]:
        d = self._cfg.screenshots_dir
        if not d.exists():
            return []
        return sorted(str(p) for p in d.glob("*.png"))

    def reports(self) -> list[str]:
        d = self._cfg.task_dir
        if not d.exists():
            return []
        return sorted(str(p) for p in d.glob("*.html")) + \
            sorted(str(p) for p in d.glob("*.md"))

    # --- safety controls --------------------------------------------
    def estop(self, reason: str = "stopped from UI") -> None:
        self._estop.stop(reason)

    def clear_stop(self) -> None:
        self._estop.clear()

    def pause(self) -> None:
        self._estop.pause()

    def resume(self) -> None:
        self._estop.resume()

    def is_stopped(self) -> bool:
        return self._estop.is_stopped()

    def is_paused(self) -> bool:
        return self._estop.is_paused()

    # --- task submission --------------------------------------------
    def submit_task(self, text: str) -> None:
        with self._task_lock:
            self._pending_task = str(text or "").strip()

    def pop_task(self) -> Optional[str]:
        """Atomically take the pending task (the worker calls this)."""
        with self._task_lock:
            t = self._pending_task
            self._pending_task = None
            return t or None

    # --- approval handshake -----------------------------------------
    def approve(self, request: Any, timeout: Optional[float] = None) -> bool:
        """Block until the UI resolves this approval request (deny on timeout)."""
        return self._approvals.request(request, timeout=timeout)

    def pending_approval(self) -> Optional[Any]:
        return self._approvals.pending()

    def resolve_approval(self, approved: bool) -> None:
        self._approvals.resolve(approved)
