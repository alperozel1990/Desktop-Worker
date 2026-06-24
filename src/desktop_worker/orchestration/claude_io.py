"""Broker-routed Claude calls for orchestration roles (Phase 6).

Same audited CLI-broker path as the planner/director (no API key, no raw
subprocess): the logged-in ``claude`` CLI is invoked through the broker with the
prompt delivered via stdin. ``make_role_ask`` parameterizes the audit
attribution (``agent``/``role``) so each orchestration actor is distinguishable
in the audit trail. ``load_json`` robustly extracts the first JSON value from a
model response so a chatty answer still parses (or fails safe).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from desktop_worker.drawing.claude_io import _result_text
from desktop_worker.loop.claude_cli_planner import _CLAUDE_FLAGS, _read_stdout


def make_role_ask(broker, cwd: str, *, agent: str, role: str,
                  claude_path: str = "claude") -> Callable[[str], str]:
    """Return an ``ask(prompt) -> str`` bound to the broker for one role."""

    def ask(prompt: str) -> str:
        cli_dir = Path(getattr(broker, "cli_dir", None) or cwd)
        try:
            cli_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            cli_dir = Path(cwd)
        fd, name = tempfile.mkstemp(suffix=".txt", prefix="dw_orch_", dir=str(cli_dir))
        os.close(fd)
        pf = Path(name)
        try:
            pf.write_text(prompt, encoding="utf-8")
            command = f'{claude_path} {_CLAUDE_FLAGS} < "{pf}"'
            res = broker.run(command, cwd, elevated=False, agent=agent, role=role)
            if getattr(res, "blocked", False):
                raise RuntimeError(f"broker blocked the {role} call: "
                                   f"{getattr(res, 'blockedReason', '')}")
            return _result_text(_read_stdout(res))
        finally:
            try:
                pf.unlink()
            except OSError:
                pass

    return ask


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line and a trailing fence
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip()


def load_json(raw: str) -> Any:
    """Extract the first JSON object/array from a model response.

    Tries a direct decode, then scans for the first balanced ``{...}`` or
    ``[...]``. Raises ``ValueError`` if nothing decodes (callers fail safe).
    """
    text = _strip_fences(raw or "")
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Single forward pass: at each { or [, let the decoder consume one value
    # (raw_decode advances past it in O(n)) — no quadratic reverse-shrink scan.
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _end = decoder.raw_decode(text, i)
                return obj
            except ValueError:
                continue
    raise ValueError("no JSON value found in model response")
