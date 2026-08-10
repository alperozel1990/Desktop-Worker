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


def _server_and_bridge(tmp_path):
    from mcp.server.fastmcp import FastMCP

    # Isolate BOTH artifacts and the emergency-stop sentinel under tmp.
    cfg = Config(session_id="mcp-e2e", task_id="t", artifacts_root=tmp_path,
                 estop_file=tmp_path / "EMERGENCY_STOP")
    bridge = build_agent_bridge(real=False, config=cfg)  # Null backends
    server = FastMCP(SERVER_NAME)
    register(server, bridge)
    return server, bridge


def _server(tmp_path):
    return _server_and_bridge(tmp_path)[0]


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
    assert len(names) == 24
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


def _png_bytes(width=2, height=2):
    import struct
    import zlib

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class _ShotObserver:
    """Observer stand-in reporting a real, decodable PNG at a path we control."""

    def __init__(self, ref):
        self._ref = ref

    def observe(self, agent, screenshot=True):
        class _Obs:
            screenshotRef = self._ref
            screenshotError = None

            def to_dict(_self):
                return {"screenshotRef": self._ref, "screenshotError": None}

        return _Obs()


def test_screenshot_wire_response_keeps_the_path_alongside_the_image(tmp_path):
    """A successful inline capture used to hand the SDK's Image object back on
    its own, silently dropping `path`/`ok` off the wire (a real capture with
    no evidence of its own path — UQC-BL-1's second layer). The tool must now
    return the metadata as one content block and the image as another."""
    shot = tmp_path / "shot.png"
    shot.write_bytes(_png_bytes())
    server, bridge = _server_and_bridge(tmp_path)
    bridge.session.observer = _ShotObserver(str(shot))

    result = asyncio.run(server.call_tool("screenshot", {}))
    content = result[0] if isinstance(result, tuple) else result

    types = [item.type for item in content]
    assert "text" in types and "image" in types

    meta = json.loads(next(item.text for item in content if item.type == "text"))
    assert meta["ok"] is True
    assert meta["path"] == str(shot)
    assert "image" not in meta  # not duplicated into the text block

    image_block = next(item for item in content if item.type == "image")
    assert image_block.data  # non-empty base64 image payload
