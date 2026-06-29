"""AgentBridge — the dependency-free core of the MCP server (Phase 8).

External AI agents drive Desktop-Worker through this bridge. Every capability is
mapped onto the SAME path the built-in planner uses —
``executor.execute(parse_action(...))`` for actions, the observer for state, the
perceiver for elements, the broker for CLI — so all safety stays *below* the
bridge:

  * malformed requests are rejected by ``parse_action`` before touching anything;
  * the emergency stop is checked before every action;
  * the permission policy gates anything above the chosen risk threshold;
  * every action is written to the audit log.

The bridge holds no MCP-specific code and imports no third-party libraries, so the
entire external-control surface is unit-testable with Null backends and no display.
``server.py`` wraps it with the actual MCP SDK.

Invariant: the bridge can only *propose* structured actions; it can never bypass
validation, approval, the emergency stop, or audit. An external AI is exactly as
constrained as the internal planner.
"""

from __future__ import annotations

from typing import Any, Optional

from desktop_worker.app import Session
from desktop_worker.schema.actions import ActionValidationError, parse_action


def _deny_approver(_request: Any) -> bool:
    """Default approval callback for an unattended MCP server: deny.

    With the ``standard`` profile this only affects HIGH-risk requests (e.g. risky
    CLI); LOW/MEDIUM still auto-run. A host that wants interactive approval can pass
    its own callback to :func:`build_agent_bridge`.
    """
    return False


class AgentBridge:
    """Maps MCP tool calls onto Desktop-Worker's audited executor/observer/perceiver.

    Construct with an already-wired :class:`~desktop_worker.app.Session`; optionally
    pass a tools registry (enables ``run_tool``) and a perceiver (enables element
    detection in ``perceive``). Use :func:`build_agent_bridge` for the standard
    real-backend wiring.
    """

    def __init__(
        self,
        session: Session,
        *,
        tools: Any = None,
        perceiver: Any = None,
        default_cwd: Optional[str] = None,
    ) -> None:
        self.session = session
        self.executor = session.executor
        # Expose the same reliable tools the internal planner uses, and attribute
        # audited actions to the external agent so logs are honest about the driver.
        if tools is not None:
            self.executor.tools = tools
        self.tools = tools
        self.perceiver = perceiver
        self.executor.agent = "mcp-client"
        self.executor.role = "external-ai"
        self.default_cwd = default_cwd or str(session.config.artifacts_root.parent)

    # --- generic action path -------------------------------------------
    def act(self, action: dict) -> dict:
        """Execute any structured action (the escape hatch). Validates first."""
        try:
            parsed = parse_action(action)
        except ActionValidationError as exc:
            return {"ok": False, "error": f"invalid action: {exc}"}
        return self._result(self.executor.execute(parsed))

    @staticmethod
    def _result(res: Any) -> dict:
        d = res.to_dict()
        return {
            "ok": bool(d.get("success")),
            "error": d.get("error"),
            "actionType": d.get("actionType"),
            "detail": d.get("detail", {}),
        }

    # --- mouse ----------------------------------------------------------
    def move(self, x: int, y: int) -> dict:
        return self.act({"type": "mouse.move", "x": x, "y": y})

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left") -> dict:
        return self.act(_xy({"type": "mouse.click", "button": button}, x, y))

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None,
                     button: str = "left") -> dict:
        return self.act(_xy({"type": "mouse.doubleClick", "button": button}, x, y))

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        return self.act(_xy({"type": "mouse.rightClick"}, x, y))

    def scroll(self, dx: int = 0, dy: int = 0) -> dict:
        return self.act({"type": "mouse.scroll", "dx": int(dx), "dy": int(dy)})

    def drag(self, frm: Any, to: Any, duration_ms: int = 600) -> dict:
        return self.act({"type": "mouse.drag", "from": list(frm), "to": list(to),
                         "durationMs": int(duration_ms)})

    # --- keyboard -------------------------------------------------------
    def type_text(self, text: str) -> dict:
        return self.act({"type": "keyboard.type", "text": text})

    def press_key(self, key: str) -> dict:
        return self.act({"type": "keyboard.press", "key": key})

    def hotkey(self, keys: Any) -> dict:
        return self.act({"type": "keyboard.hotkey", "keys": list(keys)})

    # --- clipboard / timing --------------------------------------------
    def clipboard_set(self, text: str) -> dict:
        return self.act({"type": "clipboard.set", "text": text})

    def clipboard_get(self) -> dict:
        return self.act({"type": "clipboard.get"})

    def wait(self, duration_ms: int) -> dict:
        return self.act({"type": "wait", "durationMs": int(duration_ms)})

    # --- reliable tools / CLI ------------------------------------------
    def run_tool(self, name: str, args: Optional[dict] = None) -> dict:
        if self.tools is None:
            return {"ok": False, "error": "no tools registry configured"}
        return self.act({"type": "tool.run", "tool": name, "args": args or {}})

    def run_cli(self, command: str, cwd: Optional[str] = None, *,
                elevated: bool = True, timeout_ms: Optional[int] = None) -> dict:
        action: dict[str, Any] = {"type": "cli.run", "command": command,
                                  "cwd": cwd or self.default_cwd,
                                  "elevated": bool(elevated)}
        if timeout_ms is not None:
            action["timeoutMs"] = int(timeout_ms)
        return self.act(action)

    def list_tools(self) -> dict:
        cat = self.tools.catalog() if self.tools is not None else []
        return {"ok": True, "tools": cat}

    # --- perception -----------------------------------------------------
    def observe(self, screenshot: bool = True) -> dict:
        obs = self.session.observer.observe("mcp", screenshot=screenshot)
        return {"ok": True, "observation": obs.to_dict()}

    def perceive(self, screenshot: bool = True) -> dict:
        """Observe + detect UI elements (UIA preferred, OCR fallback).

        Each element carries its id, type, text, bounds, and a ``center`` [x, y] the
        external AI can click directly.
        """
        obs = self.session.observer.observe("mcp", screenshot=screenshot)
        if self.perceiver is not None:
            obs = self.perceiver.perceive(obs)
        d = obs.to_dict()
        elements = []
        for el in d.get("elements", []):
            b = el.get("bounds")
            if isinstance(b, (list, tuple)) and len(b) == 4:
                el = {**el, "center": [int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)]}
            elements.append(el)
        return {
            "ok": True,
            "summary": obs.summary(),
            "activeWindow": d.get("activeWindow"),
            "screen": d.get("screen"),
            "screenshotRef": d.get("screenshotRef"),
            "elements": elements,
        }

    def screenshot(self) -> dict:
        obs = self.session.observer.observe("mcp", screenshot=True)
        return {"ok": True, "path": obs.screenshotRef}

    # --- control / safety ----------------------------------------------
    def status(self) -> dict:
        return {
            "ok": True,
            "backends": self.session.backend_names(),
            "stopped": self.session.estop.is_stopped(),
            "auditLog": str(self.session.config.audit_file),
            "tools": [t["name"] for t in (self.tools.catalog() if self.tools else [])],
        }

    def emergency_stop(self, reason: str = "stop via MCP") -> dict:
        self.session.estop.stop(reason)
        return {"ok": True, "stopped": True}

    def clear_stop(self) -> dict:
        self.session.estop.clear()
        return {"ok": True, "stopped": False}


def _xy(action: dict, x: Optional[int], y: Optional[int]) -> dict:
    """Add optional absolute x/y to a mouse action (omitted => click at cursor)."""
    if x is not None:
        action["x"] = x
    if y is not None:
        action["y"] = y
    return action


def build_agent_bridge(
    *,
    real: bool = True,
    profile: str = "standard",
    approver: Any = None,
    config: Any = None,
) -> AgentBridge:
    """Wire a real-backend :class:`AgentBridge` with the same tools as ``do``.

    ``real`` False forces Null backends (headless smoke). ``profile`` selects the
    safety preset; ``approver`` is the approval callback for interactive profiles
    (defaults to deny, suitable for an unattended server).
    """
    from desktop_worker.config import Config
    from desktop_worker.geometry import get_canvas_locator
    from desktop_worker.geometry.paint_setup import get_paint_ui
    from desktop_worker.perception import Perceiver, get_ocr_backend, get_uia_backend
    from desktop_worker.safety import build_policy
    from desktop_worker.tools import (CreateTextFileTool, DragDropTool, FocusWindowTool,
                                      OpenAppTool, OpenUrlTool, SketchTool, ToolRegistry)
    from desktop_worker.workflows.desktop_ui import get_desktop_dir

    cfg = config or Config(session_id="mcp", task_id="task")
    policy = build_policy(profile, approver or _deny_approver,
                          app_allowlist=cfg.app_allowlist, app_denylist=cfg.app_denylist)
    session = Session(cfg, policy=policy, prefer_real_backends=real)

    desktop_dir = get_desktop_dir()
    tools = ToolRegistry()
    tools.register(CreateTextFileTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(OpenAppTool(desktop_dir=desktop_dir, broker=session.broker, policy=policy))
    tools.register(OpenUrlTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(FocusWindowTool())
    tools.register(DragDropTool(input_backend=session.input_backend, estop=session.estop))
    tools.register(SketchTool(input_backend=session.input_backend,
                              canvas_locator=get_canvas_locator(real),
                              estop=session.estop, paint_ui=get_paint_ui(real)))

    perceiver = Perceiver(ocr=get_ocr_backend(real), uia=get_uia_backend(real))
    return AgentBridge(session, tools=tools, perceiver=perceiver)
