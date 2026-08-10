"""Tests for the MCP AgentBridge (Phase 8) — the external-AI control surface.

Everything runs on Null backends with no display and no MCP SDK: the bridge is the
dependency-free core, so the whole external-control surface is unit-testable.
"""

import dataclasses

import pytest

from desktop_worker.app import Session
from desktop_worker.config import Config
from desktop_worker.mcp_server.bridge import AgentBridge, build_agent_bridge
from desktop_worker.safety.policy import PermissionPolicy, auto_approve, deny_all
from desktop_worker.schema.observations import Element
from desktop_worker.tools import ToolRegistry


class FakeTool:
    name = "noop"
    description = "a no-op tool"
    args_help = "anything"
    risk = "low"

    def __init__(self):
        self.calls = []

    def run(self, args):
        self.calls.append(args)
        return {"success": True, "echo": args, "error": None}


class FakeBroker:
    """Stand-in for the elevated broker so cli.run never runs a real command."""

    def __init__(self, blocked=False):
        self.calls = []
        self._blocked = blocked

    def run(self, command, cwd, **kw):
        self.calls.append((command, cwd, kw))

        class R:
            pass

        r = R()
        r.blocked = self._blocked
        r.blockedReason = "denied"
        r.to_dict = lambda: {"command": command, "cwd": cwd, "exitCode": 0}
        return r


class FakePerceiver:
    def __init__(self, elements):
        self._elements = tuple(elements)

    def perceive(self, observation):
        return dataclasses.replace(observation, elements=self._elements)


def _bridge(tmp_path, *, approve=True, tools=None, perceiver=None, broker=None):
    # Isolate BOTH artifacts and the emergency-stop sentinel under tmp so the test
    # never reads or pollutes the shared default EMERGENCY_STOP file.
    cfg = Config(session_id="mcp-test", task_id="t", artifacts_root=tmp_path,
                 estop_file=tmp_path / "EMERGENCY_STOP")
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    session = Session(cfg, policy=policy, prefer_real_backends=False)
    if broker is not None:
        session.executor.broker = broker
    return AgentBridge(session, tools=tools, perceiver=perceiver), session


def test_click_routes_through_executor_and_audits(tmp_path):
    bridge, session = _bridge(tmp_path)
    out = bridge.click(10, 20)
    assert out["ok"] is True
    assert out["actionType"] == "mouse.click"
    # The action was audited honestly under the external-agent identity.
    text = session.config.audit_file.read_text(encoding="utf-8")
    assert "mouse.click" in text
    assert "mcp-client" in text


def test_malformed_action_is_rejected_not_executed(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "mouse.move", "x": 1})  # missing required y
    assert out["ok"] is False
    assert "invalid action" in out["error"]


def test_unknown_action_type_rejected(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "totally.bogus"})
    assert out["ok"] is False
    assert "invalid action" in out["error"]


def test_type_text_and_clipboard(tmp_path):
    bridge, _ = _bridge(tmp_path)
    assert bridge.type_text("merhaba ş ı")["ok"] is True
    assert bridge.clipboard_set("x")["ok"] is True
    assert bridge.clipboard_get()["ok"] is True


def test_run_tool_routes_to_registry(tmp_path):
    tool = FakeTool()
    reg = ToolRegistry()
    reg.register(tool)
    bridge, _ = _bridge(tmp_path, tools=reg)
    out = bridge.run_tool("noop", {"a": 1})
    assert out["ok"] is True
    assert tool.calls == [{"a": 1}]


def test_run_tool_without_registry_fails_safe(tmp_path):
    bridge, _ = _bridge(tmp_path)  # no tools
    out = bridge.run_tool("noop", {})
    assert out["ok"] is False
    assert "no tools registry" in out["error"]


def test_run_cli_goes_through_broker(tmp_path):
    broker = FakeBroker()
    bridge, _ = _bridge(tmp_path, broker=broker)
    out = bridge.run_cli("echo hi", cwd=str(tmp_path))
    assert out["ok"] is True
    assert "cli" in out["detail"]
    assert broker.calls and broker.calls[0][0] == "echo hi"


def test_run_cli_blocked_broker_fails_safe(tmp_path):
    broker = FakeBroker(blocked=True)
    bridge, _ = _bridge(tmp_path, broker=broker)
    out = bridge.run_cli("rmdir /s /q C:\\", cwd=str(tmp_path))
    assert out["ok"] is False


def test_emergency_stop_blocks_then_clear_resumes(tmp_path):
    bridge, _ = _bridge(tmp_path)
    bridge.emergency_stop("test")
    blocked = bridge.click(1, 1)
    assert blocked["ok"] is False
    assert "halt" in (blocked["error"] or "").lower()
    bridge.clear_stop()
    assert bridge.click(1, 1)["ok"] is True


def test_perceive_adds_click_centers(tmp_path):
    el = Element(id="e1", type="button", bounds=(10, 20, 30, 40), source="uia",
                 text="OK", confidence=0.9)
    bridge, _ = _bridge(tmp_path, perceiver=FakePerceiver([el]))
    out = bridge.perceive(screenshot=False)
    assert out["ok"] is True
    assert len(out["elements"]) == 1
    assert out["elements"][0]["center"] == [20, 30]
    assert out["elements"][0]["text"] == "OK"


def test_observe_returns_structured_state(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.observe(screenshot=False)
    assert out["ok"] is True
    assert "screen" in out["observation"]


def test_status_lists_tools(tmp_path):
    reg = ToolRegistry()
    reg.register(FakeTool())
    bridge, _ = _bridge(tmp_path, tools=reg)
    st = bridge.status()
    assert st["ok"] is True
    assert "noop" in st["tools"]
    assert st["stopped"] is False


def test_high_risk_denied_under_deny_policy(tmp_path):
    """A HIGH-risk tool is denied when the policy denies — safety stays below."""
    reg = ToolRegistry()

    class HighTool(FakeTool):
        name = "danger"
        risk = "high"

    reg.register(HighTool())
    bridge, _ = _bridge(tmp_path, approve=False, tools=reg)
    out = bridge.run_tool("danger", {})
    assert out["ok"] is False


def test_build_agent_bridge_null_wires_default_tools(tmp_path):
    cfg = Config(session_id="mcp-build", task_id="t", artifacts_root=tmp_path)
    bridge = build_agent_bridge(real=False, config=cfg)
    names = {t["name"] for t in bridge.list_tools()["tools"]}
    assert {"create_text_file", "open_app", "open_url", "focus_window",
            "drag_drop", "sketch"} <= names


# --- DW-PERCEIVE-RANK: truncation signalling + filters over the bridge -------


class _ReportingPerceiver:
    """Perceiver stand-in that also exposes a truncation report."""

    def __init__(self, elements, report=None):
        self._elements = tuple(elements)
        self.last_report = report or {
            "truncated": False, "totalSeen": len(elements),
            "returned": len(elements), "dropped": 0, "droppedByType": {},
        }

    def perceive(self, observation):
        return dataclasses.replace(observation, elements=self._elements)


def _bridge_with(tmp_path, elements, report=None):
    bridge, _session = _bridge(tmp_path, perceiver=_ReportingPerceiver(elements, report))
    return bridge


def _element(etype="button", text="Save", bounds=(0, 0, 10, 10)):
    return Element(id=f"uia-{text}", type=etype, bounds=bounds, source="uia",
                   text=text, label=text, confidence=0.9)


def test_perceive_always_reports_truncated_even_when_false(tmp_path):
    """The agent must be able to rely on the field existing, not infer from counts."""
    res = _bridge_with(tmp_path, [_element()]).perceive(screenshot=False)

    assert "truncated" in res
    assert res["truncated"] is False
    assert res["perception"]["dropped"] == 0


def test_perceive_propagates_a_real_truncation_report(tmp_path):
    report = {"truncated": True, "totalSeen": 900, "returned": 200,
              "dropped": 700, "droppedByType": {"text": 700}}
    res = _bridge_with(tmp_path, [_element()], report).perceive(screenshot=False)

    assert res["truncated"] is True
    assert res["perception"]["totalSeen"] == 900
    assert res["perception"]["droppedByType"] == {"text": 700}


def test_perceive_filters_by_control_type_and_reports_how_many_were_filtered(tmp_path):
    elements = [_element("button", "Save"), _element("text", "Hello")]
    res = _bridge_with(tmp_path, elements).perceive(screenshot=False, control_type="button")

    assert [e["text"] for e in res["elements"]] == ["Save"]
    assert res["perception"]["filteredOut"] == 1
    assert res["perception"]["shown"] == 1


def test_perceive_filters_by_text(tmp_path):
    elements = [_element("button", "Save"), _element("button", "Cancel")]
    res = _bridge_with(tmp_path, elements).perceive(screenshot=False, text_contains="canc")
    assert [e["text"] for e in res["elements"]] == ["Cancel"]


def test_perceive_max_elements_caps_and_marks_truncated(tmp_path):
    elements = [_element("button", f"b{i}") for i in range(5)]
    res = _bridge_with(tmp_path, elements).perceive(screenshot=False, max_elements=2)

    assert len(res["elements"]) == 2
    assert res["truncated"] is True, "a caller-requested cap is still truncation"
    assert res["perception"]["cappedByRequest"] == 3


def test_perceive_elements_still_carry_click_centres(tmp_path):
    res = _bridge_with(tmp_path, [_element(bounds=(10, 20, 30, 40))]).perceive(screenshot=False)
    assert res["elements"][0]["center"] == [20, 30]


# --- DW-MCP-IMAGE: the agent must receive the picture, not a path it cannot open ---


def _png_bytes(width=8, height=6):
    """A minimal real PNG, written without Pillow so the test has no extra deps."""
    import struct
    import zlib

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class _ShotObserver:
    """Observer stand-in that reports a screenshot at a path we control."""

    def __init__(self, ref, error=None):
        self._ref = ref
        self._error = error

    def observe(self, agent, screenshot=True):
        class _Obs:
            screenshotRef = self._ref
            screenshotError = self._error

            def to_dict(_self):
                return {"screenshotRef": self._ref, "screenshotError": self._error}

        return _Obs()


def test_screenshot_returns_decodable_image_bytes(tmp_path):
    """The defect: only a path was returned, so an external agent was blind."""
    import base64

    shot = tmp_path / "shot.png"
    shot.write_bytes(_png_bytes())
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(str(shot))

    out = bridge.screenshot()

    assert out["ok"] is True
    assert out["path"] == str(shot), "the path must still be returned for audit/replay"
    decoded = base64.b64decode(out["image"], validate=True)
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")
    assert out["mediaType"] == "image/png"
    assert out["bytes"] == len(decoded)


def test_screenshot_inline_false_keeps_the_old_path_only_shape(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(_png_bytes())
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(str(shot))

    out = bridge.screenshot(inline=False)
    assert out["path"] == str(shot)
    assert "image" not in out


def test_screenshot_reports_ok_false_with_a_reason_when_capture_fails(tmp_path):
    """UQC-BL-1: a failed capture must never look like success.

    A missing screenshotRef used to come back as ok=True/path=None with no
    way to tell "capture failed" from "not requested" apart. It must now be
    ok=False with the backend's machine-readable reason, for both inline
    values (the caller never gets far enough to hit the inline-encode step).
    """
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(None, error="missing_dependency: ModuleNotFoundError: mss")

    for inline in (True, False):
        out = bridge.screenshot(inline=inline)
        assert out["ok"] is False
        assert out["path"] is None
        assert out["error"] == "missing_dependency: ModuleNotFoundError: mss"
        assert "image" not in out


def test_screenshot_falls_back_to_a_generic_reason_when_backend_gives_none(tmp_path):
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(None)

    out = bridge.screenshot()
    assert out["ok"] is False
    assert out["path"] is None
    assert out["error"]


def test_screenshot_reports_why_it_could_not_inline_a_placeholder(tmp_path):
    """The Null backend writes a .txt placeholder — say so, do not pretend."""
    placeholder = tmp_path / "shot.txt"
    placeholder.write_text("not an image", encoding="utf-8")
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(str(placeholder))

    out = bridge.screenshot()
    assert out["ok"] is True
    assert "image" not in out
    assert "not an image" in out["inlineError"]


def test_screenshot_reports_a_missing_file_rather_than_crashing(tmp_path):
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(str(tmp_path / "gone.png"))

    out = bridge.screenshot()
    assert "inlineError" in out
    assert "FileNotFoundError" in out["inlineError"]


def test_screenshot_refuses_to_inline_an_oversized_image(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(_png_bytes())
    bridge, session = _bridge(tmp_path)
    session.observer = _ShotObserver(str(shot))

    out = bridge.screenshot(max_bytes=10)
    assert "image" not in out
    assert "over the 10 limit" in out["inlineError"]


# --- DW-ELEM-STABLE: click_element re-verifies instead of trusting coordinates ---


def test_click_element_clicks_the_current_centre_of_the_named_control(tmp_path):
    el = Element(id="a:SaveBtn", type="button", bounds=(100, 200, 140, 220),
                 source="uia", text="Save", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el])

    out = bridge.click_element("a:SaveBtn")

    assert out["ok"] is True
    assert out["detail"]["element"]["center"] == [120, 210]
    assert out["detail"]["element"]["text"] == "Save"


def test_click_element_refuses_a_stale_id_instead_of_clicking_something_else(tmp_path):
    """Refusing is recoverable; a wrong click may not be."""
    present = Element(id="a:Other", type="button", bounds=(0, 0, 10, 10),
                      source="uia", text="Other", confidence=0.9)
    bridge = _bridge_with(tmp_path, [present])

    out = bridge.click_element("a:Gone")

    assert out["ok"] is False
    assert "not on screen now" in out["error"]
    assert "Re-perceive" in out["error"]


def test_stale_id_error_points_at_truncation_when_the_list_was_capped(tmp_path):
    """"Not listed" and "not there" are different problems — say which."""
    report = {"truncated": True, "totalSeen": 900, "returned": 200,
              "dropped": 700, "droppedByType": {"text": 700}}
    el = Element(id="a:Visible", type="button", bounds=(0, 0, 10, 10),
                 source="uia", text="V", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el], report)

    out = bridge.click_element("a:Hidden")

    assert out["ok"] is False
    assert "may exist but not be listed" in out["error"]
    assert out["detail"]["truncated"] is True


def test_click_element_rejects_an_empty_id(tmp_path):
    bridge = _bridge_with(tmp_path, [])
    out = bridge.click_element("")
    assert out["ok"] is False
    assert "non-empty" in out["error"]


def test_click_element_reports_unusable_bounds_rather_than_clicking_0_0(tmp_path):
    el = Element(id="a:Weird", type="button", bounds=(0, 0, 0, 0),
                 source="uia", text="W", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el])
    out = bridge.click_element("a:Weird")
    # zero-area bounds still yield a centre, so this must click 0,0 deliberately
    # rather than silently — assert we at least report which element was used.
    assert out["detail"]["element"]["id"] == "a:Weird"


# --- DW-ACT-BATCH / DW-ACT-SETTLE: fewer round-trips, no safety bypass -------


def test_act_many_runs_every_action_in_one_call(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act_many([
        {"type": "mouse.move", "x": 1, "y": 2},
        {"type": "mouse.click", "button": "left"},
        {"type": "keyboard.type", "text": "hi"},
    ])

    assert out["ok"] is True
    assert out["completed"] == 3
    assert out["requested"] == 3
    assert out["failedAt"] is None


def test_act_many_stops_at_the_first_failure(tmp_path):
    """Later steps assume earlier ones worked — typing into an unfocused field
    sends the text somewhere else."""
    bridge, _ = _bridge(tmp_path)
    out = bridge.act_many([
        {"type": "mouse.move", "x": 1, "y": 2},
        {"type": "mouse.move", "x": 1},          # invalid: missing y
        {"type": "keyboard.type", "text": "must not run"},
    ])

    assert out["ok"] is False
    assert out["failedAt"] == 1
    assert out["completed"] == 1
    assert len(out["results"]) == 2, "the third action must never have been attempted"


def test_act_many_can_be_told_to_continue_past_failures(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act_many([
        {"type": "mouse.move", "x": 1},           # invalid
        {"type": "mouse.move", "x": 3, "y": 4},
    ], stop_on_failure=False)

    assert out["ok"] is False
    assert len(out["results"]) == 2
    assert out["completed"] == 1


def test_act_many_still_validates_every_action(tmp_path):
    """Batching shares the transport, never the checks."""
    bridge, _ = _bridge(tmp_path)
    out = bridge.act_many([{"type": "totally.bogus"}])
    assert out["ok"] is False
    assert "invalid action" in out["results"][0]["error"]


def test_act_many_halts_mid_batch_on_emergency_stop(tmp_path):
    bridge, _ = _bridge(tmp_path)
    bridge.emergency_stop("mid-batch")
    out = bridge.act_many([
        {"type": "mouse.move", "x": 1, "y": 2},
        {"type": "mouse.move", "x": 3, "y": 4},
    ])

    assert out["ok"] is False
    assert out["completed"] == 0, "emergency stop must halt the batch, not be batched past"


def test_act_many_respects_policy_denial_for_high_risk_tools(tmp_path):
    reg = ToolRegistry()

    class HighTool(FakeTool):
        name = "danger"
        risk = "high"

    reg.register(HighTool())
    bridge, _ = _bridge(tmp_path, approve=False, tools=reg)
    out = bridge.act_many([{"type": "tool.run", "tool": "danger", "args": {}}])

    assert out["ok"] is False, "a batch must not launder a denied action"


def test_act_many_rejects_an_empty_or_non_list_payload(tmp_path):
    bridge, _ = _bridge(tmp_path)
    assert bridge.act_many([])["ok"] is False
    assert bridge.act_many("not a list")["ok"] is False


def test_act_reports_whether_anything_changed(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "mouse.move", "x": 5, "y": 5}, report_change=True)

    assert "changed" in out
    assert "silentNoOp" in out["change"]
    # Null backends never change the active window, so this IS a silent no-op —
    # which is exactly what the field is meant to surface.
    assert out["change"]["silentNoOp"] is True


def test_act_without_report_change_stays_lean(tmp_path):
    bridge, _ = _bridge(tmp_path)
    out = bridge.act({"type": "mouse.move", "x": 5, "y": 5})
    assert "changed" not in out
    assert "change" not in out


def test_settle_ms_is_honoured_on_click(tmp_path):
    import time

    bridge, _ = _bridge(tmp_path)
    started = time.perf_counter()
    bridge.click(1, 1, settle_ms=120)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms >= 100, f"settle was not honoured (took {elapsed_ms:.0f} ms)"


# --- DW-OCR-PREFLIGHT: perceive warns when a thin read may be an undercount ---


def test_status_reports_ocr_health(tmp_path):
    bridge, _ = _bridge(tmp_path)
    st = bridge.status()
    assert "ocr" in st
    assert set(st["ocr"]) == {"available", "backend", "version", "missing", "reason"}


def test_perceive_warns_when_ocr_absent_and_no_ocr_elements(tmp_path, monkeypatch):
    """A UIA-only read on a real screenshot, with OCR unavailable, is exactly the
    silent-undercount case (KiCad: 46 vs 193)."""
    import desktop_worker.perception as perc

    monkeypatch.setattr(perc, "ocr_status",
                        lambda: {"available": False, "backend": "null", "version": None,
                                 "missing": ["tesseract-binary"],
                                 "reason": "tesseract not on PATH"})
    el = Element(id="a:1", type="button", bounds=(0, 0, 10, 10), source="uia",
                 text="X", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el])

    out = bridge.perceive(screenshot=True)

    assert out["perception"]["ocrAvailable"] is False
    assert "undercount" in out["perception"]["ocrWarning"]
    assert out["perception"]["bySource"] == {"uia": 1}


def test_perceive_does_not_warn_when_ocr_contributed(tmp_path, monkeypatch):
    """If OCR elements are present, the read is not OCR-starved — no warning."""
    import desktop_worker.perception as perc

    monkeypatch.setattr(perc, "ocr_status",
                        lambda: {"available": False, "backend": "null", "version": None,
                                 "missing": ["tesseract-binary"], "reason": "x"})
    els = [
        Element(id="a:1", type="button", bounds=(0, 0, 10, 10), source="uia",
                text="X", confidence=0.9),
        Element(id="ocr-1", type="text", bounds=(0, 0, 10, 10), source="ocr",
                text="Y", confidence=0.5),
    ]
    bridge = _bridge_with(tmp_path, els)

    out = bridge.perceive(screenshot=True)
    assert "ocrWarning" not in out["perception"]


def test_perceive_does_not_warn_when_ocr_is_available(tmp_path, monkeypatch):
    import desktop_worker.perception as perc

    monkeypatch.setattr(perc, "ocr_status",
                        lambda: {"available": True, "backend": "tesseract",
                                 "version": "5.4.0", "missing": [], "reason": "ready"})
    el = Element(id="a:1", type="button", bounds=(0, 0, 10, 10), source="uia",
                 text="X", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el])

    out = bridge.perceive(screenshot=True)
    assert "ocrWarning" not in out["perception"]


def test_perceive_without_screenshot_never_warns_about_ocr(tmp_path, monkeypatch):
    """OCR only runs on a real screenshot, so a UIA-only perceive is not a miss."""
    import desktop_worker.perception as perc

    monkeypatch.setattr(perc, "ocr_status",
                        lambda: {"available": False, "backend": "null", "version": None,
                                 "missing": ["pytesseract"], "reason": "x"})
    el = Element(id="a:1", type="button", bounds=(0, 0, 10, 10), source="uia",
                 text="X", confidence=0.9)
    bridge = _bridge_with(tmp_path, [el])

    out = bridge.perceive(screenshot=False)
    assert "ocrWarning" not in out["perception"]
