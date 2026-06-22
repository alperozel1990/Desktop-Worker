"""Broker-routed Claude text/vision calls for the DrawingDirector.

Reuses the same CLI-broker path as the planner (no raw subprocess, no API key):
the logged-in `claude` CLI is invoked through the audited broker with the prompt
delivered via stdin. Returns the raw ``result`` text from the JSON envelope (the
director wants SVG / a judge number, not a parsed action).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Tuple

from desktop_worker.loop.claude_cli_planner import (_CLAUDE_FLAGS, _CLAUDE_FLAGS_VISION,
                                                    _read_stdout)


def _result_text(raw: str) -> str:
    """Extract the `result` text from a `claude --output-format json` envelope."""
    try:
        env = json.loads(raw)
    except (ValueError, TypeError):
        return raw or ""
    if isinstance(env, dict):
        if env.get("is_error"):
            raise RuntimeError(f"claude error: {str(env.get('result'))[:200]}")
        return str(env.get("result", ""))
    return raw or ""


def make_claude_callers(broker, cwd: str, claude_path: str = "claude") -> Tuple[
        Callable[[str], str], Callable[[str, str], str]]:
    """Return (ask_text, ask_vision) bound to the broker. Both raise on failure."""

    def _call(prompt: str, *, vision: bool) -> str:
        cli_dir = Path(getattr(broker, "cli_dir", None) or cwd)
        try:
            cli_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            cli_dir = Path(cwd)
        fd, name = tempfile.mkstemp(suffix=".txt", prefix="dw_draw_", dir=str(cli_dir))
        os.close(fd)
        pf = Path(name)
        try:
            pf.write_text(prompt, encoding="utf-8")
            flags = _CLAUDE_FLAGS_VISION if vision else _CLAUDE_FLAGS
            command = f'{claude_path} {flags} < "{pf}"'
            res = broker.run(command, cwd, elevated=False, agent="DrawingDirector",
                             role="planner")
            if getattr(res, "blocked", False):
                raise RuntimeError(f"broker blocked the draw call: "
                                   f"{getattr(res, 'blockedReason', '')}")
            return _result_text(_read_stdout(res))
        finally:
            try:
                pf.unlink()
            except OSError:
                pass

    def ask_text(prompt: str) -> str:
        return _call(prompt, vision=False)

    def ask_vision(prompt: str, image_path: str) -> str:
        full = (f"{prompt}\n\nThe image to look at is saved at this path:\n{image_path}\n"
                "Use your Read tool to VIEW that image file, then answer.")
        return _call(full, vision=True)

    return ask_text, ask_vision
