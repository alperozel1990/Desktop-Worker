import pytest

from desktop_worker.schema.actions import (
    ActionValidationError,
    KNOWN_ACTION_TYPES,
    parse_action,
)


def test_parse_valid_mouse_move():
    a = parse_action({"type": "mouse.move", "x": 10, "y": 20})
    assert a.type == "mouse.move"
    assert a.params == {"x": 10, "y": 20}
    assert a.to_dict() == {"type": "mouse.move", "x": 10, "y": 20}


def test_unknown_type_rejected():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "mouse.teleport", "x": 1, "y": 2})


def test_missing_required_field_rejected():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "mouse.move", "x": 1})


def test_wrong_type_rejected():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "keyboard.type", "text": 123})


def test_unexpected_field_rejected():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "wait", "durationMs": 5, "bogus": 1})


def test_bool_is_not_int_for_coordinates():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "mouse.move", "x": True, "y": 2})


def test_cli_run_requires_cwd():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "cli.run", "command": "echo hi"})
    ok = parse_action({"type": "cli.run", "command": "echo hi", "cwd": "."})
    assert ok.params["cwd"] == "."


def test_hotkey_requires_nonempty_list():
    with pytest.raises(ActionValidationError):
        parse_action({"type": "keyboard.hotkey", "keys": []})
    ok = parse_action({"type": "keyboard.hotkey", "keys": ["CTRL", "L"]})
    assert ok.params["keys"] == ["CTRL", "L"]


def test_drag_points():
    a = parse_action({"type": "mouse.drag", "from": [0, 0], "to": [5, 5], "durationMs": 100})
    assert a.params["from"] == [0, 0]


def test_all_known_types_have_summary():
    for t in KNOWN_ACTION_TYPES:
        a = parse_action(_minimal(t))
        assert a.summary


def _minimal(t: str) -> dict:
    samples = {
        "mouse.move": {"x": 1, "y": 1},
        "mouse.moveRelative": {"dx": 1, "dy": 1},
        "mouse.click": {},
        "mouse.doubleClick": {},
        "mouse.rightClick": {},
        "mouse.down": {},
        "mouse.up": {},
        "mouse.scroll": {},
        "mouse.drag": {"from": [0, 0], "to": [1, 1]},
        "mouse.stroke": {"points": [[0, 0], [1, 1]]},
        "keyboard.type": {"text": "x"},
        "keyboard.press": {"key": "ENTER"},
        "keyboard.hotkey": {"keys": ["CTRL", "C"]},
        "clipboard.set": {"text": "x"},
        "clipboard.get": {},
        "window.focus": {"titleContains": "Chrome"},
        "wait": {"durationMs": 1},
        "cli.run": {"command": "echo hi", "cwd": "."},
        "tool.run": {"tool": "create_text_file"},
        "verify": {"visibleTextContains": "ok"},
    }
    return {"type": t, **samples[t]}
