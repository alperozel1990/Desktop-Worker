"""Tests for the thin MCP server wrapper (Phase 8).

`register` is pure and SDK-free, so a fake server proves every bridge capability is
exposed as a tool without installing the MCP SDK. `serve` must fail clearly when the
SDK is absent.
"""

import importlib.util

import pytest

from desktop_worker.mcp_server.server import register, serve

EXPECTED_TOOLS = {
    "observe", "perceive", "screenshot", "click", "double_click", "right_click",
    "move", "scroll", "drag", "type_text", "press_key", "hotkey", "clipboard_set",
    "clipboard_get", "wait", "run_tool", "run_cli", "act", "list_tools", "status",
    "emergency_stop", "clear_stop",
}


class FakeServer:
    """Mimics FastMCP's `tool()` decorator, recording registered functions."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class FakeBridge:
    """Any method call returns a marker dict so tool wrappers are exercised."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"ok": True, "method": name}
        return method


def test_register_exposes_every_capability():
    server = FakeServer()
    bridge = FakeBridge()
    register(server, bridge)
    assert set(server.tools) == EXPECTED_TOOLS


def test_registered_tools_call_through_to_bridge():
    server = FakeServer()
    bridge = FakeBridge()
    register(server, bridge)

    assert server.tools["observe"]()["method"] == "observe"
    assert server.tools["hotkey"](["CTRL", "S"])["ok"] is True
    assert server.tools["act"]({"type": "wait", "durationMs": 1})["method"] == "act"
    # The bridge actually received the calls.
    called = {c[0] for c in bridge.calls}
    assert {"observe", "hotkey", "act"} <= called


def test_serve_without_sdk_raises_clear_error():
    if importlib.util.find_spec("mcp") is not None:
        pytest.skip("mcp SDK is installed; serve would block on stdio")
    with pytest.raises(RuntimeError, match="MCP SDK is not installed"):
        serve(FakeBridge())
