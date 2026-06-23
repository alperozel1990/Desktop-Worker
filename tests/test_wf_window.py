"""Tests for the window switching + drag-and-drop workflow (Phase 5)."""

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve, deny_all
from desktop_worker.tools import ToolRegistry
from desktop_worker.tools.builtin import DragDropTool
from desktop_worker.tools.registry import ToolError
from desktop_worker.workflows import drag_drop, switch_window


def _executor(tmp_path, approve=True, estop=None, input_backend=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    ib = input_backend or NullInputBackend()
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=ib,
                        estop=estop or EmergencyStop())
    return ex, ib, audit


# --- switch_window --------------------------------------------------------

def test_switch_window_focuses_matching_window():
    focused = []
    windows = [(1, "Untitled - Notepad"), (2, "Calculator")]
    res = switch_window("calc", enum_windows=lambda: windows,
                        focus=lambda hwnd: focused.append(hwnd) or True)
    assert res.success
    assert focused == [2]
    assert "Calculator" in res.steps[0]


def test_switch_window_no_match_fails_safe():
    res = switch_window("nonexistent", enum_windows=lambda: [(1, "Notepad")],
                        focus=lambda hwnd: True)
    assert not res.success
    assert res.error


def test_switch_window_empty_title():
    res = switch_window("   ", enum_windows=lambda: [], focus=lambda h: True)
    assert not res.success
    assert "empty" in res.error


# --- drag_drop (workflow, executor path) ----------------------------------

def test_drag_drop_emits_audited_mouse_drag(tmp_path):
    ex, ib, _ = _executor(tmp_path)
    res = drag_drop((10, 20), (110, 220), executor=ex, duration_ms=500)
    assert res.success
    assert ("drag", 10, 20, 110, 220, 500) in ib.calls


def test_drag_drop_blocked_when_denied(tmp_path):
    ex, ib, _ = _executor(tmp_path, approve=False)
    res = drag_drop((0, 0), (5, 5), executor=ex)
    # mouse.drag is low-risk so it is auto-allowed even under deny_all (below
    # the approval threshold); the action still reaches the backend.
    assert ("drag", 0, 0, 5, 5, 600) in ib.calls
    assert res.success


# --- DragDropTool (AI-callable, input-backend path) -----------------------

def test_drag_drop_tool_drags_via_backend():
    ib = NullInputBackend()
    tool = DragDropTool(input_backend=ib)
    out = tool.run({"from": [1, 2], "to": [3, 4], "durationMs": 200})
    assert out["success"]
    assert ("drag", 1, 2, 3, 4, 200) in ib.calls


def test_drag_drop_tool_rejects_bad_point():
    tool = DragDropTool(input_backend=NullInputBackend())
    try:
        tool.run({"from": [1], "to": [3, 4]})
        assert False, "expected ToolError"
    except ToolError:
        pass


def test_drag_drop_tool_honors_estop():
    es = EmergencyStop()
    es.stop("test")
    ib = NullInputBackend()
    out = DragDropTool(input_backend=ib, estop=es).run({"from": [0, 0], "to": [1, 1]})
    assert not out["success"]
    assert ib.calls == []


def test_drag_drop_tool_registered_low_risk():
    r = ToolRegistry()
    r.register(DragDropTool(input_backend=NullInputBackend()))
    assert r.risk_of("drag_drop") == "low"
