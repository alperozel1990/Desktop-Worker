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
                res = self._broker.launch(f'start "" notepad "{path}"', self._desktop_dir, agent="create_text_file", role="tool")
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
        res = self._broker.launch(f'start "" {token}', self._cwd, agent="open_app", role="tool")
        if getattr(res, "blocked", False):
            return {"success": False, "app": app,
                    "error": f"launch blocked: {getattr(res, 'blockedReason', '')}"}
        return {"success": True, "app": app, "launched": token, "error": None}


# http/https only. The URL is always passed INSIDE quotes (`start "" "<url>"`),
# where cmd only treats '"' and '%' specially — so we reject quotes, '%' (env
# expansion), whitespace and angle brackets; '&','?','=' etc. (query params) are
# safe inside quotes and allowed.
# SAFETY DEPENDS on the broker invoking cmd WITHOUT delayed expansion (no /V:ON):
# '!' is literal under the default `cmd /c`. If the broker ever enables /V:ON,
# '!VAR!' would become injectable and this regex would need to also reject '!'.
_SAFE_URL = re.compile(r'^https?://[^\s"%<>]+$', re.IGNORECASE)


def _sanitize_url(url: Any) -> str:
    url = str(url or "").strip()
    if not _SAFE_URL.match(url):
        raise ToolError(f"unsafe or non-http(s) url: {url!r}")
    return url


class OpenUrlTool:
    """Open an http(s) URL in the default browser (reliable, non-blocking).

    Only http/https URLs with a safe character set are allowed; the URL is
    launched via the audited broker's non-blocking `start`.
    """

    name = "open_url"
    description = "Open an http(s) web URL in the default browser (reliable)."
    args_help = "url (must start with http:// or https://)"
    risk = "medium"  # opens a browser to an AI-chosen URL; non-destructive

    def __init__(self, *, desktop_dir: str, broker: Any = None) -> None:
        self._cwd = desktop_dir
        self._broker = broker

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        url = _sanitize_url(args.get("url"))
        if self._broker is None:
            return {"success": False, "url": url, "error": "no broker to open the url"}
        res = self._broker.launch(f'start "" "{url}"', self._cwd, agent="open_url", role="tool")
        if getattr(res, "blocked", False):
            return {"success": False, "url": url,
                    "error": f"open blocked: {getattr(res, 'blockedReason', '')}"}
        return {"success": True, "url": url, "error": None}


class SketchTool:
    """Draw a complete figure in Paint from geometric primitives — reliable hands.

    The AI plans a whole figure ONCE as primitives on a 0..100 grid (the brain);
    this tool finds Paint's real canvas, tessellates each primitive into a precise
    stroke (smooth circles/curves), and draws them with the existing input backend
    (the reliable hands). One primitive == one stroke, so shapes never fuse into a
    stray connecting line. Emergency stop is honored before every stroke.
    """

    name = "sketch"
    description = ("Draw a complete figure in MS Paint from geometric primitives on a "
                  "0..100 grid (kinds: line, polyline, circle, ellipse, arc, bezier, dot; "
                  "origin top-left). Reliable + precise — use this instead of mouse "
                  "strokes for ANY drawing. Plan the whole figure in one call.")
    args_help = ("title (str), primitives (list of {kind, ...}); e.g. "
                "{kind:'circle',center:[50,40],r:22}, {kind:'polyline',points:[[33,22],"
                "[28,8],[42,26]],closed:true}, {kind:'dot',at:[50,46]}, "
                "{kind:'arc',center:[50,46],r:8,start:20,end:160}, "
                "{kind:'bezier',points:[[72,55],[92,60],[80,80]]}")
    risk = "low"  # synthesized mouse movement inside the focused window; non-destructive

    def __init__(self, *, input_backend: Any, canvas_locator: Any, estop: Any = None) -> None:
        self._input = input_backend
        self._locator = canvas_locator
        self._estop = estop

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        from desktop_worker.geometry import (apply_inner_margin, compile_program,
                                             fit_square, parse_program)
        from desktop_worker.safety.emergency_stop import EmergencyStopError

        program = parse_program(args)            # raises ToolError on bad input
        canvas = self._locator.locate()
        if canvas is None:
            return {"success": False, "error": "could not locate the drawing canvas "
                    "(is Paint the focused window?)"}

        # Draw into the largest centered SQUARE so the 0..100 grid keeps its aspect
        # ratio (circles stay round on a wide canvas), with a small margin so the
        # figure never crowds the ribbon/edges. Report the full canvas so the
        # critique screenshot can be cropped to the whole drawing area.
        draw_rect = apply_inner_margin(fit_square(canvas), 0.05)
        strokes = compile_program(program, draw_rect)
        drawn = total_points = 0
        for points in strokes:
            if self._estop is not None:
                try:
                    self._estop.check()
                except EmergencyStopError as exc:
                    return {"success": False, "error": f"emergency stop: {exc}",
                            "strokes": drawn, "canvas": list(canvas.as_tuple()),
                            "canvasSource": canvas.source}
            duration_ms = max(120, len(points) * 6)
            self._input.stroke(points, duration_ms)
            drawn += 1
            total_points += len(points)

        return {"success": True, "title": program.title,
                "primitives": len(program.primitives), "strokes": drawn,
                "points": total_points, "canvas": list(canvas.as_tuple()),
                "canvasSource": canvas.source, "error": None}


def _match_window(windows: list[tuple[int, str]], title_contains: str) -> tuple[int, str] | None:
    """Pure: first (hwnd, title) whose title contains the text (case-insensitive)."""
    want = title_contains.lower()
    for hwnd, title in windows:
        if title and want in title.lower():
            return hwnd, title
    return None


class FocusWindowTool:
    """Bring a window to the foreground by (part of) its title.

    The window matching is a pure function; the OS enumeration/focus calls are
    injectable so the tool is testable without a desktop.
    """

    name = "focus_window"
    description = "Bring an open window to the front by (part of) its title."
    args_help = "title_contains (text appearing in the window's title)"
    risk = "low"  # changes focus only; non-destructive

    def __init__(self, *, enum_windows: Any = None, focus: Any = None) -> None:
        self._enum = enum_windows or self._win_enum_windows
        self._focus = focus or self._win_focus

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        tc = str(args.get("title_contains", "")).strip()
        if not tc:
            raise ToolError("focus_window needs a non-empty title_contains")
        match = _match_window(list(self._enum()), tc)
        if match is None:
            return {"success": False, "error": f"no open window matching {tc!r}"}
        hwnd, title = match
        ok = self._focus(hwnd)
        return {"success": bool(ok), "title": title,
                "error": None if ok else "could not focus the window"}

    # --- Windows implementations (lazy ctypes) -------------------------
    def _win_enum_windows(self) -> list[tuple[int, str]]:
        try:
            import ctypes
        except Exception:
            return []
        u = ctypes.windll.user32
        out: list[tuple[int, str]] = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(hwnd, _l):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hwnd, b, n + 1)
                    out.append((hwnd, b.value))
            return True

        u.EnumWindows(EnumProc(cb), 0)
        return out

    def _win_focus(self, hwnd: int) -> bool:
        try:
            import ctypes
        except Exception:
            return False
        u = ctypes.windll.user32
        try:
            u.ShowWindow(hwnd, 9)            # SW_RESTORE (un-minimize)
            return bool(u.SetForegroundWindow(hwnd))
        except Exception:
            return False
