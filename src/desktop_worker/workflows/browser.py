"""Chrome navigation + form-fill workflow (requirements Phase 5).

Composes the Phase-5 browser story from structured actions (through the audited,
emergency-stop-gated executor) plus a UI-Automation locator:

* ``navigate``     focus the address bar (Ctrl+L), type a URL, press Enter.
* ``fill_field``   locate an input by (part of) its label, click it, type text.
* ``click_control``locate a button/link by name and click it.
* ``submit_form``  navigate (optional) → fill each field → click submit / Enter.

URLs are validated with the same safe-URL check the ``open_url`` tool uses.
The browser is launched through the audited CLI broker (no raw subprocess).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from desktop_worker.schema.actions import parse_action
from desktop_worker.tools.builtin import _sanitize_url
from desktop_worker.tools.registry import ToolError
from desktop_worker.workflows.browser_ui import SUBMIT_NAMES, BrowserUi, NullBrowserUi


@dataclass
class BrowserResult:
    success: bool
    action: str
    detail: str = ""
    steps: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "action": self.action,
                "detail": self.detail, "steps": list(self.steps), "error": self.error}

    def to_markdown(self) -> str:
        head = f"{'OK' if self.success else 'FAILED'}: {self.action}"
        body = "".join(f"\n  - {s}" for s in self.steps)
        tail = f"\n  error: {self.error}" if self.error else ""
        return f"{head} ({self.detail}){body}{tail}"


def _runner(executor, steps: list[str]):
    def do(action_dict: dict, label: str) -> bool:
        res = executor.execute(parse_action(action_dict))
        ok = getattr(res, "success", False)
        steps.append(f"{'ok' if ok else 'FAIL'}: {label}")
        return ok
    return do


def open_chrome(*, broker, cwd: str) -> BrowserResult:
    """Launch Chrome (detached) through the audited broker."""
    if broker is None:
        return BrowserResult(False, "open_chrome", error="no broker to launch Chrome")
    res = broker.launch('start "" chrome', cwd, agent="browser", role="workflow")
    if getattr(res, "blocked", False):
        return BrowserResult(False, "open_chrome",
                             error=f"launch blocked: {getattr(res, 'blockedReason', '')}")
    return BrowserResult(True, "open_chrome", detail="chrome", steps=["ok: launch chrome"])


def navigate(url: str, *, executor, sleep=None) -> BrowserResult:
    """Focus the address bar, type ``url``, and press Enter (URL is validated)."""
    import time

    nap = sleep or time.sleep
    steps: list[str] = []
    try:
        url = _sanitize_url(url)
    except ToolError as exc:
        return BrowserResult(False, "navigate", error=str(exc))

    do = _runner(executor, steps)
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "L"]}, "focus address bar")
    nap(0.1)
    if not do({"type": "keyboard.type", "text": url}, f"type {url}"):
        return BrowserResult(False, "navigate", detail=url, steps=steps,
                             error="could not type the URL")
    ok = do({"type": "keyboard.press", "key": "ENTER"}, "press ENTER")
    return BrowserResult(bool(ok), "navigate", detail=url, steps=steps,
                         error="" if ok else "could not submit the URL")


def fill_field(label: str, text: str, *, executor, ui: BrowserUi, sleep=None) -> BrowserResult:
    """Locate an input by (part of) its label, click it, and type ``text``."""
    import time

    nap = sleep or time.sleep
    steps: list[str] = []
    center = ui.edit_center((label,))
    if center is None:
        return BrowserResult(False, "fill_field", detail=label, steps=steps,
                             error=f"could not find input {label!r}")
    x, y = center
    do = _runner(executor, steps)
    do({"type": "mouse.click", "x": x, "y": y}, f"click {label!r}")
    nap(0.05)
    do({"type": "keyboard.hotkey", "keys": ["CTRL", "A"]}, "select existing")
    ok = do({"type": "keyboard.type", "text": str(text)}, f"type into {label!r}")
    return BrowserResult(bool(ok), "fill_field", detail=label, steps=steps,
                         error="" if ok else "could not type into the field")


def click_control(name: str, *, executor, ui: BrowserUi) -> BrowserResult:
    """Locate a button/link by name and click it."""
    steps: list[str] = []
    center = ui.button_center((name,))
    if center is None:
        return BrowserResult(False, "click_control", detail=name, steps=steps,
                             error=f"could not find control {name!r}")
    x, y = center
    ok = _runner(executor, steps)({"type": "mouse.click", "x": x, "y": y}, f"click {name!r}")
    return BrowserResult(bool(ok), "click_control", detail=name, steps=steps,
                         error="" if ok else "could not click the control")


def submit_form(fields: dict[str, str], *, executor, ui: BrowserUi,
                url: Optional[str] = None, submit_label: Optional[str] = None,
                sleep=None) -> BrowserResult:
    """Navigate (optional) → fill each field → click submit (or press Enter).

    ``fields`` maps an input label substring to the text to type.
    """
    import time

    nap = sleep or time.sleep
    steps: list[str] = []

    if url:
        nav = navigate(url, executor=executor, sleep=sleep)
        steps += nav.steps
        if not nav.success:
            return BrowserResult(False, "submit_form", detail="navigate", steps=steps,
                                 error=nav.error)
        nap(0.2)

    for label, text in fields.items():
        r = fill_field(label, text, executor=executor, ui=ui, sleep=sleep)
        steps += r.steps
        if not r.success:
            return BrowserResult(False, "submit_form", detail=label, steps=steps,
                                 error=r.error)

    if submit_label:
        r = click_control(submit_label, executor=executor, ui=ui)
        steps += r.steps
        if not r.success:
            # Fall back to a located generic submit control, then ENTER.
            r2 = click_control_any(SUBMIT_NAMES, executor=executor, ui=ui)
            steps += r2.steps
            if not r2.success:
                ok = _runner(executor, steps)(
                    {"type": "keyboard.press", "key": "ENTER"}, "press ENTER to submit")
                if not ok:
                    return BrowserResult(False, "submit_form", steps=steps,
                                         error="could not submit the form")
    else:
        ok = _runner(executor, steps)({"type": "keyboard.press", "key": "ENTER"},
                                      "press ENTER to submit")
        if not ok:
            return BrowserResult(False, "submit_form", steps=steps,
                                 error="could not submit the form")

    return BrowserResult(True, "submit_form", detail=f"{len(fields)} field(s)", steps=steps)


def click_control_any(names: tuple[str, ...], *, executor, ui: BrowserUi) -> BrowserResult:
    """Click the first button/link matching any of ``names``."""
    steps: list[str] = []
    center = ui.button_center(names)
    if center is None:
        return BrowserResult(False, "click_control", steps=steps,
                             error="no matching control")
    x, y = center
    ok = _runner(executor, steps)({"type": "mouse.click", "x": x, "y": y}, "click submit")
    return BrowserResult(bool(ok), "click_control", steps=steps,
                         error="" if ok else "could not click")
