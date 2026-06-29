"""End-to-end test through the REAL FastMCP server (Phase 8).

Locks in the validation that the SDK's `tool()` decorator + schema inference match
`register`, and that a tool call flows MCP -> AgentBridge -> executor and back. Skipped
cleanly when the `mcp` SDK is not installed (CI without the [mcp] extra), so it never
blocks the core suite. Runs on Null backends — no display, no real desktop.
"""

import asyncio
import importlib.util
import json

import pytest

if importlib.util.find_spec("mcp") is None:  # SDK not installed
    pytest.skip("mcp SDK not installed; skipping real-server e2e", allow_module_level=True)

from desktop_worker.config import Config
from desktop_worker.mcp_server.bridge import build_agent_bridge
from desktop_worker.mcp_server.server import SERVER_NAME, register


def _server(tmp_path):
    from mcp.server.fastmcp import FastMCP

    # Isolate BOTH artifacts and the emergency-stop sentinel under tmp.
    cfg = Config(session_id="mcp-e2e", task_id="t", artifacts_root=tmp_path,
                 estop_file=tmp_path / "EMERGENCY_STOP")
    bridge = build_agent_bridge(real=False, config=cfg)  # Null backends
    server = FastMCP(SERVER_NAME)
    register(server, bridge)
    return server


def _val(result):
    """Extract the tool's JSON return value from a FastMCP call_tool result.

    Tolerates SDK variants that return a content list or a (content, structured) tuple.
    """
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def _call(server, name, args=None):
    return _val(asyncio.run(server.call_tool(name, args or {})))


def test_all_tools_registered_on_real_server(tmp_path):
    server = _server(tmp_path)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert len(names) == 22
    assert {"observe", "perceive", "click", "type_text", "run_tool", "run_cli",
            "act", "emergency_stop"} <= names


def test_observe_and_click_flow_through_executor(tmp_path):
    server = _server(tmp_path)
    obs = _call(server, "observe", {"screenshot": False})
    assert obs["ok"] is True and "screen" in obs["observation"]
    clicked = _call(server, "click", {"x": 5, "y": 6})
    assert clicked["ok"] is True and clicked["actionType"] == "mouse.click"


def test_list_tools_reports_named_tools(tmp_path):
    server = _server(tmp_path)
    out = _call(server, "list_tools")
    names = {t["name"] for t in out["tools"]}
    assert {"create_text_file", "open_app", "sketch"} <= names


def test_malformed_action_rejected_through_server(tmp_path):
    server = _server(tmp_path)
    out = _call(server, "act", {"action": {"type": "mouse.move", "x": 1}})  # missing y
    assert out["ok"] is False
    assert "invalid action" in out["error"]


def test_emergency_stop_halts_then_clear_resumes_through_server(tmp_path):
    server = _server(tmp_path)
    assert _call(server, "emergency_stop", {})["stopped"] is True
    halted = _call(server, "click", {"x": 1, "y": 1})
    assert halted["ok"] is False and "halt" in (halted["error"] or "").lower()
    assert _call(server, "clear_stop")["stopped"] is False
    assert _call(server, "click", {"x": 1, "y": 1})["ok"] is True
