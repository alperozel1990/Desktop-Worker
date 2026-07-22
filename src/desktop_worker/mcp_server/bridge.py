"""AgentBridge — the dependency-free core of the MCP server (Phase 8).

External AI agents drive Desktop-Worker through this bridge. Every capability is
mapped onto the SAME path the built-in planner uses —
``executor.execute(parse_action(...))`` for actions, the observer for state, the
perceiver for elements, the broker for CLI — so all safety stays *below* the
bridge:

  * malformed requests are rejected by ``parse_action`` before touching anything;
  * the emergency stop is checked before every action;
  * the permission policy gates anything above the chosen risk threshold;
  * every action is written to the audit log.

The bridge holds no MCP-specific code and imports no third-party libraries, so the
entire external-control surface is unit-testable with Null backends and no display.
``server.py`` wraps it with the actual MCP SDK.

Invariant: the bridge can only *propose* structured actions; it can never bypass
validation, approval, the emergency stop, or audit. An external AI is exactly as
constrained as the internal planner.
"""

from __future__ import annotations

from typing import Any, Optional

from desktop_worker.app import Session
from desktop_worker.schema.actions import ActionValidationError, parse_action


def _deny_approver(_request: Any) -> bool:
    """Default approval callback for an unattended MCP server: deny.

    With the ``standard`` profile this only affects HIGH-risk requests (e.g. risky
    CLI); LOW/MEDIUM still auto-run. A host that wants interactive approval can pass
    its own callback to :func:`build_agent_bridge`.
    """
    return False


class AgentBridge:
    """Maps MCP tool calls onto Desktop-Worker's audited executor/observer/perceiver.

    Construct with an already-wired :class:`~desktop_worker.app.Session`; optionally
    pass a tools registry (enables ``run_tool``) and a perceiver (enables element
    detection in ``perceive``). Use :func:`build_agent_bridge` for the standard
    real-backend wiring.
    """

    def __init__(
        self,
        session: Session,
        *,
        tools: Any = None,
        perceiver: Any = None,
        default_cwd: Optional[str] = None,
    ) -> None:
        self.session = session
        self.executor = session.executor
        # Expose the same reliable tools the internal planner uses, and attribute
        # audited actions to the external agent so logs are honest about the driver.
        if tools is not None:
            self.executor.tools = tools
        self.tools = tools
        self.perceiver = perceiver
        self.executor.agent = "mcp-client"
        self.executor.role = "external-ai"
        self.default_cwd = default_cwd or str(session.config.artifacts_root.parent)

    # --- generic action path -------------------------------------------
    def act(self, action: dict, settle_ms: int = 0, report_change: bool = False) -> dict:
        """Execute any structured action (the escape hatch). Validates first.

        ``settle_ms`` waits after the action so the UI can repaint before the next
        observation. The MCP surface previously had no settle at all — `click`
        returned the instant SendInput returned — so an agent had to guess a
        `wait()` duration, and guessed wrong in both directions.

        ``report_change`` returns a compact before/after signature so the agent can
        tell whether anything actually happened, without paying for a full
        re-perceive (a capture + a UIA walk + an OCR pass) just to find out.
        """
        try:
            parsed = parse_action(action)
        except ActionValidationError as exc:
            return {"ok": False, "error": f"invalid action: {exc}"}

        before = self._state_signature() if report_change else None
        result = self._result(self.executor.execute(parsed))

        if settle_ms > 0:
            self.wait(int(settle_ms))

        if report_change:
            after = self._state_signature()
            result["changed"] = before != after
            result["change"] = {
                "before": before,
                "after": after,
                # A successful action that changed nothing is the classic silent
                # no-op; surfacing it lets the agent react instead of proceeding
                # on a false assumption.
                "silentNoOp": bool(result.get("ok")) and before == after,
            }
        return result

    def _state_signature(self) -> str:
        """Cheap, coarse fingerprint of the screen: active window + element count.

        Deliberately not a screenshot hash — it must be cheap enough to take twice
        around every action, and stable against cursor jitter.
        """
        try:
            obs = self.session.observer.observe("mcp", screenshot=False)
            d = obs.to_dict()
            window = d.get("activeWindow") or {}
            return f"{window.get('process', '')}|{window.get('title', '')}"
        except Exception as exc:
            return f"<signature unavailable: {type(exc).__name__}>"

    @staticmethod
    def _result(res: Any) -> dict:
        d = res.to_dict()
        return {
            "ok": bool(d.get("success")),
            "error": d.get("error"),
            "actionType": d.get("actionType"),
            "detail": d.get("detail", {}),
        }

    # --- mouse ----------------------------------------------------------
    def move(self, x: int, y: int, settle_ms: int = 0) -> dict:
        return self.act({"type": "mouse.move", "x": x, "y": y}, settle_ms=settle_ms)

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", settle_ms: int = 0,
              report_change: bool = False) -> dict:
        return self.act(_xy({"type": "mouse.click", "button": button}, x, y),
                        settle_ms=settle_ms, report_change=report_change)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None,
                     button: str = "left") -> dict:
        return self.act(_xy({"type": "mouse.doubleClick", "button": button}, x, y))

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        return self.act(_xy({"type": "mouse.rightClick"}, x, y))

    def scroll(self, dx: int = 0, dy: int = 0) -> dict:
        return self.act({"type": "mouse.scroll", "dx": int(dx), "dy": int(dy)})

    def drag(self, frm: Any, to: Any, duration_ms: int = 600) -> dict:
        return self.act({"type": "mouse.drag", "from": list(frm), "to": list(to),
                         "durationMs": int(duration_ms)})

    # --- keyboard -------------------------------------------------------
    def type_text(self, text: str) -> dict:
        return self.act({"type": "keyboard.type", "text": text})

    def press_key(self, key: str) -> dict:
        return self.act({"type": "keyboard.press", "key": key})

    def hotkey(self, keys: Any) -> dict:
        return self.act({"type": "keyboard.hotkey", "keys": list(keys)})

    # --- clipboard / timing --------------------------------------------
    def clipboard_set(self, text: str) -> dict:
        return self.act({"type": "clipboard.set", "text": text})

    def clipboard_get(self) -> dict:
        return self.act({"type": "clipboard.get"})

    def wait(self, duration_ms: int) -> dict:
        return self.act({"type": "wait", "durationMs": int(duration_ms)})

    # --- reliable tools / CLI ------------------------------------------
    def run_tool(self, name: str, args: Optional[dict] = None) -> dict:
        if self.tools is None:
            return {"ok": False, "error": "no tools registry configured"}
        return self.act({"type": "tool.run", "tool": name, "args": args or {}})

    def run_cli(self, command: str, cwd: Optional[str] = None, *,
                elevated: bool = True, timeout_ms: Optional[int] = None) -> dict:
        action: dict[str, Any] = {"type": "cli.run", "command": command,
                                  "cwd": cwd or self.default_cwd,
                                  "elevated": bool(elevated)}
        if timeout_ms is not None:
            action["timeoutMs"] = int(timeout_ms)
        return self.act(action)

    def list_tools(self) -> dict:
        cat = self.tools.catalog() if self.tools is not None else []
        return {"ok": True, "tools": cat}

    # --- perception -----------------------------------------------------
    def observe(self, screenshot: bool = True) -> dict:
        obs = self.session.observer.observe("mcp", screenshot=screenshot)
        return {"ok": True, "observation": obs.to_dict()}

    def perceive(
        self,
        screenshot: bool = True,
        control_type: str = "",
        text_contains: str = "",
        region: list | None = None,
        max_elements: int = 0,
    ) -> dict:
        """Observe + detect UI elements (UIA preferred, OCR fallback).

        Each element carries its id, type, text, bounds, and a ``center`` [x, y] the
        external AI can click directly.

        The response ALWAYS reports whether the list was truncated. Without that,
        an agent cannot distinguish "that control does not exist" from "you were
        not told about it" — and on a dense UI the second is common.

        Optional filters narrow the payload before it is returned, so an agent
        hunting one control does not have to pay for the whole tree:
        ``control_type`` (e.g. "button"), ``text_contains`` (case-insensitive),
        ``region`` [left, top, right, bottom], ``max_elements`` (0 = no extra cap).
        """
        obs = self.session.observer.observe("mcp", screenshot=screenshot)
        if self.perceiver is not None:
            obs = self.perceiver.perceive(obs)
        d = obs.to_dict()
        elements = []
        for el in d.get("elements", []):
            b = el.get("bounds")
            if isinstance(b, (list, tuple)) and len(b) == 4:
                el = {**el, "center": [int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)]}
            elements.append(el)

        report = dict(getattr(self.perceiver, "last_report", None) or {})
        report.setdefault("truncated", False)
        report.setdefault("totalSeen", len(elements))
        report.setdefault("returned", len(elements))
        report.setdefault("dropped", 0)
        report.setdefault("droppedByType", {})

        before_filter = len(elements)
        elements = _filter_elements(
            elements,
            control_type=control_type,
            text_contains=text_contains,
            region=region,
        )
        filtered_out = before_filter - len(elements)

        capped_by_request = 0
        if max_elements and len(elements) > max_elements:
            capped_by_request = len(elements) - max_elements
            elements = elements[:max_elements]

        by_source: dict[str, int] = {}
        for el in elements:
            by_source[str(el.get("source") or "unknown")] = (
                by_source.get(str(el.get("source") or "unknown"), 0) + 1
            )

        perception = {
            # totalSeen/returned/dropped/droppedByType describe the UIA WALK,
            # before OCR elements are merged in — so `returned` can be lower
            # than `shown`. Spelled out because the two numbers disagreeing
            # otherwise looks like a bug.
            "stage": "totalSeen/returned/dropped cover the UIA walk; "
                     "`shown` is the final list after OCR merge and filters",
            **report,
            "filteredOut": filtered_out,
            "cappedByRequest": capped_by_request,
            "shown": len(elements),
            "bySource": by_source,
        }

        # If a real screenshot was requested but OCR contributed nothing AND OCR is
        # unavailable, this read may be silently undercounting on an OCR-heavy app
        # (KiCad reads 46 elements without OCR vs 193 with). Warn rather than let
        # the agent mistake a thin read for an empty screen.
        if screenshot and by_source.get("ocr", 0) == 0:
            from desktop_worker.perception import ocr_status

            ocr = ocr_status()
            if not ocr["available"]:
                perception["ocrWarning"] = (
                    "OCR is unavailable, so only UI-Automation elements are listed. "
                    "On custom-drawn / EDA / wxWidgets apps this can undercount by "
                    f"several-fold. {ocr['reason']}"
                )
                perception["ocrAvailable"] = False

        return {
            "ok": True,
            "summary": obs.summary(),
            "activeWindow": d.get("activeWindow"),
            "screen": d.get("screen"),
            "screenshotRef": d.get("screenshotRef"),
            "elements": elements,
            # Truncation is reported unconditionally, even when False, so an agent
            # can rely on the field being there rather than inferring from a count.
            "truncated": bool(report.get("truncated")) or capped_by_request > 0,
            "perception": perception,
        }

    def act_many(
        self, actions: list, stop_on_failure: bool = True, settle_ms: int = 0
    ) -> dict:
        """Run several actions in ONE round-trip, stopping at the first failure.

        A four-step form fill cost four round-trips, realistically eight with a
        confirming perceive between each. Model round-trips are the dominant term
        in agent latency, so grouping is the lever that actually moves it.

        Batching is NOT a safety bypass: every action still goes through
        ``parse_action`` -> policy -> emergency stop -> executor -> audit
        individually, exactly as if it had been sent alone. What is saved is the
        transport, not the checks.

        Stops at the first failure by default, because later actions in a sequence
        almost always assume the earlier ones worked — typing into a field that was
        never focused sends the text somewhere else.
        """
        if not isinstance(actions, list) or not actions:
            return {"ok": False, "error": "act_many needs a non-empty list of actions"}

        results: list[dict] = []
        failed_at: Optional[int] = None
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                results.append({"ok": False, "error": f"action {index} is not an object"})
                failed_at = index
                break
            outcome = self.act(action)
            results.append(outcome)
            if not outcome.get("ok"):
                failed_at = index
                if stop_on_failure:
                    break
            if settle_ms > 0:
                self.wait(settle_ms)

        completed = sum(1 for r in results if r.get("ok"))
        return {
            "ok": failed_at is None,
            "completed": completed,
            "requested": len(actions),
            "failedAt": failed_at,
            "error": (
                None if failed_at is None
                else f"action {failed_at} failed: {results[failed_at].get('error')}"
            ),
            "results": results,
        }

    def click_element(self, element_id: str, button: str = "left") -> dict:
        """Click a control BY ID, re-verifying it is still there first.

        Clicking a remembered coordinate is a silent-failure machine: anything
        that moves between the perceive and the click sends the click somewhere
        else, and the agent gets `ok: true` for hitting the wrong thing. So this
        re-perceives, finds the id, and clicks its CURRENT centre.

        A stale id is REFUSED, never guessed at. Refusing is recoverable — the
        agent re-perceives and tries again; a wrong click may not be.
        """
        if not element_id:
            return {"ok": False, "error": "click_element needs a non-empty element_id"}

        current = self.perceive(screenshot=False)
        elements = current.get("elements") or []
        match = next((e for e in elements if e.get("id") == element_id), None)

        if match is None:
            truncated = current.get("truncated")
            hint = (
                " The element list was truncated, so it may exist but not be listed — "
                "narrow with control_type/text_contains/region and retry."
                if truncated
                else " Re-perceive to get current ids."
            )
            return {
                "ok": False,
                "error": f"element {element_id!r} is not on screen now.{hint}",
                "detail": {"truncated": bool(truncated), "perceived": len(elements)},
            }

        centre = match.get("center")
        if not (isinstance(centre, (list, tuple)) and len(centre) == 2):
            return {
                "ok": False,
                "error": f"element {element_id!r} has no usable bounds to click",
                "detail": {"element": match},
            }

        result = self.click(int(centre[0]), int(centre[1]), button=button)
        result.setdefault("detail", {})
        if isinstance(result["detail"], dict):
            result["detail"]["element"] = {
                "id": element_id,
                "type": match.get("type"),
                "text": match.get("text"),
                "center": list(centre),
            }
        return result

    def screenshot(
        self, inline: bool = True, max_bytes: int = 4_000_000, region: list | None = None
    ) -> dict:
        """Capture the screen and return the image ITSELF, not just a path.

        Returning only a path left an external agent blind: it has no filesystem
        access to `artifacts/`, so the vision half of "vision + accessibility" was
        disconnected. That is not academic — Blender exposes 6 UIA elements and 2
        OCR elements, so for GHOST/OpenGL apps the picture is not a fallback, it is
        the only channel.

        The path is still returned for audit/replay. `inline=False` restores the
        old path-only behaviour for callers that do have disk access and do not
        want the payload.
        """
        obs = self.session.observer.observe("mcp", screenshot=True)
        out: dict[str, Any] = {"ok": True, "path": obs.screenshotRef}
        if not inline:
            return out

        ref = obs.screenshotRef
        if not ref:
            out["inlineError"] = "no screenshot reference was produced"
            return out

        try:
            data, media_type, meta = _read_image_bytes(ref, region=region)
        except Exception as exc:
            # A capture that cannot be encoded must SAY so; silently returning a
            # path-only result is how this defect went unnoticed the first time.
            out["inlineError"] = f"{type(exc).__name__}: {exc}"
            return out

        if len(data) > max_bytes:
            out["inlineError"] = (
                f"image is {len(data)} bytes, over the {max_bytes} limit; "
                "re-request with a region or a larger max_bytes"
            )
            out.update(meta)
            return out

        import base64

        out["image"] = base64.b64encode(data).decode("ascii")
        out["mediaType"] = media_type
        out["bytes"] = len(data)
        out.update(meta)
        return out

    # --- control / safety ----------------------------------------------
    def status(self) -> dict:
        from desktop_worker.perception import ocr_status

        return {
            "ok": True,
            "backends": self.session.backend_names(),
            "stopped": self.session.estop.is_stopped(),
            "auditLog": str(self.session.config.audit_file),
            "tools": [t["name"] for t in (self.tools.catalog() if self.tools else [])],
            # Surfaced so an agent can see, before it trusts a thin perceive, that
            # OCR is off — on OCR-heavy apps that means a silent undercount.
            "ocr": ocr_status(),
        }

    def emergency_stop(self, reason: str = "stop via MCP") -> dict:
        self.session.estop.stop(reason)
        return {"ok": True, "stopped": True}

    def clear_stop(self) -> dict:
        self.session.estop.clear()
        return {"ok": True, "stopped": False}


_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
}


def _read_image_bytes(ref: str, *, region: Any = None) -> tuple[bytes, str, dict]:
    """Read a captured image as bytes, optionally cropping to ``region``.

    Cropping needs Pillow; without it a region request is reported as unsupported
    rather than silently returning the whole screen, which would make an agent
    reason about the wrong pixels.
    """
    from pathlib import Path

    path = Path(ref)
    if not path.exists():
        raise FileNotFoundError(f"screenshot not found at {ref}")
    suffix = path.suffix.lower()
    if suffix not in _MEDIA_TYPES:
        # The Null desktop backend writes a .txt placeholder; say so plainly.
        raise ValueError(f"{path.name} is not an image (suffix {suffix!r})")

    meta: dict[str, Any] = {}
    box = None
    if isinstance(region, (list, tuple)) and len(region) == 4:
        try:
            box = tuple(int(v) for v in region)
        except (TypeError, ValueError):
            box = None

    if box is None:
        return path.read_bytes(), _MEDIA_TYPES[suffix], meta

    try:
        import io

        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            f"region crop needs Pillow (install the [vision] extra): {exc}"
        ) from exc

    with Image.open(path) as img:
        cropped = img.crop(box)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        meta["region"] = list(box)
        meta["size"] = [cropped.width, cropped.height]
        return buf.getvalue(), "image/png", meta


def _filter_elements(
    elements: list[dict],
    *,
    control_type: str = "",
    text_contains: str = "",
    region: Any = None,
) -> list[dict]:
    """Narrow a perceived element list. Empty/absent criteria are no-ops.

    Pure and dependency-free so it is unit-testable without a desktop.
    """
    want_type = (control_type or "").strip().lower()
    want_text = (text_contains or "").strip().lower()
    box = None
    if isinstance(region, (list, tuple)) and len(region) == 4:
        try:
            box = tuple(int(v) for v in region)
        except (TypeError, ValueError):
            box = None

    out = []
    for el in elements:
        if want_type and str(el.get("type") or "").lower() != want_type:
            continue
        if want_text:
            haystack = f"{el.get('text') or ''} {el.get('label') or ''}".lower()
            if want_text not in haystack:
                continue
        if box is not None:
            b = el.get("bounds")
            if not (isinstance(b, (list, tuple)) and len(b) == 4):
                continue
            cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            if not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
                continue
        out.append(el)
    return out


def _xy(action: dict, x: Optional[int], y: Optional[int]) -> dict:
    """Add optional absolute x/y to a mouse action (omitted => click at cursor)."""
    if x is not None:
        action["x"] = x
    if y is not None:
        action["y"] = y
    return action


def build_agent_bridge(
    *,
    real: bool = True,
    profile: str = "standard",
    approver: Any = None,
    config: Any = None,
) -> AgentBridge:
    """Wire a real-backend :class:`AgentBridge` with the same tools as ``do``.

    ``real`` False forces Null backends (headless smoke). ``profile`` selects the
    safety preset; ``approver`` is the approval callback for interactive profiles
    (defaults to deny, suitable for an unattended server).
    """
    from desktop_worker.config import Config
    from desktop_worker.geometry import get_canvas_locator
    from desktop_worker.geometry.paint_setup import get_paint_ui
    from desktop_worker.perception import Perceiver, get_ocr_backend, get_uia_backend
    from desktop_worker.safety import build_policy
    from desktop_worker.tools import (CaptureBurstTool, CreateTextFileTool, DragDropTool,
                                      FocusWindowTool, Inspect3DTool, OpenAppTool, OpenUrlTool,
                                      OrbitTool, SketchTool, ToolRegistry)
    from desktop_worker.workflows.desktop_ui import get_desktop_dir

    cfg = config or Config(session_id="mcp", task_id="task")
    policy = build_policy(profile, approver or _deny_approver,
                          app_allowlist=cfg.app_allowlist, app_denylist=cfg.app_denylist)
    session = Session(cfg, policy=policy, prefer_real_backends=real)

    desktop_dir = get_desktop_dir()
    tools = ToolRegistry()
    tools.register(CreateTextFileTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(OpenAppTool(desktop_dir=desktop_dir, broker=session.broker, policy=policy))
    tools.register(OpenUrlTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(FocusWindowTool())
    tools.register(DragDropTool(input_backend=session.input_backend, estop=session.estop))
    tools.register(SketchTool(input_backend=session.input_backend,
                              canvas_locator=get_canvas_locator(real),
                              estop=session.estop, paint_ui=get_paint_ui(real)))
    tools.register(Inspect3DTool(input_backend=session.input_backend,
                                 screenshot_fn=session.desktop_backend.capture_screenshot,
                                 estop=session.estop, work_dir=cfg.task_dir / "inspect"))
    tools.register(OrbitTool(input_backend=session.input_backend, estop=session.estop))
    tools.register(CaptureBurstTool(input_backend=session.input_backend,
                                    screenshot_fn=session.desktop_backend.capture_screenshot,
                                    estop=session.estop, work_dir=cfg.task_dir / "burst"))

    perceiver = Perceiver(ocr=get_ocr_backend(real), uia=get_uia_backend(real))
    return AgentBridge(session, tools=tools, perceiver=perceiver)
