"""External AI interface — Model Context Protocol server (Phase 8).

Lets ANY MCP-capable AI agent (another Claude session, Claude Desktop, Cursor, a
custom agent) drive Desktop-Worker as its "hands". The built-in Claude CLI planner
(`do`/`draw`) is no longer the only driver: an external agent becomes the planner
and Desktop-Worker exposes observe/perceive/act/tools/cli over MCP — with every
request still routed through the existing audited, emergency-stop-gated,
policy-checked executor.

Layout mirrors the rest of the package: a pure, dependency-free core
(:class:`AgentBridge` in ``bridge``) plus a thin SDK wrapper (``server``) that
imports the MCP SDK lazily. The package is named ``mcp_server`` (not ``mcp``) so it
never shadows the installed ``mcp`` SDK.
"""

from __future__ import annotations

from desktop_worker.mcp_server.bridge import AgentBridge, build_agent_bridge

__all__ = ["AgentBridge", "build_agent_bridge"]
