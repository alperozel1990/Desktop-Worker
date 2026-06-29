"""Tests for the MCP AgentBridge (Phase 8) — the external-AI control surface.

Everything runs on Null backends with no display and no MCP SDK: the bridge is the
dependency-free core, so the whole external-control surface is unit-testable.
"""

import dataclasses

import pytest

from desktop_worker.app import Session
from desktop_worker.config import Config
from desktop_worker.mcp_server.bridge import AgentBridge, build_agent_bridge
from desktop_worker.safety.policy import PermissionPolicy, auto_approve, deny_all
from desktop_worker.schema.observations import Element
from desktop_worker.tools import ToolRegistry


class FakeTool:
    name = "noop"
    description = "a no-op tool"
    args_help = "anything"
    risk = "low"

    def __init__(self):
        self.calls = []

    def run(self, args):
        self.calls.append(args)
        return {"success": True, "echo": args, "error": None}


class FakeBroker:
    """Stand-in for the elevated broker so cli.run never runs a real command."""

    def __init__(self, blocked=False):
        self.calls = []
        self._blocked = blocked

    def run(self, command, cwd, **kw):
        self.calls.append((command, cwd, kw))

        class R:
            pass

        r = R()
        r.blocked = self._blocked
        r.blockedReason = "denied"
        r.to_dict = lambda: {"command": command, "cwd": cwd, "exitCode": 0}
        return r


class FakePerceiver:
    def __init__(self, elements):
        self._elements = tuple(elements)

    def perceive(self, observation):
        return dataclasses.replace(observation, elements=self._elements)


def _bridge(tmp_path, *, approve=True, tools=None, perceiver=None, broker=None):
    # Isolate BOTH artifacts and the emergency-stop sentinel under tmp so the test
    # never reads or pollutes the shared default EMERGENCY_STOP file.
    cfg = Config(session_id="mcp-test", task_id="t", artifacts_root=tmp_path,
                 estop_file=tmp_path / "EMERGENCY_STOP")
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    session = Session(cfg, policy=policy, prefer_real_backends=False)
    if broker is not None:
        session.executor.broker = broker
    return AgentBridge(session, tools=tools, perceiver=perceiver), session


def test_click_routes_through_executor_and_audits(tmp_path):
    bridge, session = _bridge(tmp_path)
    out = bridge.click(10, 20)
    assert out["ok"] is True
    assert out["actionType"] == "mouse.click"
    # The action was audited honestly under the external-agent identity.
    text = session.config.audit_file.read_text(encoding="utf-8")
    assert "mouse.click" in text
    assert "mcp-client" in text


def test_malformed_action_is_rejected_not_executed(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "mouse.move", "x": 1})  # missing required y
    assert out["ok"] is False
    assert "invalid action" in out["error"]


def test_unknown_action_type_rejected(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "totally.bogus"})
    assert out["ok"] is False
    assert "invalid action" in out["error"]


def test_type_text_and_clipboard(tmp_path):
    bridge, _ = _bridge(tmp_path)
    assert bridge.type_text("merhaba ş ı")["ok"] is True
    assert bridge.clipboard_set("x")["ok"] is True
    assert bridge.clipboard_get()["ok"] is True


def test_run_tool_routes_to_registry(tmp_path):
    tool = FakeTool()
    reg = ToolRegistry()
    reg.register(tool)
    bridge, _ = _bridge(tmp_path, tools=reg)
    out = bridge.run_tool("noop", {"a": 1})
    assert out["ok"] is True
    assert tool.calls == [{"a": 1}]


def test_run_tool_without_registry_fails_safe(tmp_path):
    bridge, _ = _bridge(tmp_path)  # no tools
    out = bridge.run_tool("noop", {})
    assert out["ok"] is False
    assert "no tools registry" in out["error"]


def test_run_cli_goes_through_broker(tmp_path):
    broker = FakeBroker()
    bridge, _ = _bridge(tmp_path, broker=broker)
    out = bridge.run_cli("echo hi", cwd=str(tmp_path))
    assert out["ok"] is True
    assert "cli" in out["detail"]
    assert broker.calls and broker.calls[0][0] == "echo hi"


def test_run_cli_blocked_broker_fails_safe(tmp_path):
    broker = FakeBroker(blocked=True)
    bridge, _ = _bridge(tmp_path, broker=broker)
    out = bridge.run_cli("rmdir /s /q C:\\", cwd=str(tmp_path))
    assert out["ok"] is False


def test_emergency_stop_blocks_then_clear_resumes(tmp_path):
    bridge, _ = _bridge(tmp_path)
    bridge.emergency_stop("test")
    blocked = bridge.click(1, 1)
    assert blocked["ok"] is False
    assert "halt" in (blocked["error"] or "").lower()
    bridge.clear_stop()
    assert bridge.click(1, 1)["ok"] is True


def test_perceive_adds_click_centers(tmp_path):
    el = Element(id="e1", type="button", bounds=(10, 20, 30, 40), source="uia",
                 text="OK", confidence=0.9)
    bridge, _ = _bridge(tmp_path, perceiver=FakePerceiver([el]))
    out = bridge.perceive(screenshot=False)
    assert out["ok"] is True
    assert len(out["elements"]) == 1
    assert out["elements"][0]["center"] == [20, 30]
    assert out["elements"][0]["text"] == "OK"


def test_observe_returns_structured_state(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.observe(screenshot=False)
    assert out["ok"] is True
    assert "screen" in out["observation"]


def test_status_lists_tools(tmp_path):
    reg = ToolRegistry()
    reg.register(FakeTool())
    bridge, _ = _bridge(tmp_path, tools=reg)
    st = bridge.status()
    assert st["ok"] is True
    assert "noop" in st["tools"]
    assert st["stopped"] is False


def test_high_risk_denied_under_deny_policy(tmp_path):
    """A HIGH-risk tool is denied when the policy denies — safety stays below."""
    reg = ToolRegistry()

    class HighTool(FakeTool):
        name = "danger"
        risk = "high"

    reg.register(HighTool())
    bridge, _ = _bridge(tmp_path, approve=False, tools=reg)
    out = bridge.run_tool("danger", {})
    assert out["ok"] is False


def test_build_agent_bridge_null_wires_default_tools(tmp_path):
    cfg = Config(session_id="mcp-build", task_id="t", artifacts_root=tmp_path)
    bridge = build_agent_bridge(real=False, config=cfg)
    names = {t["name"] for t in bridge.list_tools()["tools"]}
    assert {"create_text_file", "open_app", "open_url", "focus_window",
            "drag_drop", "sketch"} <= names
