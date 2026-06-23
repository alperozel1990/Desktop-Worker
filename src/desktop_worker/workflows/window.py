"""Window switching + drag-and-drop workflow (requirements Phase 5).

Two small, reliable desktop capabilities:

* ``switch_window`` brings an open window to the foreground by (part of) its
  title. The OS enumeration/focus calls are injectable, so it delegates to the
  pure matcher in :class:`~desktop_worker.tools.builtin.FocusWindowTool` and is
  testable without a real desktop.
* ``drag_drop`` performs a press-move-release drag between two points. Like every
  other workflow input, it is emitted as a *structured action* through the audited,
  emergency-stop-gated executor (``mouse.drag``) — never by poking a backend
  directly — so it is validated, policy-checked and logged like any other action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from desktop_worker.schema.actions import parse_action


@dataclass
class WindowResult:
    """Outcome of a window/drag workflow step."""

    success: bool
    action: str
    detail: str = ""
    steps: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "action": self.action,
                "detail": self.detail, "steps": list(self.steps), "error": self.error}

    def to_markdown(self) -> str:
        head = f"{'OK' if self.success else 'FAILED'}: {self.action}"
        body = "".join(f"\n  - {s}" for s in self.steps)
        tail = f"\n  error: {self.error}" if self.error else ""
        return f"{head} ({self.detail}){body}{tail}"


def switch_window(title_contains: str, *, enum_windows: Any = None,
                  focus: Any = None) -> WindowResult:
    """Bring the first window whose title contains ``title_contains`` to the front.

    ``enum_windows`` / ``focus`` are injectable (default = real Win32 via
    :class:`FocusWindowTool`) so this is unit-testable on a headless machine.
    """
    from desktop_worker.tools.builtin import FocusWindowTool

    title_contains = str(title_contains or "").strip()
    if not title_contains:
        return WindowResult(False, "switch_window", error="empty title")

    tool = FocusWindowTool(enum_windows=enum_windows, focus=focus)
    res = tool.run({"title_contains": title_contains})
    ok = bool(res.get("success"))
    found = res.get("title") or title_contains
    return WindowResult(
        ok, "switch_window", detail=f"focus {title_contains!r}",
        steps=[f"{'ok' if ok else 'FAIL'}: focus {found!r}"],
        error="" if ok else str(res.get("error") or "no matching window"))


def drag_drop(from_xy: tuple[int, int], to_xy: tuple[int, int], *, executor: Any,
              duration_ms: int = 600) -> WindowResult:
    """Drag from ``from_xy`` to ``to_xy`` via a single audited ``mouse.drag`` action."""
    fx, fy = int(from_xy[0]), int(from_xy[1])
    tx, ty = int(to_xy[0]), int(to_xy[1])
    action = parse_action({"type": "mouse.drag", "from": [fx, fy], "to": [tx, ty],
                           "durationMs": int(duration_ms)})
    res = executor.execute(action)
    ok = getattr(res, "success", False)
    detail = f"({fx},{fy}) -> ({tx},{ty})"
    return WindowResult(
        bool(ok), "drag_drop", detail=detail,
        steps=[f"{'ok' if ok else 'FAIL'}: drag {detail}"],
        error="" if ok else str(getattr(res, "error", "") or "drag failed"))
