"""Thin MCP server wrapper around :class:`AgentBridge` (Phase 8).

The MCP SDK is imported lazily inside :func:`serve` so the core package keeps
zero required dependencies (install with ``pip install -e ".[mcp]"``).
:func:`register` is pure: it maps the bridge's methods onto an MCP server object's
``tool()`` decorator, so it can be unit-tested with a fake server and no SDK
present. The function docstrings ARE the tool descriptions the external AI reads,
so they double as the agent-facing contract.
"""

from __future__ import annotations

from typing import Any, Optional

from desktop_worker.mcp_server.bridge import AgentBridge

SERVER_NAME = "desktop-worker"


def register(server: Any, bridge: AgentBridge) -> Any:
    """Register every bridge capability as an MCP tool on ``server``.

    ``server`` must expose ``tool()`` returning a decorator (FastMCP does). Kept
    free of any SDK import so a fake server can drive it in tests.
    """
    tool = server.tool

    @tool()
    def observe(screenshot: bool = True) -> dict:
        """Capture a structured desktop observation: active window, cursor, screen size, and a screenshot reference. Call this first to see the current state."""
        return bridge.observe(screenshot=screenshot)

    @tool()
    def perceive(screenshot: bool = True) -> dict:
        """Detect on-screen UI elements (Windows UI Automation preferred, OCR fallback). Returns elements with id, type, text, bounds, and a click `center` [x,y]. Use this to find controls to click before acting."""
        return bridge.perceive(screenshot=screenshot)

    @tool()
    def screenshot() -> dict:
        """Capture a screenshot and return its file path (for vision-capable inspection)."""
        return bridge.screenshot()

    @tool()
    def click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> dict:
        """Click the mouse, optionally moving to absolute screen (x, y) first. button is left|right|middle. Omit x/y to click at the current cursor."""
        return bridge.click(x=x, y=y, button=button)

    @tool()
    def double_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> dict:
        """Double-click the mouse, optionally at absolute screen (x, y)."""
        return bridge.double_click(x=x, y=y, button=button)

    @tool()
    def right_click(x: Optional[int] = None, y: Optional[int] = None) -> dict:
        """Right-click the mouse, optionally at absolute screen (x, y) — opens context menus."""
        return bridge.right_click(x=x, y=y)

    @tool()
    def move(x: int, y: int) -> dict:
        """Move the cursor to absolute screen (x, y)."""
        return bridge.move(x, y)

    @tool()
    def scroll(dx: int = 0, dy: int = 0) -> dict:
        """Scroll the mouse wheel by (dx, dy) steps (positive dy scrolls up)."""
        return bridge.scroll(dx=dx, dy=dy)

    @tool()
    def drag(from_x: int, from_y: int, to_x: int, to_y: int, duration_ms: int = 600) -> dict:
        """Drag (press-move-release) from absolute (from_x, from_y) to (to_x, to_y). Use for moving icons, selecting ranges, rearranging windows."""
        return bridge.drag([from_x, from_y], [to_x, to_y], duration_ms=duration_ms)

    @tool()
    def type_text(text: str) -> dict:
        """Type literal text at the current keyboard focus (Unicode-safe, incl. Turkish)."""
        return bridge.type_text(text)

    @tool()
    def press_key(key: str) -> dict:
        """Press a single key by name, e.g. 'ENTER', 'TAB', 'ESC', 'F2', 'DOWN'."""
        return bridge.press_key(key)

    @tool()
    def hotkey(keys: list) -> dict:
        """Press a key combination, e.g. ['CTRL','S'] or ['WIN','R'] or ['ALT','TAB']."""
        return bridge.hotkey(keys)

    @tool()
    def clipboard_set(text: str) -> dict:
        """Set the clipboard text (useful before pasting with hotkey ['CTRL','V'])."""
        return bridge.clipboard_set(text)

    @tool()
    def clipboard_get() -> dict:
        """Read the current clipboard text back."""
        return bridge.clipboard_get()

    @tool()
    def wait(duration_ms: int) -> dict:
        """Wait for a fixed number of milliseconds (let a window open or settle before the next step)."""
        return bridge.wait(duration_ms)

    @tool()
    def run_tool(name: str, args: Optional[dict] = None) -> dict:
        """Run a reliable named tool instead of many fragile GUI steps. See list_tools for names/args. Includes create_text_file, open_app, open_url, focus_window, drag_drop, sketch."""
        return bridge.run_tool(name, args)

    @tool()
    def run_cli(command: str, cwd: Optional[str] = None, elevated: bool = True,
                timeout_ms: Optional[int] = None) -> dict:
        """Run a SHORT non-interactive command through the elevated, risk-classified, audited CLI broker. It BLOCKS until the command exits — never use it to launch GUI apps (use open_app). High-risk commands may be denied by policy. cwd must exist."""
        return bridge.run_cli(command, cwd=cwd, elevated=elevated, timeout_ms=timeout_ms)

    @tool()
    def act(action: dict) -> dict:
        """Escape hatch: execute any validated structured action as a dict, e.g. {"type":"mouse.click","x":10,"y":20} or {"type":"keyboard.hotkey","keys":["CTRL","A"]}. Malformed actions are rejected, not executed."""
        return bridge.act(action)

    @tool()
    def list_tools() -> dict:
        """List the reliable named tools available to run_tool, with their descriptions and argument hints."""
        return bridge.list_tools()

    @tool()
    def status() -> dict:
        """Report active backends, emergency-stop state, the audit log path, and the available tools."""
        return bridge.status()

    @tool()
    def emergency_stop(reason: str = "stop via MCP") -> dict:
        """Immediately halt all desktop actions. Every subsequent action is refused until clear_stop is called."""
        return bridge.emergency_stop(reason)

    @tool()
    def clear_stop() -> dict:
        """Clear a previously-set emergency stop so actions can resume."""
        return bridge.clear_stop()

    return server


def serve(bridge: AgentBridge, *, name: str = SERVER_NAME) -> None:
    """Build a FastMCP server, register the bridge tools, and serve over stdio.

    Imports the MCP SDK lazily and raises a clear :class:`RuntimeError` if it isn't
    installed. NOTE: in stdio mode stdout is the JSON-RPC channel — callers must
    print human-facing messages to stderr only.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:  # SDK not installed
        raise RuntimeError(
            'the MCP SDK is not installed; run `pip install -e ".[mcp]"` '
            "(or `pip install mcp`) to start the MCP server"
        ) from exc

    server = FastMCP(name)
    register(server, bridge)
    server.run()
