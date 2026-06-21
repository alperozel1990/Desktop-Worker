"""Action executor (requirements section 8).

Single choke point for executing structured actions:

    validate -> emergency-stop check -> policy/approval -> dry-run? ->
    dispatch to backend (or CLI broker) -> ActionResult -> audit

Guarantees:
  * Malformed actions never execute (schema validation happens first).
  * High-risk actions never execute without policy approval.
  * cli.run is delegated to the elevated broker — never run inline here.
  * Every action produces an ActionResult and an audit entry.
"""

from __future__ import annotations

from typing import Any, Optional

from desktop_worker.actions.backends import InputBackend, get_input_backend
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.safety.emergency_stop import EmergencyStop, EmergencyStopError
from desktop_worker.safety.policy import ApprovalRequest, PermissionPolicy, RiskLevel
from desktop_worker.schema.actions import Action
from desktop_worker.schema.results import ActionResult
from desktop_worker.util import utc_now_iso


class ActionExecutor:
    def __init__(
        self,
        *,
        audit: AuditLog,
        policy: PermissionPolicy,
        input_backend: Optional[InputBackend] = None,
        broker: Optional[ElevatedCliBroker] = None,
        estop: Optional[EmergencyStop] = None,
        dry_run: bool = False,
        agent: str = "system",
        role: str = "system",
        tools: Any = None,
    ) -> None:
        self.audit = audit
        self.policy = policy
        self.input = input_backend or get_input_backend()
        self.broker = broker
        self.estop = estop or EmergencyStop()
        self.dry_run = dry_run
        self.agent = agent
        self.role = role
        # Optional tool registry (AI-callable reliable workflows). None => the
        # AI cannot use tool.run (fails safe, like cli.run without a broker).
        self.tools = tools
        self._in_tool = False  # nesting guard: a tool's sub-actions can't be tool.run

    def execute(self, action: Action) -> ActionResult:
        started = utc_now_iso()

        # 1) Emergency stop / pause guard — before anything else.
        try:
            self.estop.check()
        except EmergencyStopError as exc:
            return self._fail(action, started, f"halted: {exc}", event="action.halted")

        # 2) Approval / risk policy. cli.run risk is classified in the broker;
        #    tool.run risk is declared by the named tool (unknown tool => HIGH).
        if action.type == "tool.run":
            ok, risk = self._authorize_tool(action)
            if not ok:
                res = self._fail(action, started,
                                 f"tool not approved (risk={risk.value})",
                                 event="action.blocked")
                res.detail["riskLevel"] = risk.value
                return res
        elif action.type != "cli.run":
            ok, risk = self.policy.authorize_action(action)
            if not ok:
                res = self._fail(
                    action, started,
                    f"action not approved (risk={risk.value})",
                    event="action.blocked",
                )
                res.detail["riskLevel"] = risk.value
                return res

        # 3) Dry-run: validate + log, never touch the desktop.
        if self.dry_run:
            res = ActionResult(
                action_type=action.type, success=True,
                startedAt=started, endedAt=utc_now_iso(),
                detail={"dryRun": True},
            )
            self.audit.record(
                "action.dryrun", agent=self.agent, role=self.role,
                action=action.to_dict(), result=res.to_dict(),
            )
            return res

        # 4) Dispatch.
        try:
            detail = self._dispatch(action)
        except EmergencyStopError as exc:
            return self._fail(action, started, f"halted: {exc}", event="action.halted")
        except Exception as exc:  # noqa: BLE001 — turn any backend error into a result
            return self._fail(action, started, f"{type(exc).__name__}: {exc}")

        res = ActionResult(
            action_type=action.type, success=True,
            startedAt=started, endedAt=utc_now_iso(),
            detail=detail or {},
        )
        self.audit.record(
            "action.executed", agent=self.agent, role=self.role,
            action=action.to_dict(), result=res.to_dict(),
        )
        return res

    # --- dispatch table ------------------------------------------------
    def _dispatch(self, action: Action) -> dict:
        p = action.params
        t = action.type
        ib = self.input

        if t == "mouse.move":
            ib.move(p["x"], p["y"]); return {}
        if t == "mouse.moveRelative":
            ib.move_relative(p["dx"], p["dy"]); return {}
        if t == "mouse.click":
            ib.click(p.get("button", "left"), p.get("x"), p.get("y")); return {}
        if t == "mouse.doubleClick":
            ib.double_click(p.get("button", "left"), p.get("x"), p.get("y")); return {}
        if t == "mouse.rightClick":
            ib.click("right", p.get("x"), p.get("y")); return {}
        if t == "mouse.down":
            ib.mouse_down(p.get("button", "left")); return {}
        if t == "mouse.up":
            ib.mouse_up(p.get("button", "left")); return {}
        if t == "mouse.scroll":
            ib.scroll(p.get("dx", 0), p.get("dy", 0)); return {}
        if t == "mouse.drag":
            fx, fy = p["from"]; tx, ty = p["to"]
            ib.drag(fx, fy, tx, ty, p.get("durationMs", 600)); return {}
        if t == "mouse.stroke":
            ib.stroke(list(p["points"]), p.get("durationMs", 800)); return {}

        if t == "keyboard.type":
            ib.type_text(p["text"]); return {}
        if t == "keyboard.press":
            ib.press_key(p["key"]); return {}
        if t == "keyboard.hotkey":
            ib.hotkey(list(p["keys"])); return {}

        if t == "clipboard.set":
            ib.clipboard_set(p["text"]); return {}
        if t == "clipboard.get":
            return {"text": ib.clipboard_get()}

        if t == "wait":
            import time
            time.sleep(p["durationMs"] / 1000.0); return {}

        if t == "cli.run":
            if self.broker is None:
                raise RuntimeError("cli.run requires a CLI broker; none configured")
            result = self.broker.run(
                p["command"], p["cwd"],
                timeout_ms=p.get("timeoutMs"),
                elevated=p.get("elevated", True),
                agent=self.agent, role=self.role,
            )
            if result.blocked:
                raise RuntimeError(f"cli blocked: {result.blockedReason}")
            return {"cli": result.to_dict()}

        if t == "tool.run":
            if self.tools is None:
                raise RuntimeError("tool.run requires a tools registry; none configured")
            if self._in_tool:
                raise RuntimeError("a tool may not call tool.run (no nesting)")
            name, args = p["tool"], p.get("args", {})
            self._in_tool = True
            try:
                result = self.tools.run(name, args)  # raises on unknown/failed tool
            finally:
                self._in_tool = False
            # If a sub-action tripped the emergency stop, propagate as a halt.
            if self.estop.is_stopped():
                raise EmergencyStopError(self.estop.reason or "emergency stop active")
            return {"tool": name, "args": args, "result": result}

        # window.focus and verify are handled by higher layers (loop/perception);
        # reaching here means a known-but-unhandled type.
        raise NotImplementedError(f"action type not handled by executor: {t}")

    # --- helpers -------------------------------------------------------
    def _authorize_tool(self, action: Action) -> tuple[bool, RiskLevel]:
        """Authorize a tool.run by the named tool's declared risk (unknown => HIGH)."""
        name = action.params.get("tool", "")
        risk_str = self.tools.risk_of(name) if self.tools is not None else "high"
        try:
            risk = RiskLevel(risk_str)
        except ValueError:
            risk = RiskLevel.HIGH
        ok = self.policy.authorize(ApprovalRequest(
            kind="tool", summary=f"tool {name}({action.params.get('args', {})})",
            risk=risk, detail=action.to_dict(),
        ))
        return ok, risk
    def _fail(self, action: Action, started: str, error: str,
              *, event: str = "action.failed") -> ActionResult:
        res = ActionResult(
            action_type=action.type, success=False,
            startedAt=started, endedAt=utc_now_iso(), error=error,
        )
        self.audit.record(
            event, agent=self.agent, role=self.role,
            action=action.to_dict(), result=res.to_dict(),
        )
        return res
