"""Built-in tools. One MVP tool: create a desktop text file (reliable).

A tool is the AI's "reliable hands": it must GUARANTEE its result, not mimic a
flaky GUI. So `create_text_file` writes the file's content directly and verifies
it on disk (100% reliable for the content — the whole point of a tool), then
opens it in Notepad through the audited CLI broker so the user still SEES it.
The flaky right-click→New→Text Document GUI dance stays in the separate, watch-it
`create-file` demo; a tool the AI relies on should not be flaky.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from desktop_worker.tools.registry import ToolError

# AI-supplied args are UNTRUSTED. A filename must be a bare name (no path
# separators, no traversal, no drive) so it can only land on the desktop.
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|]{1,80}$")
_MAX_CONTENT = 20_000


def _sanitize_filename(name: Any) -> str:
    name = str(name or "ai-file").strip()
    if name.lower().endswith(".txt"):
        name = name[:-4]
    if ".." in name or not _SAFE_NAME.match(name):
        raise ToolError(f"unsafe filename: {name!r} (must be a bare name, no path)")
    return name


class CreateTextFileTool:
    """Create a text file on the desktop with given content, reliably + visibly.

    Writes the content to disk (guaranteed/verified), then opens it in Notepad via
    the broker (non-blocking, audited) so the user sees the result.
    """

    name = "create_text_file"
    description = ("Create a text file on the user's Desktop with given content and "
                  "open it (RELIABLE — use this instead of manual file-creation steps).")
    args_help = "filename (bare name, no path), content (text)"
    risk = "medium"  # writes a file + opens an app; non-destructive, scoped

    def __init__(self, *, desktop_dir: str, broker: Any = None) -> None:
        self._desktop_dir = desktop_dir
        self._broker = broker

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        filename = _sanitize_filename(args.get("filename"))
        content = str(args.get("content", ""))
        if len(content) > _MAX_CONTENT:
            raise ToolError(f"content too long ({len(content)} > {_MAX_CONTENT})")

        path = Path(self._desktop_dir) / f"{filename}.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"success": False, "path": str(path), "error": f"write failed: {exc}"}

        # Verify on disk — never claim success unless the bytes match.
        try:
            ok = path.read_text(encoding="utf-8") == content
        except OSError:
            ok = False
        if not ok:
            return {"success": False, "path": str(path), "error": "content verification failed"}

        opened = False
        if self._broker is not None:
            # `start` launches Notepad detached (non-blocking) and is audited by
            # the broker; best-effort — the file already exists either way.
            try:
                res = self._broker.run(f'start "" notepad "{path}"', self._desktop_dir,
                                       elevated=False, agent="create_text_file", role="tool")
                opened = not getattr(res, "blocked", False)
            except Exception:
                opened = False

        return {"success": True, "path": str(path), "opened": opened, "error": None}


# Curated allowlist of safe GUI apps the AI may open (friendly name -> launch
# token for `start "" <token>`). Shells (cmd/powershell) are deliberately EXCLUDED
# — the AI has the gated cli.run path for commands. Unknown apps are rejected, so
# the AI cannot launch an arbitrary executable through this tool.
_APP_ALLOWLIST = {
    "notepad": "notepad",
    "calculator": "calc", "calc": "calc",
    "paint": "mspaint", "mspaint": "mspaint",
    "explorer": "explorer", "file explorer": "explorer", "files": "explorer",
    "settings": "ms-settings:",
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "microsoft edge": "msedge",
    "task manager": "taskmgr",
    "wordpad": "write",
}


class OpenAppTool:
    """Open a known, safe GUI application by friendly name (reliable, non-blocking).

    Only apps in a curated allowlist can be opened (no arbitrary executables, no
    shells). Launches via the audited CLI broker's non-blocking `start`.
    """

    name = "open_app"
    description = ("Open a known Windows app by name (reliable). Allowed: "
                  + ", ".join(sorted(set(_APP_ALLOWLIST))) + ".")
    args_help = "app (one of the allowed names above)"
    risk = "medium"  # launches a known GUI app; non-destructive

    def __init__(self, *, desktop_dir: str, broker: Any = None) -> None:
        self._cwd = desktop_dir
        self._broker = broker

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        app = str(args.get("app", "")).strip().lower()
        token = _APP_ALLOWLIST.get(app)
        if token is None:
            raise ToolError(f"app not allowed: {args.get('app')!r}. "
                            f"Allowed: {', '.join(sorted(set(_APP_ALLOWLIST)))}")
        if self._broker is None:
            return {"success": False, "app": app, "error": "no broker to launch the app"}
        res = self._broker.run(f'start "" {token}', self._cwd, elevated=False,
                               agent="open_app", role="tool")
        if getattr(res, "blocked", False):
            return {"success": False, "app": app,
                    "error": f"launch blocked: {getattr(res, 'blockedReason', '')}"}
        return {"success": True, "app": app, "launched": token, "error": None}
