"""Tool registry and protocol (AI-callable reliable workflows)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class ToolError(RuntimeError):
    """Raised when a tool is unknown, mis-argued, or fails."""


@runtime_checkable
class Tool(Protocol):
    """A reliable named workflow the AI may call via a ``tool.run`` action.

    ``risk`` is the tool's declared risk level ("low" | "medium" | "high") used
    by the permission policy — a tool, not the planner, owns its risk.
    """

    name: str
    description: str
    args_help: str
    risk: str

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run the tool; return a dict containing at least ``success: bool``."""
        ...


class ToolRegistry:
    """A plain in-process name -> Tool map (no plugin discovery, by design)."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def risk_of(self, name: str) -> str:
        """Risk of a named tool; UNKNOWN tools are HIGH (deny-by-default)."""
        tool = self._tools.get(name)
        return tool.risk if tool is not None else "high"

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"name": t.name, "description": t.description, "args": t.args_help}
            for t in self._tools.values()
        ]

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run a tool by name. Raises ToolError for unknown tool or failure."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name!r}")
        if not isinstance(args, dict):
            raise ToolError(f"tool {name!r} args must be an object")
        result = tool.run(args)
        if not isinstance(result, dict) or not result.get("success"):
            raise ToolError(f"tool {name!r} failed: {(result or {}).get('error', 'unknown error')}")
        return result
