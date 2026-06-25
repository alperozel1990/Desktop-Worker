"""Tests for the Chrome navigation + form-fill workflow (Phase 5)."""

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from types import SimpleNamespace

from desktop_worker.workflows import (
    click_control,
    ensure_foreground,
    fill_field,
    navigate,
    open_chrome,
    submit_form,
)
from desktop_worker.workflows.browser_ui import NullBrowserUi, get_browser_ui


class FakeBrowserUi:
    def __init__(self, edit=(40, 60), button=(120, 200)):
        self._edit = edit
        self._button = button

    def edit_center(self, names, timeout=2.0):
        return self._edit

    def button_center(self, names, timeout=2.0):
        return self._button


class FakeBroker:
    def __init__(self, blocked=False):
        self.commands = []
        self._blocked = blocked

    def launch(self, command, cwd, **kw):
        self.commands.append(command)
        class R:
            pass
        r = R(); r.blocked = self._blocked; r.blockedReason = "no"; return r


def _executor(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    ib = NullInputBackend()
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=ib,
                        estop=EmergencyStop())
    return ex, ib


def test_open_chrome_launches_via_broker():
    b = FakeBroker()
    r = open_chrome(broker=b, cwd="C:/work")
    assert r.success
    assert b.commands == ['start "" chrome']


def test_open_chrome_blocked():
    r = open_chrome(broker=FakeBroker(blocked=True), cwd="C:/work")
    assert not r.success


def test_navigate_focuses_bar_types_and_enters(tmp_path):
    ex, ib = _executor(tmp_path)
    r = navigate("https://example.com/path?q=1", executor=ex, sleep=lambda s: None)
    assert r.success
    assert ("hotkey", ("CTRL", "L")) in ib.calls
    assert ("type_text", "https://example.com/path?q=1") in ib.calls
    assert ("press_key", "ENTER") in ib.calls


def test_navigate_rejects_unsafe_url(tmp_path):
    ex, ib = _executor(tmp_path)
    r = navigate("javascript:alert(1)", executor=ex, sleep=lambda s: None)
    assert not r.success
    assert ib.calls == []  # never typed anything


def test_navigate_aborts_when_browser_not_foreground(tmp_path):
    ex, ib = _executor(tmp_path)
    r = navigate("https://example.com", executor=ex, foreground=lambda: False,
                 sleep=lambda s: None)
    assert not r.success
    assert "foreground" in r.error
    assert ib.calls == []  # never typed into the wrong window


def test_navigate_proceeds_when_foreground_confirmed(tmp_path):
    ex, ib = _executor(tmp_path)
    r = navigate("https://example.com", executor=ex, foreground=lambda: True,
                 sleep=lambda s: None)
    assert r.success
    assert ("hotkey", ("CTRL", "L")) in ib.calls
    assert ("type_text", "https://example.com") in ib.calls


def test_ensure_foreground_confirms_once_chrome_is_active():
    switched = []
    # Active window is something else twice, then Chrome.
    seq = iter([
        SimpleNamespace(title="dw-demo.txt - Notepad", process="Notepad.exe"),
        SimpleNamespace(title="Project Settings", process="Unity.exe"),
        SimpleNamespace(title="New Tab - Google Chrome", process="chrome.exe"),
    ])
    ok = ensure_foreground("Chrome", active_window=lambda: next(seq),
                           switch=lambda t: switched.append(t),
                           attempts=5, delay=0, sleep=lambda s: None)
    assert ok
    assert switched == ["Chrome"]  # re-used the window switch once


def test_ensure_foreground_times_out_when_never_active():
    polls = []

    def active():
        polls.append(1)
        return SimpleNamespace(title="Project Settings", process="Unity.exe")

    ok = ensure_foreground("Chrome", active_window=active, switch=lambda t: None,
                           attempts=3, delay=0, sleep=lambda s: None)
    assert not ok
    assert len(polls) == 3  # polled exactly `attempts` times, then gave up


def test_ensure_foreground_handles_no_active_window():
    ok = ensure_foreground("Chrome", active_window=lambda: None, switch=lambda t: None,
                           attempts=2, delay=0, sleep=lambda s: None)
    assert not ok


def test_fill_field_clicks_and_types(tmp_path):
    ex, ib = _executor(tmp_path)
    r = fill_field("Email", "a@b.com", executor=ex, ui=FakeBrowserUi(edit=(40, 60)),
                   sleep=lambda s: None)
    assert r.success
    clicks = [c for c in ib.calls if c[0] == "click"]
    assert (40, 60) == (clicks[0][2], clicks[0][3])
    assert ("type_text", "a@b.com") in ib.calls


def test_fill_field_missing_input_fails(tmp_path):
    ex, ib = _executor(tmp_path)
    r = fill_field("Nope", "x", executor=ex, ui=NullBrowserUi(), sleep=lambda s: None)
    assert not r.success
    assert ib.calls == []


def test_click_control_clicks_button(tmp_path):
    ex, ib = _executor(tmp_path)
    r = click_control("Search", executor=ex, ui=FakeBrowserUi(button=(120, 200)))
    assert r.success
    assert any(c[0] == "click" and (c[2], c[3]) == (120, 200) for c in ib.calls)


def test_submit_form_navigates_fills_and_submits(tmp_path):
    ex, ib = _executor(tmp_path)
    r = submit_form({"User": "neo", "Pass": "zion"}, executor=ex, ui=FakeBrowserUi(),
                    url="https://login.test", submit_label="Sign in",
                    sleep=lambda s: None)
    assert r.success
    assert ("type_text", "neo") in ib.calls
    assert ("type_text", "zion") in ib.calls
    # navigated first
    assert ("hotkey", ("CTRL", "L")) in ib.calls


def test_submit_form_aborts_on_missing_field(tmp_path):
    ex, ib = _executor(tmp_path)
    r = submit_form({"Only": "x"}, executor=ex, ui=NullBrowserUi(), sleep=lambda s: None)
    assert not r.success


def test_factory_falls_back_to_null():
    assert isinstance(get_browser_ui(prefer_real=False), NullBrowserUi)
