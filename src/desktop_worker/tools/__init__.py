"""Tools: reliable named workflows the AI agent may CHOOSE to call.

"AI brain + reliable hands": the live AI planner can invoke a deterministic,
verified workflow (a tool) in one step instead of improvising many fragile GUI
actions — fewer model calls (cheaper) and more reliable for known tasks. Raw
primitive actions remain fully available for everything else; the AI decides.

Every tool expands into schema-validated, emergency-stop-checked, audited
primitive actions — a tool is a *gated capability*, not a privileged side path.
"""

from desktop_worker.tools.registry import Tool, ToolRegistry, ToolError
from desktop_worker.tools.builtin import CreateTextFileTool, OpenAppTool, OpenUrlTool

__all__ = ["Tool", "ToolRegistry", "ToolError",
           "CreateTextFileTool", "OpenAppTool", "OpenUrlTool"]
