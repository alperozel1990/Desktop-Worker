from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, deny_all
from desktop_worker.schema.actions import parse_action


def _executor(tmp_path, dry_run=False, estop=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=deny_all)
    backend = NullInputBackend()
    ex = ActionExecutor(
        audit=audit, policy=policy, input_backend=backend,
        estop=estop or EmergencyStop(), dry_run=dry_run,
    )
    return ex, backend, audit


def test_mouse_move_dispatches_to_backend(tmp_path):
    ex, backend, _ = _executor(tmp_path)
    res = ex.execute(parse_action({"type": "mouse.move", "x": 42, "y": 7}))
    assert res.success
    assert ("move", 42, 7) in backend.calls


def test_clipboard_roundtrip(tmp_path):
    ex, backend, _ = _executor(tmp_path)
    ex.execute(parse_action({"type": "clipboard.set", "text": "hi"}))
    res = ex.execute(parse_action({"type": "clipboard.get"}))
    assert res.detail["text"] == "hi"


def test_hotkey_dispatch(tmp_path):
    ex, backend, _ = _executor(tmp_path)
    ex.execute(parse_action({"type": "keyboard.hotkey", "keys": ["CTRL", "L"]}))
    assert ("hotkey", ("CTRL", "L")) in backend.calls


def test_dry_run_does_not_touch_backend(tmp_path):
    ex, backend, _ = _executor(tmp_path, dry_run=True)
    res = ex.execute(parse_action({"type": "mouse.move", "x": 1, "y": 1}))
    assert res.success
    assert res.detail.get("dryRun") is True
    assert backend.calls == []


def test_emergency_stop_blocks_execution(tmp_path):
    es = EmergencyStop()
    es.stop("halt")
    ex, backend, _ = _executor(tmp_path, estop=es)
    res = ex.execute(parse_action({"type": "mouse.move", "x": 1, "y": 1}))
    assert res.success is False
    assert "halted" in (res.error or "")
    assert backend.calls == []


def test_every_action_is_audited(tmp_path):
    ex, _, audit = _executor(tmp_path)
    ex.execute(parse_action({"type": "mouse.move", "x": 1, "y": 1}))
    events = [e["event"] for e in audit.read_all()]
    assert "action.executed" in events


def test_cli_run_without_broker_fails_cleanly(tmp_path):
    ex, _, _ = _executor(tmp_path)
    res = ex.execute(parse_action({"type": "cli.run", "command": "echo hi", "cwd": str(tmp_path)}))
    assert res.success is False
    assert "broker" in (res.error or "").lower()


def test_mouse_stroke_dispatches_points(tmp_path):
    ex, backend, _ = _executor(tmp_path)
    res = ex.execute(parse_action({"type": "mouse.stroke",
                                   "points": [[10, 10], [20, 30], [40, 5]], "durationMs": 50}))
    assert res.success
    calls = [c for c in backend.calls if c[0] == "stroke"]
    assert calls and calls[0][1] == ((10, 10), (20, 30), (40, 5))


def test_mouse_stroke_requires_two_points():
    from desktop_worker.schema.actions import ActionValidationError
    import pytest as _pt
    with _pt.raises(ActionValidationError):
        parse_action({"type": "mouse.stroke", "points": [[1, 1]]})   # need >= 2
